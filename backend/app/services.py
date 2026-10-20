import base64
import copy
import hashlib
from contextlib import contextmanager
from pathlib import Path
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select, text
from .config import DATA, SECRET_KEY
from .db import Session, Setting, Document, Task, uid

cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()))
DEFAULT = {'base_url': 'https://api.openai.com/v1', 'model': '', 'timeout': 180, 'concurrency': 2, 'mode': 'reference', 'extra': {}}


@contextmanager
def transaction():
    with Session() as db:
        if db.bind.dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def get_doc(db, ident, kind, lock=False):
    query = select(Document).where(Document.id == ident, Document.kind == kind)
    if lock:
        query = query.with_for_update()
    doc = db.scalar(query)
    if not doc:
        raise HTTPException(404, '记录不存在')
    return doc


def get_setting(db, key, default=None):
    row = db.get(Setting, key)
    return copy.deepcopy(row.value) if row else copy.deepcopy(default)


def set_setting(db, key, value):
    row = db.get(Setting, key)
    if row:
        row.value = copy.deepcopy(value)
    else:
        db.add(Setting(key=key, value=copy.deepcopy(value)))


def provider_config(db, kind, public=False):
    data = {**DEFAULT, **get_setting(db, kind, {})}
    encrypted = data.pop('encrypted_key', '')
    data['has_key'] = bool(encrypted)
    data['api_key'] = '' if public or not encrypted else cipher.decrypt(encrypted.encode()).decode()
    return data


def save_provider(db, kind, data):
    current = get_setting(db, kind, {})
    if data.pop('clear_key', False):
        current.pop('encrypted_key', None)
    key = data.pop('api_key', '').strip()
    data.pop('has_key', None)
    if key:
        current['encrypted_key'] = cipher.encrypt(key.encode()).decode()
    current.update(data)
    set_setting(db, kind, current)


def product_json(doc):
    return {'id': doc.id, 'created_at': doc.created_at.isoformat(), **copy.deepcopy(doc.data)}


def project_json(doc):
    data = copy.deepcopy(doc.data)
    data.pop('product_snapshot', None)
    return {'id': doc.id, 'created_at': doc.created_at.isoformat(), **data}


def stored_file(relative: str) -> Path:
    normalized = relative.replace('\\', '/')
    parts = normalized.split('/')
    if len(parts) < 2 or parts[0] not in ('products', 'projects') or any(p in ('', '.', '..') or p.startswith('.') for p in parts):
        raise HTTPException(400, '无效文件路径')
    target = (DATA / normalized).resolve()
    allowed_root = (DATA / parts[0]).resolve()
    if allowed_root not in target.parents or DATA not in allowed_root.parents:
        raise HTTPException(400, '无效文件路径')
    return target


def file_url(relative):
    return '/api/files/' + relative.replace('\\', '/')


def relative_url_path(url):
    return stored_file(url.removeprefix('/api/files/'))


def ref_paths(product):
    return [relative_url_path(x['url']) for x in product.get('images', []) if x.get('role') in ('main', 'detail', '外观主参考', '细节参考')][:6]


def active_tasks(db, project_id):
    return list(db.scalars(select(Task).where(Task.project_id == project_id, Task.status.in_(['queued', 'running']))))


def enqueue_images(db, doc, slide_ids=None, instruction='', force_refine=False):
    data = copy.deepcopy(doc.data)
    if not data.get('slides'):
        raise HTTPException(409, '请先完成内容策划')
    if any(t.type == 'plan' for t in active_tasks(db, doc.id)):
        raise HTTPException(409, '策划任务正在执行')
    active = {t.slide_id for t in active_tasks(db, doc.id)}
    valid = {s['id'] for s in data['slides']}
    if slide_ids is not None and not set(slide_ids).issubset(valid):
        raise HTTPException(400, '包含无效图片编号')
    selected = [s for s in data['slides'] if (s['id'] in slide_ids if slide_ids is not None else s['status'] in ('pending', 'failed') or s.get('needs_regeneration', False))]
    for slide in selected:
        if slide['id'] in active:
            raise HTTPException(409, '该图片已有排队或生成任务')
        slide['status'], slide['error'] = 'queued', ''
        db.add(Task(id=uid(), project_id=doc.id, slide_id=slide['id'], type='image', payload={'instruction': instruction, 'force_refine': force_refine}))
    if not selected:
        raise HTTPException(409, '没有需要生成的图片')
    data['status'], data['error'] = 'generating', ''
    doc.data = data


def refresh_project(db, doc):
    data = copy.deepcopy(doc.data)
    active = active_tasks(db, doc.id)
    if active:
        data['status'] = 'planning' if any(t.type == 'plan' for t in active) else 'generating'
    elif data.get('slides'):
        states = [s['status'] for s in data['slides']]
        data['status'] = 'ready' if all(s == 'ready' for s in states) and not any(s.get('needs_regeneration') for s in data['slides']) else ('failed' if 'failed' in states else 'draft')
    doc.data = data
