"""Diagnose native/Qt exits after successful unittest output.

CI runs this only after the *normal* full suite fails. Every discovered test
module is executed in a child interpreter and its real process exit code is
recorded. This script never substitutes an OK result for a crashing child.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / 'tests'
OUT = ROOT / 'shutdown_diagnostics'
SUMMARY = re.compile(r'Ran (\d+) tests? in [\d.]+s')


def run_child(paths: list[str]) -> int:
    sys.path.insert(0, str(ROOT))
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in paths:
        suite.addTests(loader.discover(str(TESTS), pattern=name))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', nargs='*', default=None,
                        help=argparse.SUPPRESS)
    parser.add_argument('--group-size', type=int, default=1,
                        help='Modules per child process (default: 1)')
    parser.add_argument('--timeout', type=int, default=300,
                        help='Timeout for each child process, in seconds')
    options = parser.parse_args()
    if options.child is not None:
        return run_child(options.child)
    if options.group_size < 1 or options.timeout < 1:
        parser.error('group-size and timeout must be positive')

    files = sorted(p.name for p in TESTS.glob('test_*.py'))
    if not files:
        print('ERROR: No test modules found in tests/', flush=True)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    groups = [files[i:i + options.group_size]
              for i in range(0, len(files), options.group_size)]
    results = []
    total = 0
    print(f'Diagnosing {len(files)} modules in {len(groups)} child processes; '
          'native errors will remain failures.', flush=True)
    env = os.environ.copy()
    env['PYTHONFAULTHANDLER'] = '1'
    env['PYTHONUNBUFFERED'] = '1'
    for i, group in enumerate(groups, 1):
        label = '+'.join(n.removesuffix('.py') for n in group)
        log_path = OUT / f'group_{i:03}.log'
        command = [sys.executable, str(Path(__file__).resolve()),
                   '--child', *group]
        timed_out = False
        with log_path.open('w', encoding='utf-8', errors='replace') as log:
            try:
                process = subprocess.run(command, cwd=ROOT, env=env,
                                         stdout=log, stderr=subprocess.STDOUT,
                                         timeout=options.timeout, check=False)
                rc = process.returncode
            except subprocess.TimeoutExpired:
                timed_out, rc = True, None
                log.write('\nDIAGNOSTIC TIMEOUT\n')
        data = log_path.read_text(encoding='utf-8', errors='replace')
        m = list(SUMMARY.finditer(data))
        count = int(m[-1].group(1)) if m else 0
        total += count
        ok = rc == 0 and bool(m) and not timed_out
        result = {'modules': group, 'exit_code': rc, 'tests_reported': count,
                  'timed_out': timed_out, 'ok': ok, 'log': str(log_path.relative_to(ROOT))}
        results.append(result)
        print(f'[{i:03}/{len(groups):03}] {"PASS" if ok else "FAIL"} '
              f'exit={rc!s} tests={count:3} {label}', flush=True)
        if not ok:
            print('--- failing child log tail ---', flush=True)
            print('\n'.join(data.splitlines()[-36:]), flush=True)
            print('--- end child log ---', flush=True)

    (OUT / 'summary.json').write_text(
        json.dumps({'total_reported_tests': total, 'groups': results}, indent=2),
        encoding='utf-8')
    failed = [r for r in results if not r['ok']]
    print(f'Isolation summary: {len(failed)} / {len(results)} groups failed; '
          f'{total} test results reported.', flush=True)
    if failed:
        print('Native exit code(s) found; inspect attached group logs.', flush=True)
        return 1
    print('All isolated groups exited 0. If the combined suite still crashes, '
          'the bug likely requires shared cross-module interpreter/Qt state.',
          flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
