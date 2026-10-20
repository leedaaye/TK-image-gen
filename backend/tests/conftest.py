import os
import tempfile
from pathlib import Path

# Isolate the complete suite from developer data and external services.
TEST_ROOT = Path(tempfile.mkdtemp(prefix='tk-studio-tests-'))
os.environ['DATA_DIR'] = str(TEST_ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///' + (TEST_ROOT / 'test.db').as_posix()
os.environ['SECRET_KEY'] = 'test-secret-key-for-isolated-tests-only-1234'
os.environ.pop('ADMIN_PASSWORD', None)
