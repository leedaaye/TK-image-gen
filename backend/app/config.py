import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv('DATA_DIR', str(ROOT / 'data'))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{(DATA / "app.db").as_posix()}')
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
SESSION_DAYS = 7

def installation_secret() -> str:
    configured = os.getenv('SECRET_KEY')
    if configured:
        if len(configured) < 32:
            raise RuntimeError('SECRET_KEY 至少需要32个字符')
        return configured
    target = DATA / '.secret'
    if not target.exists():
        import secrets
        # Publish a fully written secret atomically; readers never observe empty data.
        temporary = DATA / ('.secret-' + secrets.token_hex(12))
        temporary.write_text(secrets.token_urlsafe(48), encoding='utf-8')
        temporary.chmod(0o600)
        try:
            os.link(temporary, target)
        except FileExistsError:
            pass
        finally:
            temporary.unlink(missing_ok=True)
    result = target.read_text(encoding='utf-8').strip()
    if len(result) < 32:
        raise RuntimeError('本机密钥文件无效，请恢复 data/.secret 备份')
    return result

SECRET_KEY = installation_secret()
