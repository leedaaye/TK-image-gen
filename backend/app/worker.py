"""Durable single-process worker; API and worker share the database and DATA_DIR."""
import asyncio
import copy
import io
import logging
import os
import signal
import time
from datetime import datetime, timezone
from PIL import Image
from sqlalchemy import select
from .config import DATA
from .db import Session, Task, uid, initialize
from .services import transaction, get_doc, get_setting, set_setting, provider_config, ref_paths, stored_file, file_url, enqueue_images, refresh_project
from .providers import plan_content, refine_slide_prompt, generate_image

log = logging.getLogger('worker')
analysis_semaphore = asyncio.Semaphore(2)


def exclusive_worker_lock():
    handle = (DATA / '.worker.lock').open('a+b')
    handle.write(b'0')
    handle.flush()
    handle.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('同一数据目录已有 Worker 运行')
    return handle


def recover_interrupted():
    with transaction() as db:
        for task in db.scalars(select(Task).where(Task.status == 'running')):
            task.status = 'failed'
            task.error = 'Worker 上次中断；为避免重复付费，请确认服务商任务后手动重试'
            doc = get_doc(db, task.project_id, 'project', True)
            data = copy.deepcopy(doc.data)
            data['status'], data['error'] = 'failed', task.error
            for slide in data.get('slides', []):
                if slide['id'] == task.slide_id:
                    slide['status'], slide['error'] = 'failed', task.error
            doc.data = data


def claim_task(running):
    with transaction() as db:
        candidates = list(db.scalars(select(Task).where(Task.status == 'queued').order_by(Task.created_at).with_for_update(skip_locked=True)))
        for task in candidates:
            kind = 'analysis' if task.type == 'plan' else 'image'
            limit = provider_config(db, kind)['concurrency']
            if sum(1 for _, k in running.values() if k == kind) >= limit:
                continue
            doc = get_doc(db, task.project_id, 'project', True)
            task.status, task.error = 'running', ''
            data = copy.deepcopy(doc.data)
            for slide in data.get('slides', []):
                if slide['id'] == task.slide_id:
                    slide['status'] = 'generating'
            doc.data = data
            return task.id, kind
    return None


async def execute(task_id):
    config = {}
    analysis_config = {}
    try:
        with Session() as db:
            task = db.get(Task, task_id)
            project_id, slide_id, task_type = task.project_id, task.slide_id, task.type
            payload = copy.deepcopy(task.payload)
            data = copy.deepcopy(get_doc(db, project_id, 'project').data)
            config = provider_config(db, 'analysis' if task_type == 'plan' else 'image')
            analysis_config = provider_config(db, 'analysis')
            image_mode = provider_config(db, 'image')['mode']
        product = data['product_snapshot']
        references = ref_paths(product)
        if task_type == 'plan':
            async with analysis_semaphore:
                plan = await plan_content(config, product, data['market'], data['language'], data['image_count'], data['style'], data['brief'], references, image_mode=image_mode)
            with transaction() as db:
                doc = get_doc(db, project_id, 'project', True)
                current = copy.deepcopy(doc.data)
                current.update({k: plan[k] for k in ('title', 'caption', 'tags', 'analysis')})
                current['slides'] = [{**slide, 'id': uid(), 'position': i + 1, 'status': 'pending', 'error': '', 'selected_version_id': None, 'url': None, 'versions': [], 'prompt_pipeline': 'native_text_v1', 'prompt_is_current': True, 'prompt_image_mode': image_mode, 'needs_regeneration': False} for i, slide in enumerate(plan['slides'])]
                current['status'], current['error'] = 'draft', ''
                current['storage_id'] = project_id
                current['prompt_pipeline'] = 'native_text_v1'
                doc.data = current
                db.get(Task, task_id).status = 'completed'
                db.flush()
                if current['auto_generate']:
                    enqueue_images(db, doc)
        else:
            slide = next(s for s in data['slides'] if s['id'] == slide_id)
            instruction = payload.get('instruction', '')
            prepared = payload.get('prepared_slide')
            prepared_context = {'style': data['style'], 'market': data['market'], 'language': data['language'], 'title': slide['title'], 'body': slide['body'], 'prompt': slide['prompt']}
            if prepared and payload.get('prepared_image_mode') == image_mode and payload.get('prepared_context') == prepared_context:
                # A retry reuses the already-approved AI brief instead of paying
                # for another refinement or changing the failed generation's intent.
                slide = {**slide, **prepared}
            elif (payload.get('force_refine') or instruction or not slide.get('prompt_is_current')
                  or slide.get('prompt_pipeline') != 'native_text_v1'
                  or slide.get('prompt_image_mode') != image_mode):
                async with analysis_semaphore:
                    refined = await refine_slide_prompt(analysis_config, product, data, slide, instruction, references, image_mode=image_mode)
                slide = {**slide, **refined}
                prepared = refined
            prompt = slide['prompt']
            if slide['title'] not in prompt or slide['body'] not in prompt:
                raise RuntimeError('完整生图提示词必须包含本张标题与正文，请更新策划')
            # Persist the exact final brief BEFORE the paid image request.
            with transaction() as db:
                doc = get_doc(db, project_id, 'project', True)
                current = copy.deepcopy(doc.data)
                target = next(s for s in current['slides'] if s['id'] == slide_id)
                target.update({k: slide[k] for k in ('title', 'body', 'prompt')})
                target.update(prompt_is_current=True, prompt_pipeline='native_text_v1', prompt_image_mode=image_mode)
                doc.data = current
                queued = db.get(Task, task_id)
                queued.payload = {**queued.payload, 'prepared_slide': {k: slide[k] for k in ('title', 'body', 'prompt')}, 'prepared_image_mode': image_mode, 'prepared_context': {**prepared_context, 'prompt': prompt}}
            # No raw facts, dict dumps, extra directives or copy are appended here.
            raw = await generate_image(config, prompt, references if image_mode == 'reference' else [])
            version_id = uid()
            base_relative = f'projects/{project_id}/{slide_id}/{version_id}-base.png'
            output_relative = f'projects/{project_id}/{slide_id}/{version_id}.jpg'
            base_path, output_path = stored_file(base_relative), stored_file(output_relative)
            base_path.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                image.convert('RGB').save(base_path, format='PNG')
                # Preserve the entire native composition: no text overlays,
                # crops or forced aspect-ratio changes that could clip copy.
                image.convert('RGB').save(output_path, format='JPEG', quality=95)
            with transaction() as db:
                doc = get_doc(db, project_id, 'project', True)
                current = copy.deepcopy(doc.data)
                target = next(s for s in current['slides'] if s['id'] == slide_id)
                version = {'id': version_id, 'url': file_url(output_relative), 'base_url': file_url(base_relative), 'created_at': datetime.now(timezone.utc).isoformat(), 'instruction': payload.get('instruction', ''), 'model': config['model'], 'mode': config['mode'], 'prompt': prompt, 'title': slide['title'], 'body': slide['body'], 'render_mode': 'native_text', 'analysis_model': analysis_config['model'], 'style': data['style']}
                target['versions'].append(version)
                target.update(status='ready', error='', selected_version_id=version_id, url=version['url'], needs_regeneration=False)
                doc.data = current
                db.get(Task, task_id).status = 'completed'
                db.flush()
                refresh_project(db, doc)
    except Exception as exc:
        message = str(exc)
        for private_config in (config, analysis_config):
            message = message.replace(private_config.get('api_key', '') or '\x00', '***')
        message = message[:1000]
        log.error('任务 %s 失败: %s', task_id, message)
        with transaction() as db:
            task = db.get(Task, task_id)
            if not task:
                return
            task.status, task.error = 'failed', message
            doc = get_doc(db, task.project_id, 'project', True)
            data = copy.deepcopy(doc.data)
            data['error'] = message
            if task.type == 'plan':
                data['status'] = 'failed'
            for slide in data.get('slides', []):
                if slide['id'] == task.slide_id:
                    slide['status'], slide['error'] = 'failed', message
            doc.data = data
            db.flush()
            if task.type != 'plan':
                refresh_project(db, doc)


async def run():
    global analysis_semaphore
    initialize()
    with Session() as db:
        analysis_semaphore = asyncio.Semaphore(provider_config(db, 'analysis')['concurrency'])
    lock_handle = exclusive_worker_lock()
    recover_interrupted()
    running = {}
    last_heartbeat = 0
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
    try:
        while not stop.is_set():
            for task in list(running):
                if task.done():
                    task.result()
                    del running[task]
            if time.time() - last_heartbeat > 5:
                with transaction() as db:
                    set_setting(db, 'worker_heartbeat', {'time': time.time()})
                last_heartbeat = time.time()
            claimed = claim_task(running)
            if claimed:
                ident, kind = claimed
                running[asyncio.create_task(execute(ident))] = (ident, kind)
            else:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=0.8)
                except asyncio.TimeoutError:
                    pass
        if running:
            await asyncio.gather(*running)
    finally:
        lock_handle.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    asyncio.run(run())
