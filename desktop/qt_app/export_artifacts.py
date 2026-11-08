"""Selection of optional user-visible export artifacts; never gates validation.

The converter must generate and validate its full internal output in staging.
Only the final transactional publisher consults this selection.
"""
from __future__ import annotations

OPTIONAL_ARTIFACTS = ('csv', 'report', 'colorValidationReport')
ALL_ARTIFACTS = OPTIONAL_ARTIFACTS + ('output',)
SETTING_KEYS = (
    ('csv', 'export_recipe_csv'),
    ('report', 'export_report_txt'),
    ('colorValidationReport', 'export_validation_md'),
)


def chosen_diagnostics(preferences):
    """Snapshot three saved booleans; older callers default to all reports."""
    selected = []
    for artifact, preference in SETTING_KEYS:
        try:
            value = preferences.get(preference)
        except KeyError:
            value = True
        if value is not False:  # tolerate pre-feature test doubles returning None
            selected.append(artifact)
    return tuple(selected)


def publication_keys(diagnostics=OPTIONAL_ARTIFACTS):
    """Validate selection before export; 3MF is always mandatory and last."""
    if not isinstance(diagnostics, (tuple, list)):
        raise ValueError('Optional export artifact selection must be a sequence')
    if (any(type(name) is not str for name in diagnostics) or
            len(diagnostics) != len(set(diagnostics)) or
            any(name not in OPTIONAL_ARTIFACTS for name in diagnostics)):
        raise ValueError('Unknown or repeated optional export artifact')
    return tuple(key for key in ALL_ARTIFACTS if key == 'output' or key in diagnostics)
