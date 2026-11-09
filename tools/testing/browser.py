#!/usr/bin/env python3
"""Real owned Chrome MCP, request/profile correlation, and browser guard contracts."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/integration'))
from contracts import Checks, correlation, workspace
from browser_report import verify as verify_browser_report
from protocol import StdioClient, text_of
sys.path.insert(0, str(ROOT / 'bin'))
from devlib import environment, execute


def chrome_processes(data):
    script = """import json,pathlib
found=[]
for path in pathlib.Path('/proc').iterdir():
 if not path.name.isdigit(): continue
 try: args=(path/'cmdline').read_bytes().split(b'\\0')
 except (FileNotFoundError,PermissionError,ProcessLookupError): continue
 if args and args[0].rsplit(b'/',1)[-1] in (b'chrome',b'chrome_crashpad_handler'): found.append(int(path.name))
print(json.dumps(sorted(found)))
"""
    return set(json.loads(execute(data, 'python3', '-c', script, capture_output=True, text=True).stdout))


def chrome(data, evidence):
    before = chrome_processes(data)
    command = [str(ROOT / 'bin/chrome-mcp'), '--run', data['run_id'], '--chromeArg=--no-sandbox']
    with StdioClient(command, Path(evidence) / 'chrome-mcp', timeout=90, env={**environment(data), 'CI': '1'}) as client:
        identity = client.initialize()
        listing = client.request('tools/list')['result']['tools']
        names = {row['name'] for row in listing}
        assert {'list_pages', 'navigate_page', 'take_snapshot'} <= names, 'Missing Chrome MCP tools'
        pages = text_of(client.call('list_pages', {}))
        assert pages, 'No page listing'
        text_of(client.call('navigate_page', {'type': 'url', 'url': 'http://127.0.0.1:8000/_ci/browser'}))
        snapshot = text_of(client.call('take_snapshot', {}))
        assert 'Symfony Chrome contract' in snapshot and 'Local action' in snapshot, snapshot
        failure = client.call('navigate_page', {'type': 'not-a-navigation-mode'})
        assert 'error' in failure or failure.get('result', {}).get('isError') is True, 'Invalid invocation was not rejected'
    state = json.loads((Path(evidence) / 'chrome-mcp/transport.json').read_text())
    assert state['closed'] is True
    deadline = time.monotonic() + 10
    while chrome_processes(data) != before and time.monotonic() < deadline:
        time.sleep(0.1)
    after = chrome_processes(data)
    assert after == before, 'Owned Chrome process survived transport cleanup: ' + str(after - before)
    (Path(evidence) / 'owned-processes.json').write_text(json.dumps({'before': sorted(before), 'after': sorted(after)}))
    (Path(evidence) / 'chrome-identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    return 'Real MCP initialization, discovery, page/navigation/snapshot and invalid-schema response; owned browser process cleanup observed', 7



def borrowed(data, evidence):
    # The fixture owner launches Chrome independently; the MCP connection borrows it.
    script = """import json,subprocess,tempfile
profile=tempfile.mkdtemp(prefix='symfony-chrome-borrowed-')
p=subprocess.Popen(['/usr/local/bin/chrome','--headless=new','--no-sandbox','--remote-debugging-port=9222','--remote-debugging-address=127.0.0.1','--user-data-dir='+profile,'about:blank'],start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print(json.dumps({'pid':p.pid,'profile':profile}))
"""
    before = chrome_processes(data)
    owner = json.loads(execute(data, 'python3', '-c', script, capture_output=True, text=True).stdout)
    primary = None
    owner['cleanup'] = 'pending'
    def endpoint():
        return execute(data, 'curl', '-fsS', '--max-time', '2', 'http://127.0.0.1:9222/json/version', check=False, capture_output=True)
    try:
        deadline = time.monotonic() + 30
        while endpoint().returncode and time.monotonic() < deadline:
            time.sleep(0.1)
        assert endpoint().returncode == 0, 'Controlled externally owned browser did not start'
        assert owner['pid'] in chrome_processes(data), 'External owner process identity not observed'
        from devlib import exec_command
        command = exec_command(data, 'chrome-devtools-mcp', '--browserUrl=http://127.0.0.1:9222',
                               '--no-usage-statistics', '--no-performance-crux')
        with StdioClient(command, Path(evidence) / 'borrowed-mcp', timeout=90, env={**environment(data), 'CI': '1'}) as client:
            client.initialize()
            assert text_of(client.call('list_pages', {})), 'Borrowed endpoint has no page'
            text_of(client.call('navigate_page', {'type':'url','url':'http://127.0.0.1:8000/_ci/browser'}))
            assert 'Symfony Chrome contract' in text_of(client.call('take_snapshot', {}))
        assert endpoint().returncode == 0 and owner['pid'] in chrome_processes(data), 'MCP detach closed the borrowed browser'
        owner['alive_after_detach'] = True
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            cleanup = "import os,signal,pathlib; p=pathlib.Path('/proc/" + str(owner['pid']) + "/cmdline'); args=p.read_bytes() if p.exists() else b''; expected=" + repr(owner['profile'].encode()) + "; assert not args or expected in args, 'Owner process identity changed'; os.killpg(" + str(owner['pid']) + ",signal.SIGTERM) if args else None"
            response = execute(data, 'python3', '-c', cleanup, check=False, capture_output=True)
            assert response.returncode == 0, 'Borrowed owner cleanup failed: ' + response.stderr.decode()[-1000:]
            deadline = time.monotonic() + 10
            while chrome_processes(data) != before and time.monotonic() < deadline:
                time.sleep(0.1)
            assert chrome_processes(data) == before, 'Externally owned Chrome resources survived owner cleanup'
            execute(data, 'python3', '-c', 'import shutil;shutil.rmtree(' + repr(owner['profile']) + ',ignore_errors=True)')
            owner['cleanup'] = 'passed'
        except Exception as exc:
            owner.update(cleanup='error', cleanup_error=str(exc))
            if primary is None:
                raise
            primary.add_note('Borrowed owner cleanup also failed: ' + str(exc))
        finally:
            (Path(evidence) / 'borrowed-owner.json').write_text(json.dumps(owner, indent=2))
    return 'Independently owned Chrome remains alive after real MCP attach, navigation, snapshot and detach', 5


def playwright(data, evidence):
    target = Path(data['app']) / '.ci/browser'
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'tests/browser', target / 'tests/browser', dirs_exist_ok=True)
    for name in ('package.json', 'package-lock.json'):
        shutil.copy2(ROOT / name, target / name)
    install = execute(data, 'npm', 'ci', '--prefix', '/workspace/.ci/browser', '--ignore-scripts', '--no-audit', '--no-fund',
                      check=False, capture_output=True)
    (Path(evidence) / 'npm-install.log').write_bytes(install.stdout + install.stderr)
    assert install.returncode == 0, 'Locked browser test dependency installation failed'
    discovery = execute(data, 'env', 'CONTRACT_URL=http://127.0.0.1:8000', 'npm', '--prefix', '/workspace/.ci/browser', 'run', '--silent', 'test:browser', '--', '--list', '--reporter=json', check=False, capture_output=True)
    assert discovery.returncode == 0, 'Native browser test discovery failed'
    plan = json.loads(discovery.stdout)
    (Path(evidence) / 'playwright-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    native = execute(data, 'env', 'CI=1', 'CONTRACT_URL=http://127.0.0.1:8000',
                     'CHROME_PATH=/usr/local/bin/chrome', 'CONTRACT_RESULTS=/workspace/.ci/browser/results',
                     'npm', '--prefix', '/workspace/.ci/browser', 'run', 'test:browser',
                     check=False, capture_output=True)
    (Path(evidence) / 'playwright.log').write_bytes(native.stdout + native.stderr)
    results = target / 'results'
    if results.exists():
        shutil.copytree(results, Path(evidence) / 'playwright', dirs_exist_ok=True)
    assert native.returncode == 0, 'Playwright browser guards failed; inspect native report'
    report = json.loads((results / 'results.json').read_text())
    count = verify_browser_report(plan, report)
    return 'Real Chrome input/client-only action and five independent browser error controls; exact native identities and attempts verified', count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--contract', choices=['browser.chrome-mcp', 'browser.borrowed-endpoint', 'browser.request-profile', 'browser.guards'], help='Run one named contract in a fresh owned workspace')
    args = parser.parse_args()
    checks = Checks(args.evidence)
    try:
        with workspace() as data:
            checks.context.update(workspace_run_id=data['run_id'], native_evidence=data['evidence'])
            if args.contract in (None, 'browser.chrome-mcp'):
                checks.check('browser.chrome-mcp', lambda: chrome(data, args.evidence))
            if args.contract in (None, 'browser.borrowed-endpoint'):
                checks.check('browser.borrowed-endpoint', lambda: borrowed(data, args.evidence))
            if args.contract in (None, 'browser.request-profile'):
                checks.check('browser.request-profile', lambda: correlation(data, args.evidence))
            if args.contract in (None, 'browser.guards'):
                checks.check('browser.guards', lambda: playwright(data, args.evidence))
    except Exception as exc:
        checks.rows.append({'id': 'browser.environment', 'outcome': 'error', 'assertions': 0,
                            'detail': type(exc).__name__ + ': ' + str(exc)[-4000:]})
    checks.save(capability_scope={'requested_mode': 'owned_and_controlled_borrowed_endpoint', 'host_auto_connect': 'not_executed',
                                 'package_correlation_api': 'not_implemented',
                                 'package_session_api': 'not_implemented'})
    return checks.exit()


if __name__ == '__main__':
    raise SystemExit(main())
