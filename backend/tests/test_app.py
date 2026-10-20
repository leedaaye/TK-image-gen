import asyncio
import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from app.db import Base, engine, Session, Task, Document
from app.main import app
from app import worker
from app.services import provider_config, stored_file, transaction


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        assert client.post('/api/auth/setup', json={'password': 'testpassword123'}).status_code == 200
        yield client


def image_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (320, 400), '#7fa6b0').save(buffer, 'PNG')
    return buffer.getvalue()


def configure(client):
    provider = {'base_url': 'https://example.com/v1', 'model': 'mock', 'api_key': 'secret-token-123', 'mode': 'reference'}
    response = client.put('/api/settings', json={'analysis': provider, 'image': provider})
    assert response.status_code == 200
    assert 'secret-token-123' not in response.text
    return provider


def new_project(client):
    configure(client)
    product = client.post('/api/products', json={'name': '旅行杯', 'description': '蓝色杯子', 'constraints': '不允许编造保温时长'}).json()
    response = client.post(f'/api/products/{product["id"]}/images', files=[('files', ('cup.png', image_bytes(), 'image/png'))])
    assert response.status_code == 200
    project = client.post('/api/projects', json={'product_id': product['id'], 'market': '美国', 'language': 'English', 'image_count': 4, 'style': 'clean'}).json()
    return product, project


async def mock_plan(*args, **kwargs):
    return {'title': 'Travel cup', 'caption': 'A cup for daily routines.', 'tags': ['#cup'], 'analysis': {'missing_information': ['capacity']}, 'slides': [{'title': f'Cup {i}', 'body': 'A blue cup', 'prompt': 'Blue cup in a clean kitchen'} for i in range(4)]}


async def mock_image(*args, **kwargs):
    assert len(args[2]) == 1
    return image_bytes()


def run_next():
    claimed = worker.claim_task({})
    assert claimed
    asyncio.run(worker.execute(claimed[0]))


def test_auth_and_csrf(client):
    assert client.post('/api/auth/setup', json={'password': 'testpassword123'}).status_code == 409
    assert client.post('/api/products', json={'name': 'x'}, headers={'Origin': 'https://evil.example'}).status_code == 403
    client.post('/api/auth/logout')
    assert client.get('/api/products').status_code == 401
    assert client.get('/api/files/products/a.png').status_code == 401
    assert client.post('/api/auth/login', json={'password': 'wrongpassword'}).status_code == 401
    assert client.post('/api/auth/login', json={'password': 'testpassword123'}).status_code == 200


def test_key_encryption_and_retention(client):
    provider = configure(client)
    with Session() as db:
        assert provider_config(db, 'analysis')['api_key'] == 'secret-token-123'
        from app.db import Setting
        assert 'secret-token-123' not in json.dumps(db.get(Setting, 'analysis').value)
    provider['api_key'] = ''
    client.put('/api/settings', json={'analysis': provider, 'image': provider})
    assert client.get('/api/settings').json()['analysis']['has_key']


def test_complete_lifecycle_and_export(client, monkeypatch):
    monkeypatch.setattr(worker, 'plan_content', mock_plan)
    monkeypatch.setattr(worker, 'generate_image', mock_image)
    product, project = new_project(client)
    ident = project['id']
    # Snapshot remains valid after product metadata and image-list changes.
    client.patch(f'/api/products/{product["id"]}', json={'name': 'changed'})
    run_next()
    project = client.get(f'/api/projects/{ident}').json()
    assert project['status'] == 'draft' and len(project['slides']) == 4
    assert project['product_name'] == '旅行杯'
    ids = [s['id'] for s in project['slides']]
    assert client.post(f'/api/projects/{ident}/generate', json={}).status_code == 200
    assert client.post(f'/api/projects/{ident}/generate', json={'slide_ids': [ids[0]]}).status_code == 409
    for _ in range(4):
        run_next()
    project = client.get(f'/api/projects/{ident}').json()
    assert project['status'] == 'ready'
    url = project['slides'][0]['url']
    assert client.get(url).status_code == 200
    response = client.get(f'/api/projects/{ident}/export', params={'slide_ids': ids[0], 'include_bases': 'true'})
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {'01.jpg', 'bases/01.png', 'caption.txt', 'plan.json'}
    assert client.post(f'/api/projects/{ident}/slides/{ids[0]}/regenerate', json={'instruction': 'more light'}).status_code == 200
    run_next()
    project = client.get(f'/api/projects/{ident}').json()
    assert len(project['slides'][0]['versions']) == 2
    old = project['slides'][0]['versions'][0]['id']
    edited = client.patch(f'/api/projects/{ident}/slides/{ids[0]}', json={'title': '新文案', 'selected_version_id': old}).json()
    assert edited['slides'][0]['selected_version_id'] == old
    assert edited['slides'][0]['url'] != url
    assert len(edited['slides'][0]['versions']) == 2
    # No extra paid task created for editing copy.
    assert len(client.get('/api/tasks').json()) == 6
    assert client.delete(f'/api/projects/{ident}').status_code == 200
    assert client.get(f'/api/projects/{ident}').status_code == 404


def test_failure_recovery_and_retry(client, monkeypatch):
    monkeypatch.setattr(worker, 'plan_content', mock_plan)
    _, project = new_project(client)
    claimed = worker.claim_task({})
    worker.recover_interrupted()
    tasks = client.get('/api/tasks').json()
    assert tasks[0]['status'] == 'failed' and '中断' in tasks[0]['error']
    assert client.post(f'/api/tasks/{claimed[0]}/retry').status_code == 200
    assert client.post(f'/api/tasks/{claimed[0]}/retry').status_code == 409
    run_next()
    assert client.get(f'/api/projects/{project["id"]}').json()['status'] == 'draft'


def test_upload_validation_and_paths(client):
    product = client.post('/api/products', json={'name': 'valid'}).json()
    response = client.post(f'/api/products/{product["id"]}/images', files=[('files', ('fake.png', b'not an image', 'image/png'))])
    assert response.status_code == 400
    for path in ('products/../../.secret', 'products/../app.db', 'projects/../app.db', 'products/..\\app.db', 'products/.secret'):
        with pytest.raises(Exception):
            stored_file(path)
    assert client.get('/api/files/products/..%2Fapp.db').status_code == 400
    assert client.get('/api/files/projects/no-file.png').status_code == 404


def test_validation_errors_and_stale_task(client, monkeypatch):
    monkeypatch.setattr(worker, 'plan_content', mock_plan)
    product, project = new_project(client)
    assert client.patch(f'/api/products/{product["id"]}', json={'name': ''}).status_code == 422
    bad = {'base_url': 'https://[broken', 'model': 'x'}
    assert client.put('/api/settings', json={'analysis': bad, 'image': bad}).status_code == 400
    run_next()
    with transaction() as db:
        task = Task(id='stale', project_id=project['id'], slide_id='old-slide', type='image', status='failed', payload={})
        db.add(task)
    assert client.post('/api/tasks/stale/retry').status_code == 409
    assert client.patch(f'/api/projects/{project["id"]}', json={'slides': [None]}).status_code == 422
    assert client.post(f'/api/projects/{project["id"]}/generate', json={'slide_ids': 3}).status_code == 422


def test_migration_matches_model():
    # Validate the checked-in migration on a fresh isolated database.
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    Base.metadata.drop_all(engine)
    command.upgrade(config, 'head')
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
