"""Host orchestration for the development environment. Subprocesses get argument arrays, never shell strings."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IMAGE = 'symfony-chrome-dev:local'
FIXTURE_IGNORE = shutil.ignore_patterns('vendor', 'var', 'node_modules', '.env.local', '.phpunit.cache')


def docker():
    executable = os.environ.get('DEV_DOCKER') or shutil.which('docker')
    if not executable:
        raise RuntimeError('Docker CLI missing. Install Docker Engine/Desktop with the Compose v2 plugin.')
    return executable


def run(args, log=None, check=True, **kwargs):
    if log:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        with Path(log).open('w') as output:
            return subprocess.run(args, stdout=output, stderr=subprocess.STDOUT, check=check, **kwargs)
    return subprocess.run(args, check=check, **kwargs)


def validate_id(run_id):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', run_id):
        raise ValueError(f'Invalid run id {run_id!r}: lowercase letters, digits and hyphens only')
    return run_id


def load(run_id='dev'):
    validate_id(run_id)
    marker = ROOT / 'workspaces' / run_id / 'run.json'
    if not marker.is_file():
        raise RuntimeError(f'Unknown run {run_id!r}; create it with ./bin/dev up --run {run_id}')
    data = json.loads(marker.read_text())
    if data['repository'] != str(ROOT) or data['run_id'] != run_id:
        raise RuntimeError('Workspace ownership marker does not match this checkout')
    return data


def prepare(run_id, port=0, app_env='dev'):
    validate_id(run_id)
    workspace = ROOT / 'workspaces' / run_id
    if workspace.exists():
        return load(run_id)
    workspace.mkdir(parents=True)
    shutil.copytree(ROOT / 'fixtures/app', workspace / 'app', ignore=FIXTURE_IGNORE)
    (workspace / 'state').mkdir()
    (ROOT / 'artifacts' / run_id).mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(ROOT).encode()).hexdigest()[:8]
    data = {'schema': 1, 'run_id': run_id, 'repository': str(ROOT),
            'project': f'symfony-chrome-{digest}-{run_id}', 'app': str(workspace / 'app'),
            'state': str(workspace / 'state'), 'evidence': str(ROOT / 'artifacts' / run_id),
            'port': port, 'app_env': app_env,
            'image': os.environ.get('DEV_IMAGE') or DEFAULT_IMAGE}
    (workspace / 'run.json').write_text(json.dumps(data, indent=2) + '\n')
    return data


def compose_files():
    files = ['-f', str(ROOT / 'compose.yaml')]
    if (ROOT / 'private').is_dir():
        files += ['-f', str(ROOT / 'compose.private.yaml')]
    return files


def compose(data, *args):
    return [docker(), 'compose', '--project-directory', str(ROOT), *compose_files(), '-p', data['project'], *args]


def environment(data):
    image = data.get('image') or DEFAULT_IMAGE
    override = os.environ.get('DEV_IMAGE')
    if override and override != image:
        raise ValueError(f'DEV_IMAGE differs from the image recorded for this run: {image}')
    return {**os.environ, 'DEV_APP': data['app'], 'DEV_STATE': data['state'], 'DEV_IMAGE': image,
            'DEV_EVIDENCE_DIR': data['evidence'], 'DEV_PORT': str(data['port']),
            'DEV_RUN_ID': data['run_id'], 'DEV_APP_ENV': data.get('app_env', 'dev'),
            'DEV_UID': str(os.getuid()), 'DEV_GID': str(os.getgid())}


def execute(data, *args, **kwargs):
    # exec would otherwise run as root; match the PUID/PGID the entrypoint gave the main process.
    user = f'{os.getuid()}:{os.getgid()}'
    return run(compose(data, 'exec', '-T', '--user', user, '-w', '/workspace', 'php', *args), env=environment(data), **kwargs)


def require_running(data):
    status = subprocess.run(compose(data, 'ps', '--status', 'running', '-q', 'php'),
                            env=environment(data), text=True, capture_output=True)
    if status.returncode or not status.stdout.strip():
        raise RuntimeError(f"Container is stopped. Start it with ./bin/dev up --run {data['run_id']}")


def host_port(data):
    out = subprocess.check_output(compose(data, 'port', 'php', '8000'), env=environment(data), text=True).strip()
    return out.rsplit(':', 1)[-1]


def start(data, build=False):
    env = environment(data)
    evidence = Path(data['evidence'])
    if build:
        run(compose(data, 'build'), env=env, log=evidence / 'build.log')
    run(compose(data, 'up', '-d', '--no-build'), env=env)
    execute(data, 'cat', '/opt/dev/image-identity.json', log=evidence / 'image-identity.json')
    execute(data, '/opt/dev/docker/setup', log=evidence / 'setup.log')
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        probe = execute(data, 'curl', '-fsS', '-o', '/dev/null', 'http://127.0.0.1:8000/_dev/ready',
                        check=False, capture_output=True)
        if probe.returncode == 0:
            return
        time.sleep(0.5)
    raise TimeoutError(f"Fixture HTTP readiness failed; inspect {evidence}/setup.log")


def stop(data, purge=False):
    run(compose(data, 'down', '--remove-orphans'), env=environment(data))
    if purge:
        load(data['run_id'])
        shutil.rmtree(ROOT / 'workspaces' / data['run_id'])
