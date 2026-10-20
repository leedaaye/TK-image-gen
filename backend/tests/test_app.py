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
    return {'title': 'Travel cup', 'caption': 'A cup for daily routines.', 'tags': ['#cup'], 'analysis': {'missing_information': ['capacity'], 'supported_facts': ['blue'], 'cautions': [], 'shared_visual_direction': 'Blue and white, editorial daylight'}, 'slides': [{'title': f'Cup {i}', 'body': 'A blue cup', 'prompt': f'An editorial blue cup image. Render EXACT headline "Cup {i}" and body "A blue cup" in high-contrast type.'} for i in range(4)]}


async def mock_refine(provider, product, project, slide, instruction, references, image_mode='reference'):
    return {'title': slide['title'], 'body': slide['body'], 'prompt': f'A refined editorial cup visual. Render EXACT text "{slide["title"]}" and "{slide["body"]}". Bright daylight.'}


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
    monkeypatch.setattr(worker, 'refine_slide_prompt', mock_refine)
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
        assert set(archive.namelist()) == {'01.jpg', 'originals/01.png', 'caption.txt', 'plan.json'}
    assert client.post(f'/api/projects/{ident}/slides/{ids[0]}/regenerate', json={'instruction': 'more light'}).status_code == 200
    run_next()
    project = client.get(f'/api/projects/{ident}').json()
    assert len(project['slides'][0]['versions']) == 2
    old = project['slides'][0]['versions'][0]['id']
    before_edit_url = project['slides'][0]['url']
    edited = client.patch(f'/api/projects/{ident}/slides/{ids[0]}', json={'title': '新文案'}).json()
    assert edited['slides'][0]['needs_regeneration']
    assert edited['slides'][0]['url'] == before_edit_url
    assert edited['status'] == 'draft'
    # Saving copy is free and does not alter pixels or create a task.
    assert len(client.get('/api/tasks').json()) == 6
    assert client.post(f'/api/projects/{ident}/generate', json={}).status_code == 200
    run_next()
    project = client.get(f'/api/projects/{ident}').json()
    assert project['slides'][0]['title'] == '新文案'
    assert len(project['slides'][0]['versions']) == 3
    restored = client.patch(f'/api/projects/{ident}/slides/{ids[0]}', json={'selected_version_id': old}).json()
    assert restored['slides'][0]['selected_version_id'] == old
    assert restored['slides'][0]['url'] == url
    assert restored['slides'][0]['title'] == 'Cup 0'
    assert not restored['slides'][0]['needs_regeneration']
    assert client.delete(f'/api/projects/{ident}').status_code == 200
    assert client.get(f'/api/projects/{ident}').status_code == 404


def test_native_prompt_is_sent_verbatim_and_pixels_are_not_overlaid(client, monkeypatch):
    monkeypatch.setattr(worker, 'plan_content', mock_plan)
    calls = []
    async def capture(provider, prompt, references):
        calls.append(prompt)
        return image_bytes()
    async def unexpected_refine(*args, **kwargs):
        raise AssertionError('A current planned prompt must be sent directly')
    monkeypatch.setattr(worker, 'generate_image', capture)
    monkeypatch.setattr(worker, 'refine_slide_prompt', unexpected_refine)
    _, project = new_project(client)
    run_next()
    project = client.get(f'/api/projects/{project["id"]}').json()
    slide = project['slides'][0]
    client.post(f'/api/projects/{project["id"]}/generate', json={'slide_ids': [slide['id']]})
    run_next()
    result = client.get(f'/api/projects/{project["id"]}').json()['slides'][0]
    assert calls == [slide['prompt']]
    version = result['versions'][0]
    assert version['render_mode'] == 'native_text'
    assert version['prompt'] == slide['prompt']
    from app.services import relative_url_path
    with Image.open(relative_url_path(version['base_url'])) as output:
        assert output.size == (320, 400)  # no forced crop or 1080x1440 overlay
        assert output.getpixel((160, 390)) == (127, 166, 176)
    with Image.open(relative_url_path(result['url'])) as output:
        assert output.size == (320, 400)
        assert max(abs(a-b) for a,b in zip(output.getpixel((160,390)), (127,166,176))) < 4


def test_legacy_upgrade_and_failed_image_retry_reuses_prepared_prompt(client, monkeypatch):
    monkeypatch.setattr(worker, 'plan_content', mock_plan)
    refinements = []
    async def refine(*args, **kwargs):
        refinements.append(args[3]['title'])
        return await mock_refine(*args, **kwargs)
    async def fail_image(*args, **kwargs):
        raise RuntimeError('simulated image failure')
    monkeypatch.setattr(worker, 'refine_slide_prompt', refine)
    monkeypatch.setattr(worker, 'generate_image', fail_image)
    _, project = new_project(client)
    run_next()
    with transaction() as db:
        doc = db.get(Document, project['id'])
        import copy
        data = copy.deepcopy(doc.data)
        slide = data['slides'][0]
        slide.pop('prompt_pipeline')
        slide['prompt_is_current'] = False
        slide['prompt'] = 'Legacy scene without any letters'
        slide_id = slide['id']
        doc.data = data
    client.post(f'/api/projects/{project["id"]}/generate', json={'slide_ids': [slide_id]})
    run_next()
    failed = next(t for t in client.get('/api/tasks').json() if t['type'] == 'image')
    assert failed['status'] == 'failed'
    assert len(refinements) == 1
    monkeypatch.setattr(worker, 'generate_image', mock_image)
    assert client.post(f'/api/tasks/{failed["id"]}/retry').status_code == 200
    run_next()
    assert len(refinements) == 1
    result = client.get(f'/api/projects/{project["id"]}').json()['slides'][0]
    assert result['status'] == 'ready' and result['versions'][0]['render_mode'] == 'native_text'


def test_empty_instruction_regenerate_refines_and_style_restore_stays_stale(client, monkeypatch):
    monkeypatch.setattr(worker, 'plan_content', mock_plan)
    monkeypatch.setattr(worker, 'generate_image', mock_image)
    refinements = []
    async def refine(*args, **kwargs):
        refinements.append(args[4])
        return await mock_refine(*args, **kwargs)
    monkeypatch.setattr(worker, 'refine_slide_prompt', refine)
    _, project = new_project(client)
    ident = project['id']
    run_next()
    slide = client.get(f'/api/projects/{ident}').json()['slides'][0]
    client.post(f'/api/projects/{ident}/generate', json={'slide_ids': [slide['id']]})
    run_next()
    original = client.get(f'/api/projects/{ident}').json()['slides'][0]['versions'][0]
    assert refinements == []
    client.post(f'/api/projects/{ident}/slides/{slide["id"]}/regenerate', json={'instruction': ''})
    run_next()
    assert refinements == ['']
    client.patch(f'/api/projects/{ident}', json={'style': 'dark editorial'})
    restored = client.patch(f'/api/projects/{ident}/slides/{slide["id"]}', json={'selected_version_id': original['id']}).json()
    assert restored['slides'][0]['url'] == original['url']
    assert restored['slides'][0]['prompt_is_current'] is False
    bad_slide = {k: slide[k] for k in ('id', 'title', 'body', 'prompt')}
    bad_slide['body'] = '   '
    assert client.patch(f'/api/projects/{ident}', json={'slides': [bad_slide]}).status_code == 422


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
