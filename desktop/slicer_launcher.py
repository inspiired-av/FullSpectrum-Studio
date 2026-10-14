"""Find installed slicers without relying on the .3mf file association.

The app launches a selected slicer with a project path argument. Keeping
lookup in this module makes it testable without starting a Tkinter window.
"""

import os
import shutil
from pathlib import Path


SLICER_EXECUTABLES = {
    "Bambu Studio": ("bambu-studio.exe", "BambuStudio.exe"),
    "OrcaSlicer": ("orca-slicer.exe", "OrcaSlicer.exe"),
}

SLICER_FOLDERS = {
    "Bambu Studio": ("Bambu Studio", "BambuStudio"),
    "OrcaSlicer": ("OrcaSlicer", "Orca Slicer"),
}


def windows_app_paths(executable_names):
    """Read Windows' registered App Paths for installed slicer executables."""
    try:
        import winreg
    except ImportError:
        return []

    found = []
    for name in executable_names:
        key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}"
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (0, winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view) as key:
                        raw = winreg.QueryValueEx(key, "")[0]
                except OSError:
                    continue
                if isinstance(raw, str) and raw.strip():
                    found.append(Path(os.path.expandvars(raw.strip().strip('"'))))
    return found


def windows_slicer_candidates(application, environ=None, registry_candidates=None, path_lookup=None):
    """Yield likely executables for a selected slicer, in priority order."""
    if application not in SLICER_EXECUTABLES:
        raise ValueError(f"Unsupported slicer {application!r}")
    env = os.environ if environ is None else environ
    names = SLICER_EXECUTABLES[application]
    folders = SLICER_FOLDERS[application]

    if registry_candidates is None:
        registry_candidates = windows_app_paths(names)
    yield from registry_candidates

    roots = [env.get("ProgramFiles"), env.get("ProgramW6432"), env.get("ProgramFiles(x86)")]
    local = env.get("LOCALAPPDATA")
    if local:
        roots.extend([str(Path(local) / "Programs"), local])
    for root in roots:
        if not root:
            continue
        for folder in folders:
            for name in names:
                yield Path(root) / folder / name

    lookup = shutil.which if path_lookup is None else path_lookup
    for name in names:
        location = lookup(name)
        if location:
            yield Path(location)


def find_windows_slicer(application, *, environ=None, registry_candidates=None, path_lookup=None):
    """Find a real executable; return None when user selection is needed."""
    seen = set()
    for candidate in windows_slicer_candidates(
        application, environ=environ,
        registry_candidates=registry_candidates, path_lookup=path_lookup,
    ):
        path = Path(candidate)
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            if path.is_file():
                return path
    return None
