#!/usr/bin/env python3
"""Check the selected released parent with xorder's pinned support checker."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_LIMIT = 2 * 1024 * 1024


def selected_base(root: Path) -> tuple[str, str, str]:
    """Bind the checked released resource to the actual Dockerfile parent pin."""
    toolchain = json.loads((root / 'toolchain.lock.json').read_text())
    revision = toolchain['xorder_support']['source_rev']
    if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('xorder_support.source_rev must pin a full source commit')
    image = toolchain['images']['base']
    reference, separator, digest = image.partition('@')
    if not separator or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('The released base must be selected by digest')
    repository = reference.rsplit(':', 1)[0] if ':' in reference.rsplit('/', 1)[-1] else reference
    lock = json.loads((root / 'xorder-support.lock.json').read_text())
    resources = lock.get('resources')
    if not isinstance(resources, list) or len(resources) != 1:
        raise ValueError('The overlay support lock must select exactly its released parent')
    resource = resources[0]
    if not isinstance(resource, dict):
        raise ValueError('The support-lock resource must be an object')
    service = resource.get('service') or resource.get('line_id')
    if not service or resource.get('identity') != repository + '@' + digest:
        raise ValueError('The support lock does not select the configured released parent')
    final_from = [line for line in (root / 'Dockerfile').read_text().splitlines()
                  if re.match(r'^\s*FROM\s+', line, re.IGNORECASE)]
    match = re.fullmatch(r'\s*FROM(?:\s+--platform=\S+)?\s+(\S+)(?:\s+AS\s+\S+)?\s*',
                         final_from[-1] if final_from else '', re.IGNORECASE)
    if not match or match.group(1) != image:
        raise ValueError('The final Dockerfile FROM does not match the configured released parent')
    return revision, image, service


def native(argv: list[str], evidence: Path, name: str, *, cwd: Path | None = None,
           timeout: int = 120) -> tuple[int, str]:
    """Retain bounded native output and terminate the owned process group on failure."""
    outputs = {'stdout': bytearray(), 'stderr': bytearray()}
    process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
    selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
    deadline = time.monotonic() + timeout
    failure = None
    try:
        while selector.get_map():
            if time.monotonic() >= deadline:
                raise TimeoutError(f'{name} exceeded {timeout} seconds')
            for key, _ in selector.select(0.2):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                output = outputs[key.data]
                output.extend(chunk[:max(0, OUTPUT_LIMIT - len(output))])
                if len(output) >= OUTPUT_LIMIT:
                    raise ValueError(f'{name} output exceeded the {OUTPUT_LIMIT}-byte limit')
        code = process.wait(timeout=max(1, deadline - time.monotonic()))
    except BaseException as exc:
        failure = exc
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        # The leader can exit while a descendant retains its pipes. Kill the
        # owned group even when the original process has already terminated.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        code = process.returncode
    finally:
        # A successful leader can still leave background descendants whose
        # standard streams were redirected. Their lifetime belongs to this call.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                break
        selector.close()
        process.stdout.close()
        process.stderr.close()
        for stream, content in outputs.items():
            (evidence / f'{name}.{stream}.log').write_bytes(content)
    if failure is not None:
        raise failure
    return code, outputs['stdout'].decode('utf-8', errors='replace')


def verify_checkout(checkout: Path, revision: str, evidence: Path) -> None:
    code, head = native(['git', 'rev-parse', 'HEAD'], evidence, 'checker-head', cwd=checkout)
    if code or head.strip() != revision:
        raise ValueError('The xorder checker checkout does not match its pinned source revision')
    code, status = native(['git', 'status', '--porcelain', '--untracked-files=all', '--ignored'], evidence,
                          'checker-status', cwd=checkout)
    if code or status.strip():
        raise ValueError('The xorder checker checkout has modified or untracked source')
    if not (checkout / 'scripts/xorder/downstream.py').is_file():
        raise ValueError('The selected xorder checkout lacks its stdlib support checker')


def acquire_checker(root: Path, revision: str, evidence: Path,
                    selected: Path | None = None) -> Path:
    checkout = selected or root / 'workspaces/xorder-checker' / revision
    if not checkout.exists():
        if selected is not None:
            raise ValueError('The explicitly selected xorder checkout does not exist')
        checkout.parent.mkdir(parents=True, exist_ok=True)
        # A failed download must not leave a directory that looks like a usable
        # persistent checkout on the next invocation.
        with tempfile.TemporaryDirectory(prefix='partial-', dir=checkout.parent) as temporary:
            staging = Path(temporary)
            for name, command in [
                ('checker-init', ['git', 'init', '--quiet']),
                ('checker-origin', ['git', 'remote', 'add', 'origin', 'https://github.com/xormania/xorder.git']),
                ('checker-fetch', ['git', 'fetch', '--quiet', '--depth', '1', 'origin', revision]),
                ('checker-checkout', ['git', 'checkout', '--quiet', '--detach', 'FETCH_HEAD']),
            ]:
                code, _ = native(command, evidence, name, cwd=staging)
                if code:
                    raise RuntimeError(f'{name} failed with exit {code}; inspect its retained logs')
            verify_checkout(staging, revision, evidence)
            try:
                staging.rename(checkout)
            except FileExistsError:
                # Another caller may have prepared the same immutable source.
                verify_checkout(checkout, revision, evidence)
    verify_checkout(checkout, revision, evidence)
    return checkout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--xorder-root', type=Path)
    parser.add_argument('--no-pull', action='store_true', help='Inspect an already pulled released parent')
    parser.add_argument('--policy-file', type=Path, help='Explicit fresh xorder support-fetch snapshot')
    args = parser.parse_args(argv)
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    checks = []
    metadata = {}
    code = 2
    try:
        revision, image, service = selected_base(ROOT)
        metadata.update(checker_revision=revision, selected_parent=image)
        checkout = acquire_checker(ROOT, revision, evidence, args.xorder_root)
        checks.append({'id': 'support.checker-source', 'outcome': 'passed', 'assertions': 2,
                       'detail': 'Pinned xorder source and clean checkout verified'})
        checker = checkout / 'scripts/xorder/downstream.py'
        policy = args.policy_file.resolve() if args.policy_file else evidence / 'support-policy.json'
        if not args.policy_file:
            # Fetch and then check through the upstream CLI. At this source pin,
            # the combined online path samples its comparison clock before the
            # fetch and rejects the newer receipt it creates itself.
            result, _ = native([sys.executable, '-B', str(checker), 'fetch', '--output', str(policy)],
                               evidence, 'policy-fetch', timeout=120)
            if result:
                raise RuntimeError(f'Current xorder policy acquisition failed with exit {result}')
        metadata['policy_mode'] = 'explicit_snapshot' if args.policy_file else 'fresh_fetch_snapshot'
        if not args.no_pull:
            result, _ = native(['docker', 'pull', image], evidence, 'parent-pull', timeout=600)
            if result:
                raise RuntimeError(f'Parent pull failed with exit {result}')
        command = [sys.executable, '-B', str(checker), 'check',
                   '--lock', str(ROOT / 'xorder-support.lock.json'), '--image', service + '=' + image,
                   '--policy-file', str(policy)]
        result, output = native(command, evidence, 'support-check', timeout=120)
        payload = json.loads(output)
        (evidence / 'support-result.json').write_text(json.dumps(payload, indent=2) + '\n')
        metadata['native_exit'] = result
        if result or payload.get('ok') is not True:
            raise RuntimeError(f"xorder support check failed: {payload.get('reason') or payload.get('code') or result}")
        if not isinstance(payload.get('observed'), list) or len(payload['observed']) != 1:
            raise ValueError('The support check did not retain one actual parent-image observation')
        checks.append({'id': 'support.current-policy-and-actual-parent', 'outcome': 'passed',
                       'assertions': 3, 'detail': payload.get('status', 'supported')})
        code = 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        checks.append({'id': 'support.current-policy-and-actual-parent', 'outcome': 'error',
                       'assertions': 0, 'detail': str(exc)})
    (evidence / 'checks.json').write_text(json.dumps({'schema': 1, 'checks': checks,
                                                   'metadata': metadata}, indent=2) + '\n')
    print(json.dumps({'suite': 'support', 'exit': code, 'checks': checks}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
