"""Describe whether an *opened source* requires a blank native 3MF template.

Match the engine's `find_project_settings` / `is_standard_colored_3mf`
distinction. UI guidance only: the engine remains the export authority.
No model contents are extracted, parsed, repaired or modified.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile


@dataclass(frozen=True)
class TemplateRequirement:
    kind: str
    required: bool
    description: str


def template_requirement(path: str | Path | None) -> TemplateRequirement:
    """Classify a source as native, generic, external, missing, or unreadable.

    Native = has slicer `project_settings.config`; generic = no such member.
    This uses only ZIP central-directory member names and safe metadata limits.
    """
    if not path:
        return TemplateRequirement('none', False,
                                   'Open a model to determine whether it needs a native template.')
    model = Path(path)
    extension = model.suffix.lower()
    if extension in ('.obj', '.glb'):
        return TemplateRequirement('external', True,
            'A blank slicer-saved 3MF template supplies the printer and process settings for this source.')
    if extension != '.3mf':
        return TemplateRequirement('unsupported', False,
                                   'This model format is not supported for native 3MF export.')
    try:
        with ZipFile(model) as archive:
            members = archive.infolist()
            if len(members) > 1500 or sum(i.file_size for i in members) > 1_000_000_000:
                raise ValueError('Archive exceeds the safe metadata inspection limits')
            native = any(i.filename.replace('\\', '/').lower().endswith('project_settings.config')
                         for i in members)
    except (BadZipFile, OSError, ValueError, OverflowError) as exc:
        return TemplateRequirement('unreadable', False,
                                   'Unable to inspect source 3MF: ' + str(exc))
    if native:
        return TemplateRequirement('native', False,
            'This native slicer 3MF already contains project settings. No additional template is needed.')
    return TemplateRequirement('generic', True,
        'This generic 3MF has no slicer project settings. Choose a blank slicer-saved 3MF template.')
