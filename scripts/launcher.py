"""Windows hidden launcher. Invoked with pythonw; all diagnostics go to logs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / 'logs'
LOGS.mkdir(exist_ok=True)
STATE = LOGS / 'processes.json'
PYTHON = ROOT / '.venv' / 'Scripts' / 'python.exe'
HIDDEN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def load_env():
    source = ROOT / '.env'
    if source.exists():
        for line in source.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def message(text, error=False):
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, 'TK 图文工作台', 0x10 if error else 0x40)
    else:
        print(text)


def healthy(url):
    try:
        with urllib.request.urlopen(url + '/api/health', timeout=2) as response:
            return json.load(response)
    except Exception:
        return None


def bootstrap(log):
    if not PYTHON.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv')], cwd=ROOT, stdout=log, stderr=log, creationflags=HIDDEN, check=True)
    subprocess.run([str(PYTHON), '-m', 'pip', 'install', '-r', str(ROOT / 'backend' / 'requirements.txt')], cwd=ROOT, stdout=log, stderr=log, creationflags=HIDDEN, check=True)
    node = os.getenv('TK_NODE', 'node')
    pnpm = os.getenv('TK_PNPM', '')
    if pnpm:
        command = [node, pnpm, 'install', '--frozen-lockfile']
        build = [node, pnpm, 'run', 'build']
    else:
        # npm.cmd needs cmd on Windows; no user-provided values are interpolated.
        command = ['cmd', '/c', 'npm install']
        build = ['cmd', '/c', 'npm run build']
    subprocess.run(command, cwd=ROOT / 'frontend', stdout=log, stderr=log, creationflags=HIDDEN, check=True)
    subprocess.run(build, cwd=ROOT / 'frontend', stdout=log, stderr=log, creationflags=HIDDEN, check=True)


def stop(quiet=False):
    if not STATE.exists():
        message('没有由启动器管理的运行进程。')
        return
    # Verify process command lines before stopping, to avoid PID reuse affecting other apps.
    state = json.loads(STATE.read_text(encoding='utf-8'))
    for process in state.get('processes', []):
        pid = int(process['pid'])
        escaped_root = str(ROOT).replace("'", "''")
        marker = process['marker']
        if marker not in ('app.main:app', 'app.worker'):
            raise RuntimeError('进程状态无效，请检查日志目录')
        script = f"$ErrorActionPreference='Stop'; $p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; if($p -and $p.ExecutablePath -like '{escaped_root}\\.venv\\*' -and $p.CommandLine -like '*{marker}*') {{ & taskkill.exe /PID {pid} /T /F; if($LASTEXITCODE -ne 0) {{ exit 1 }}; Wait-Process -Id {pid} -Timeout 10 -ErrorAction SilentlyContinue; if(Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 1 }} }}"
        subprocess.run(['powershell', '-NoProfile', '-Command', script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=HIDDEN, check=True)
    STATE.unlink(missing_ok=True)
    if not quiet:
        message('服务已停止。正在执行的任务将在下次启动时标记为中断，可确认后重试。')


def launcher_lock():
    handle = (LOGS / 'launcher.lock').open('a+b')
    handle.write(b'0')
    handle.flush()
    handle.seek(0)
    try:
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        message('启动或停止操作正在进行，请稍后再试。')
        return None
    return handle


def main():
    lock = launcher_lock()
    if lock is None:
        return
    parser = argparse.ArgumentParser()
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--setup', action='store_true')
    parser.add_argument('--rebuild', action='store_true')
    args = parser.parse_args()
    load_env()
    if args.stop:
        stop()
        return
    port = int(os.getenv('PORT', '8000'))
    url = f'http://127.0.0.1:{port}'
    health = healthy(url)
    if health and not args.setup and not args.rebuild:
        if not health.get('worker_alive'):
            message('网页服务正在运行，但 Worker 离线。请先停止服务后重新启动；详见日志。', True)
        webbrowser.open(url)
        return
    if health and (args.setup or args.rebuild):
        raise RuntimeError('请先停止正在运行的服务，再执行初始化或重新构建')
    if STATE.exists():
        # An earlier API may have exited while its worker survived: stop verified
        # managed processes before replacing their state, preserving PID safety.
        stop(quiet=True)
    with (LOGS / 'launcher.log').open('a', encoding='utf-8') as log:
        if args.setup or args.rebuild or not PYTHON.exists() or not (ROOT / 'frontend' / 'dist' / 'index.html').exists():
            bootstrap(log)
        subprocess.run([str(PYTHON), '-m', 'alembic', '-c', 'alembic.ini', 'upgrade', 'head'], cwd=ROOT / 'backend', stdout=log, stderr=log, creationflags=HIDDEN, check=True)
        processes = []
        children = []
        for marker, command in [('app.main:app', [str(PYTHON), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)]), ('app.worker', [str(PYTHON), '-m', 'app.worker'])]:
            target = (LOGS / ('api.log' if marker == 'app.main:app' else 'worker.log')).open('a', encoding='utf-8')
            process = subprocess.Popen(command, cwd=ROOT / 'backend', stdout=target, stderr=target, creationflags=HIDDEN)
            target.close()
            children.append(process)
            processes.append({'pid': process.pid, 'marker': marker})
            STATE.write_text(json.dumps({'processes': processes}), encoding='utf-8')
        for _ in range(90):
            if any(child.poll() is not None for child in children):
                stop(quiet=True)
                raise RuntimeError('API 或 Worker 意外退出，请查看 logs 中日志')
            status = healthy(url)
            if status and status.get('worker_alive'):
                webbrowser.open(url)
                return
            time.sleep(0.5)
        stop(quiet=True)
        raise RuntimeError('服务未在45秒内就绪，请查看 logs/api.log 和 logs/worker.log')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        import traceback
        with (LOGS / 'launcher.log').open('a', encoding='utf-8') as log:
            traceback.print_exc(file=log)
        message(f'启动失败：{exc}\n\n日志目录：{LOGS}', True)
