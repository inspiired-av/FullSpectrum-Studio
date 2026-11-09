"""Run the FullSpectrum unittest suite without known, harmless offscreen-GL spam.

Usage from repository root:
    python -m tools.run_qt_tests_quiet
    python -m tools.run_qt_tests_quiet --pattern test_qt_intended_dimensions.py

Unlike QT_LOGGING_RULES='*.warning=false', this suppresses only a tiny
allowlist of messages. Other Qt failures and Python exceptions remain visible.
"""
from __future__ import annotations

import argparse
import os
import sys
import unittest
from collections import Counter

# The filter is intentionally pure Python to be unit-testable without Qt.
EXPECTED_OFFSCREEN_OPENGL_MESSAGES = frozenset((
    'This plugin does not support createPlatformOpenGLContext!',
    'QOpenGLWidget: Failed to create context',
    'QOpenGLWidget is not supported on this platform.',
))


def expected_offscreen_warning(message: str, platform: str | None) -> bool:
    """Filter only known context failures when the test is actually headless."""
    return (str(platform or '').lower() in ('offscreen', 'minimal')
            and str(message).strip() in EXPECTED_OFFSCREEN_OPENGL_MESSAGES)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pattern', default='test_*.py',
                        help='unittest discovery filename pattern')
    parser.add_argument('--start-directory', default='tests')
    parser.add_argument('--top-level-directory', default=None)
    parser.add_argument('--verbosity', '-v', type=int, default=2, choices=(0, 1, 2))
    parser.add_argument('--failfast', action='store_true')
    args = parser.parse_args(argv)

    # Preserve explicit Windows Qt platform settings. Several Qt tests
    # request offscreen themselves; the runner merely supplies a default.
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    platform = os.environ.get('QT_QPA_PLATFORM', '').lower()
    counts = Counter()
    previous = None
    qt_core = None
    try:
        from PySide6 import QtCore
        qt_core = QtCore
    except ImportError:
        print('PySide6 is unavailable: running non-Qt tests without Qt warning filtering.',
              file=sys.stderr)

    if qt_core is not None:
        def qt_message_handler(mode, context, message):
            if (mode == qt_core.QtMsgType.QtWarningMsg
                    and expected_offscreen_warning(message, platform)):
                counts[str(message).strip()] += 1
                return
            # Forward all other warnings, critical errors and fatal messages.
            if previous is not None:
                previous(mode, context, message)
            else:
                print(str(message), file=sys.stderr)
        previous = qt_core.qInstallMessageHandler(qt_message_handler)

    try:
        suite = unittest.defaultTestLoader.discover(
            start_dir=args.start_directory, pattern=args.pattern,
            top_level_dir=args.top_level_directory)
        result = unittest.TextTestRunner(
            verbosity=args.verbosity, failfast=args.failfast).run(suite)
    finally:
        if qt_core is not None:
            qt_core.qInstallMessageHandler(previous)
        if counts:
            print('\nFiltered %d known offscreen OpenGL-context warnings '
                  '(test output only):' % sum(counts.values()), file=sys.stderr)
            for message, count in sorted(counts.items()):
                print('  %dx %s' % (count, message), file=sys.stderr)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
