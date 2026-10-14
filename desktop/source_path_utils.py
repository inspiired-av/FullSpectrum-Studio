"""Compare user-selected source paths across native and Tk path spellings.

On Windows, Tk may supply C:/... even though pathlib renders C:\\....
String equality therefore falsely invalidates asynchronous GUI results.
"""
from pathlib import Path, PureWindowsPath


def same_source_path(first, second):
    """Return whether two nonempty path spellings name the same selected path.

    Do not access the file system for Windows drive/UNC paths: a GUI callback
    only needs lexical equality, and the selected file may have moved already.
    """
    if first is None or second is None:
        return False
    left, right = str(first), str(second)
    if not left or not right:
        return False
    win_left, win_right = PureWindowsPath(left), PureWindowsPath(right)
    if win_left.drive and win_right.drive:
        return win_left == win_right
    try:
        return Path(left).expanduser().resolve(strict=False) == Path(right).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return False
