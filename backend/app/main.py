import copy
import hashlib
import io
import json
import os
import re
import secrets
import time
import zipfile
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Depends, Request, Response, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from sqlalchemy import select
from .config import DATA, ROOT, SECRET_KEY, COOKIE_SECURE, SESSION_DAYS
from .db import Session, Document, Task, Setting, uid, initialize, task_json
from .services import (transaction, get_doc, get_setting, set_setting, provider_config, save_provider, product_json, project_json, stored_file, file_url, relative_url_path, active_tasks, enqueue_images)

serializer = URLSafeTimedSerializer(SECRET_KEY, salt='admin-session')
rate_limits = defaultdict(deque)


@asynccontextmanager
async def lifespan(app):
    initialize()
    initial_password = os.getenv('ADMIN_PASSWORD', '')
    if initial_password:
        if len(initial_password) < 10:
            raise RuntimeError('ADMIN_PASSWORD 至少10个字符')
        with transaction() as db:
            if db.bind.dialect.name == 'postgresql':
                from sqlalchemy import text
                db.execute(text('LOCK TABLE settings IN EXCLUSIVE MODE'))
            if not get_setting(db, 'admin'):
                salt = secrets.token_hex(16)
                set_setting(db, 'admin', {'salt': salt, 'hash': password_hash(initial_password, salt), 'version': secrets.token_hex(16)})
    yield


app = FastAPI(title='TK 图文工作台', lifespan=lifespan)


@app.middleware('http')
async def security(request: Request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        if origin and urlsplit(origin).netloc != request.headers.get('host'):
            return Response('跨域写入被拒绝', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def auth(request: Request):
    try:
        token = serializer.loads(request.cookies.get('tk_session', ''), max_age=SESSION_DAYS * 86400)
        with Session() as db:
            admin = get_setting(db, 'admin', {})
        if not admin or token.get('v') != admin.get('version'):
            raise BadSignature('invalid')
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, '请先登录')


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def set_cookie(response, version):
    response.set_cookie('tk_session', serializer.dumps({'v': version}), httponly=True, secure=COOKIE_SECURE, samesite='strict', max_age=SESSION_DAYS * 86400)


class Password(BaseModel):
    password: str = Field(min_length=10, max_length=128)


@app.get('/api/auth/status')
def auth_status(request: Request):
    with Session() as db:
        setup = not bool(get_setting(db, 'admin'))
    try:
        auth(request)
        logged = True
    except HTTPException:
        logged = False
    return {'authenticated': logged, 'setup_required': setup}


@app.post('/api/auth/setup')
def setup(body: Password, response: Response):
    # Serialized with a settings-table lock on PostgreSQL to prevent first-run races.
    with transaction() as db:
        if db.bind.dialect.name == 'postgresql':
            from sqlalchemy import text
            db.execute(text('LOCK TABLE settings IN EXCLUSIVE MODE'))
        if get_setting(db, 'admin'):
            raise HTTPException(409, '管理员已设置')
        salt = secrets.token_hex(16)
        version = secrets.token_hex(16)
        set_setting(db, 'admin', {'salt': salt, 'hash': password_hash(body.password, salt), 'version': version})
    set_cookie(response, version)
    return {'ok': True}


@app.post('/api/auth/login')
def login(body: Password, request: Request, response: Response):
    client = request.client.host if request.client else 'local'
    recent = rate_limits[client]
    current = time.monotonic()
    while recent and current - recent[0] > 300:
        recent.popleft()
    if len(recent) >= 10:
        raise HTTPException(429, '登录尝试过多，请5分钟后再试')
    recent.append(current)
    with Session() as db:
        admin = get_setting(db, 'admin')
    if not admin or not secrets.compare_digest(password_hash(body.password, admin['salt']), admin['hash']):
        raise HTTPException(401, '密码错误')
    recent.clear()
    set_cookie(response, admin['version'])
    return {'ok': True}


@app.post('/api/auth/logout')
def logout(response: Response):
    response.delete_cookie('tk_session')
    return {'ok': True}


@app.get('/api/health')
def health():
    with Session() as db:
        beat = get_setting(db, 'worker_heartbeat', {})
        dialect = db.bind.dialect.name
    return {'status': 'ok', 'database': dialect, 'worker_alive': time.time() - beat.get('time', 0) < 30}


class ProductInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=12000)
    category: str = ''
    sku: str = ''
    features: str = ''
    constraints: str = ''
    price: str = ''
    currency: str = ''


@app.get('/api/products', dependencies=[Depends(auth)])
def products(q: str = ''):
    with Session() as db:
        docs = db.scalars(select(Document).where(Document.kind == 'product').order_by(Document.created_at.desc()))
        return [product_json(d) for d in docs if not d.data.get('archived') and q.lower() in (d.data['name'] + d.data.get('sku', '')).lower()]


@app.post('/api/products', dependencies=[Depends(auth)])
def create_product(body: ProductInput):
    with transaction() as db:
        doc = Document(id=uid(), kind='product', data={**body.model_dump(), 'images': [], 'archived': False})
        db.add(doc)
        db.flush()
        return product_json(doc)


@app.get('/api/products/{ident}', dependencies=[Depends(auth)])
def product(ident: str):
    with Session() as db:
        return product_json(get_doc(db, ident, 'product'))


@app.patch('/api/products/{ident}', dependencies=[Depends(auth)])
def update_product(ident: str, body: dict):
    with transaction() as db:
        doc = get_doc(db, ident, 'product', True)
        merged = {**{k: v for k, v in doc.data.items() if k in ProductInput.model_fields}, **body}
        try:
            validated = ProductInput(**merged)
        except ValidationError:
            raise HTTPException(422, '商品字段无效，请检查名称、长度和数据格式')
        doc.data = {**doc.data, **validated.model_dump()}
        return product_json(doc)


@app.delete('/api/products/{ident}', dependencies=[Depends(auth)])
def archive_product(ident: str):
    with transaction() as db:
        doc = get_doc(db, ident, 'product', True)
        doc.data = {**doc.data, 'archived': True}
    return {'ok': True}


@app.post('/api/products/{ident}/images', dependencies=[Depends(auth)])
async def upload(ident: str, files: list[UploadFile] = File(...)):
    if len(files) > 12:
        raise HTTPException(400, '一次最多上传12张图片')
    pending = []
    for item in files:
        raw = await item.read(15 * 1024 * 1024 + 1)
        if len(raw) > 15 * 1024 * 1024:
            raise HTTPException(400, '每张图片不超过15MB')
        try:
            with Image.open(io.BytesIO(raw)) as im:
                if im.width * im.height > 40_000_000:
                    raise HTTPException(400, '图片像素过大')
                im.load()
                image = im.convert('RGB')
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise HTTPException(400, '图片格式无效，请上传 PNG/JPG/WebP')
        pending.append((item.filename or 'reference.jpg', image))
    with transaction() as db:
        doc = get_doc(db, ident, 'product', True)
        images = copy.deepcopy(doc.data['images'])
        if len(images) + len(pending) > 20:
            raise HTTPException(400, '每个商品最多20张参考图')
        for filename, image in pending:
            image_id = uid()
            relative = f'products/{ident}/{image_id}.jpg'
            path = stored_file(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(path, quality=94)
            images.append({'id': image_id, 'filename': Path(filename).name, 'url': file_url(relative), 'role': 'main' if not images else 'detail'})
        doc.data = {**doc.data, 'images': images}
        return product_json(doc)


@app.patch('/api/products/{ident}/images/{image_id}', dependencies=[Depends(auth)])
def image_role(ident: str, image_id: str, body: dict):
    role = body.get('role')
    if role not in ('main', 'detail', 'scene'):
        raise HTTPException(400, '参考图角色无效')
    with transaction() as db:
        doc = get_doc(db, ident, 'product', True)
        data = copy.deepcopy(doc.data)
        item = next((i for i in data['images'] if i['id'] == image_id), None)
        if not item:
            raise HTTPException(404, '图片不存在')
        item['role'] = role
        doc.data = data
        return product_json(doc)


@app.delete('/api/products/{ident}/images/{image_id}', dependencies=[Depends(auth)])
def delete_image(ident: str, image_id: str):
    with transaction() as db:
        doc = get_doc(db, ident, 'product', True)
        doc.data = {**doc.data, 'images': [i for i in doc.data['images'] if i['id'] != image_id]}
        # Physical files retained: historical project snapshots may still reference them.
        return product_json(doc)


class Provider(BaseModel):
    model_config = ConfigDict(extra='forbid')
    base_url: str = Field(max_length=500)
    model: str = Field(default='', max_length=200)
    api_key: str = Field(default='', max_length=4000)
    has_key: bool = False
    clear_key: bool = False
    timeout: int = Field(default=180, ge=10, le=600)
    concurrency: int = Field(default=2, ge=1, le=8)
    mode: str = 'reference'
    extra: dict = Field(default_factory=dict)


class SettingsInput(BaseModel):
    analysis: Provider
    image: Provider


@app.get('/api/settings', dependencies=[Depends(auth)])
def settings():
    with Session() as db:
        return {k: provider_config(db, k, True) for k in ('analysis', 'image')}


@app.put('/api/settings', dependencies=[Depends(auth)])
def update_settings(body: SettingsInput):
    with transaction() as db:
        for kind in ('analysis', 'image'):
            provider = getattr(body, kind)
            try:
                parsed = urlsplit(provider.base_url)
                valid = parsed.scheme in ('http', 'https') and bool(parsed.hostname) and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
            except ValueError:
                valid = False
            if not valid:
                raise HTTPException(400, '接口地址必须是有效 HTTP/HTTPS API 根地址，不能包含账号或查询参数')
            if provider.mode not in ('reference', 'background'):
                raise HTTPException(400, '生成模式无效')
            save_provider(db, kind, provider.model_dump())
    return settings()


@app.post('/api/settings/test/{kind}', dependencies=[Depends(auth)])
async def test_settings(kind: str):
    from .providers import test_provider
    if kind not in ('analysis', 'image'):
        raise HTTPException(404, '模型类型不存在')
    with Session() as db:
        config = provider_config(db, kind)
    try:
        return {'ok': True, 'message': await test_provider(kind, config)}
    except Exception as exc:
        # Provider errors are sanitized again at API boundary.
        message = str(exc).replace(config.get('api_key', '') or '\x00', '***')[:600]
        return {'ok': False, 'message': message}


class ProjectInput(BaseModel):
    product_id: str
    market: str = Field(min_length=1, max_length=100)
    language: str = Field(min_length=1, max_length=100)
    image_count: int = Field(default=6, ge=4, le=10)
    style: str = Field(default='简洁明亮，突出商品', max_length=2000)
    brief: str = Field(default='', max_length=6000)
    auto_generate: bool = False


@app.get('/api/projects', dependencies=[Depends(auth)])
def projects():
    with Session() as db:
        return [project_json(d) for d in db.scalars(select(Document).where(Document.kind == 'project').order_by(Document.created_at.desc()))]


@app.post('/api/projects', dependencies=[Depends(auth)])
def create_project(body: ProjectInput):
    with transaction() as db:
        product = get_doc(db, body.product_id, 'product')
        if product.data.get('archived'):
            raise HTTPException(409, '商品已归档')
        config = provider_config(db, 'analysis')
        if not config['model'] or not config['api_key']:
            raise HTTPException(400, '请先配置分析模型和 API Key')
        ident = uid()
        doc = Document(id=ident, kind='project', data={**body.model_dump(), 'title': product.data['name'] + ' · ' + body.market, 'product_name': product.data['name'], 'product_snapshot': product_json(product), 'status': 'planning', 'caption': '', 'tags': [], 'analysis': {}, 'error': '', 'slides': []})
        db.add(doc)
        db.add(Task(id=uid(), project_id=ident, type='plan', payload={}))
        db.flush()
        return project_json(doc)


@app.get('/api/projects/{ident}', dependencies=[Depends(auth)])
def project(ident: str):
    with Session() as db:
        return project_json(get_doc(db, ident, 'project'))


class SlideEditInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    title: str = Field(max_length=2000)
    body: str = Field(max_length=4000)
    prompt: str = Field(max_length=12000)


class ProjectEditInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str | None = Field(default=None, max_length=1000)
    caption: str | None = Field(default=None, max_length=12000)
    style: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=40)
    slides: list[SlideEditInput] | None = Field(default=None, max_length=10)


class GenerateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    slide_ids: list[str] | None = Field(default=None, max_length=10)


@app.patch('/api/projects/{ident}', dependencies=[Depends(auth)])
def update_project(ident: str, body: ProjectEditInput):
    body = body.model_dump(exclude_none=True)
    with transaction() as db:
        doc = get_doc(db, ident, 'project', True)
        if active_tasks(db, ident):
            raise HTTPException(409, '任务进行中，请完成后编辑')
        data = copy.deepcopy(doc.data)
        for key in ('title', 'caption', 'style'):
            if key in body:
                if not isinstance(body[key], str) or len(body[key]) > 12000:
                    raise HTTPException(400, '文本字段无效或过长')
                data[key] = body[key]
        if 'tags' in body:
            if not isinstance(body['tags'], list) or len(body['tags']) > 40 or not all(isinstance(x, str) for x in body['tags']):
                raise HTTPException(400, '标签格式无效')
            data['tags'] = body['tags']
        for edit in body.get('slides', []):
            slide = next((s for s in data['slides'] if s['id'] == edit.get('id')), None)
            if not slide:
                raise HTTPException(400, '图片不存在')
            for key in ('title', 'body', 'prompt'):
                if key in edit:
                    if not isinstance(edit[key], str) or len(edit[key]) > 12000:
                        raise HTTPException(400, '图片文本无效')
                    slide[key] = edit[key]
            rerender_slide(data, slide)
        doc.data = data
        return project_json(doc)


def rerender_slide(project_data, slide):
    if not slide.get('selected_version_id'):
        return
    from .rendering import render_image
    version = next(v for v in slide['versions'] if v['id'] == slide['selected_version_id'])
    relative = f'projects/{project_data.get("storage_id", "renders")}/{uid()}.jpg'
    target = stored_file(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    render_image(relative_url_path(version['base_url']), target, slide['title'], slide['body'], project_data['language'])
    version['url'] = file_url(relative)
    slide['url'] = version['url']


@app.post('/api/projects/{ident}/generate', dependencies=[Depends(auth)])
def generate(ident: str, body: GenerateInput):
    with transaction() as db:
        doc = get_doc(db, ident, 'project', True)
        enqueue_images(db, doc, body.slide_ids)
        return project_json(doc)


@app.post('/api/projects/{ident}/replan', dependencies=[Depends(auth)])
def replan(ident: str):
    with transaction() as db:
        doc = get_doc(db, ident, 'project', True)
        if active_tasks(db, ident):
            raise HTTPException(409, '已有进行中的任务')
        if any(s.get('versions') for s in doc.data.get('slides', [])):
            raise HTTPException(409, '已有图片版本，请新建项目以保留历史作品')
        doc.data = {**doc.data, 'status': 'planning', 'error': ''}
        db.add(Task(id=uid(), project_id=ident, type='plan', payload={}))
        return project_json(doc)


@app.post('/api/projects/{ident}/slides/{slide_id}/regenerate', dependencies=[Depends(auth)])
def regenerate(ident: str, slide_id: str, body: dict):
    instruction = body.get('instruction', '')
    if not isinstance(instruction, str) or len(instruction) > 4000:
        raise HTTPException(400, '修改要求无效')
    with transaction() as db:
        doc = get_doc(db, ident, 'project', True)
        enqueue_images(db, doc, [slide_id], instruction)
        return project_json(doc)


@app.patch('/api/projects/{ident}/slides/{slide_id}', dependencies=[Depends(auth)])
def edit_slide(ident: str, slide_id: str, body: dict):
    with transaction() as db:
        doc = get_doc(db, ident, 'project', True)
        if active_tasks(db, ident):
            raise HTTPException(409, '请等待任务完成再编辑')
        data = copy.deepcopy(doc.data)
        slide = next((s for s in data['slides'] if s['id'] == slide_id), None)
        if not slide:
            raise HTTPException(404, '图片不存在')
        for key in ('title', 'body'):
            if key in body:
                if not isinstance(body[key], str) or len(body[key]) > 2000:
                    raise HTTPException(400, '文案过长或格式无效')
                slide[key] = body[key]
        if 'selected_version_id' in body:
            version = next((v for v in slide['versions'] if v['id'] == body['selected_version_id']), None)
            if not version:
                raise HTTPException(400, '版本不存在')
            slide['selected_version_id'] = version['id']
            slide['status'], slide['error'] = 'ready', ''
        rerender_slide(data, slide)
        if all(s['status'] == 'ready' for s in data['slides']):
            data['status'] = 'ready'
        doc.data = data
        return project_json(doc)


@app.delete('/api/projects/{ident}', dependencies=[Depends(auth)])
def delete_project(ident: str):
    with transaction() as db:
        doc = get_doc(db, ident, 'project', True)
        if active_tasks(db, ident):
            raise HTTPException(409, '任务进行中，暂时无法删除')
        for task in db.scalars(select(Task).where(Task.project_id == ident)):
            db.delete(task)
        db.delete(doc)
    return {'ok': True}


@app.get('/api/projects/{ident}/export', dependencies=[Depends(auth)])
def export(ident: str, slide_ids: str = '', include_bases: bool = False):
    with Session() as db:
        doc = get_doc(db, ident, 'project')
        data = project_json(doc)
    selected = set(slide_ids.split(',')) if slide_ids else None
    slides = [s for s in data['slides'] if s.get('url') and (selected is None or s['id'] in selected)]
    if not slides:
        raise HTTPException(400, '没有可导出的图片')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for slide in slides:
            archive.write(relative_url_path(slide['url']), f'{slide["position"]:02d}.jpg')
            if include_bases:
                version = next(v for v in slide['versions'] if v['id'] == slide['selected_version_id'])
                archive.write(relative_url_path(version['base_url']), f'bases/{slide["position"]:02d}.png')
        archive.writestr('caption.txt', data.get('caption', '') + '\n\n' + ' '.join(data.get('tags', [])))
        archive.writestr('plan.json', json.dumps(data, ensure_ascii=False, indent=2))
    buffer.seek(0)
    return StreamingResponse(buffer, media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="content-{ident[:8]}.zip"'})


@app.get('/api/tasks', dependencies=[Depends(auth)])
def tasks():
    with Session() as db:
        return [task_json(t) for t in db.scalars(select(Task).order_by(Task.created_at.desc()).limit(100))]


@app.post('/api/tasks/{ident}/retry', dependencies=[Depends(auth)])
def retry_task(ident: str):
    with transaction() as db:
        task = db.get(Task, ident)
        if not task:
            raise HTTPException(404, '任务不存在')
        doc = get_doc(db, task.project_id, 'project', True)
        if task.status != 'failed':
            raise HTTPException(409, '仅失败任务可重试')
        if any(t.slide_id == task.slide_id or t.type == 'plan' or task.type == 'plan' for t in active_tasks(db, doc.id)):
            raise HTTPException(409, '存在冲突的活动任务')
        if task.type == 'plan' and any(s.get('versions') for s in doc.data.get('slides', [])):
            raise HTTPException(409, '已有图片版本，请新建项目')
        if task.type == 'image' and not any(s['id'] == task.slide_id for s in doc.data.get('slides', [])):
            raise HTTPException(409, '该任务所属图片已被重新策划替换，请在当前项目中操作')
        data = copy.deepcopy(doc.data)
        data['status'], data['error'] = ('planning' if task.type == 'plan' else 'generating'), ''
        for slide in data['slides']:
            if slide['id'] == task.slide_id:
                slide['status'], slide['error'] = 'queued', ''
        doc.data = data
        task.status, task.error = 'queued', ''
        return task_json(task)


@app.get('/api/files/{path:path}', dependencies=[Depends(auth)])
def files(path: str):
    target = stored_file(path)
    if not target.is_file():
        raise HTTPException(404, '文件不存在')
    return FileResponse(target)


FRONTEND = ROOT / 'frontend' / 'dist'
if FRONTEND.is_dir():
    app.mount('/assets', StaticFiles(directory=FRONTEND / 'assets'), name='assets')

    @app.get('/{path:path}')
    def spa(path: str):
        if path.startswith('api/'):
            raise HTTPException(404, '接口不存在')
        return FileResponse(FRONTEND / 'index.html')
