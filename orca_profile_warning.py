"""Non-blocking H2C / OrcaSlicer native-template compatibility guidance.

The selected EXE may differ from the program that saved the .3mf.  This module
never guesses its version, and never prevents the user using a nightly build.
"""
import re


def orca_h2c_warning(template_info, target_slicer):
    """Return relevant warning text or an empty string for the template/target pair."""
    if not isinstance(template_info, dict):
        return ""
    source = str(template_info.get('slicer') or '').strip()
    printer = str(template_info.get('printerPreset') or '')
    version = str(template_info.get('slicerVersion') or '')
    h2c = bool(re.search(r'\bH2C\b', printer, re.I))
    target = str(target_slicer or '').strip()
    warnings = []
    if source in ('Bambu Studio', 'OrcaSlicer') and target in ('Bambu Studio', 'OrcaSlicer') and source != target:
        warnings.append(f'Template was saved by {source}, but output opens in {target}. Prefer a template saved by the selected slicer.')
    if h2c and (source == 'OrcaSlicer' or target == 'OrcaSlicer'):
        warnings.append(
            'OrcaSlicer H2C needs a compatible 2.5.0-generation build (including supported dev/nightly builds). '
            'Older versions can discard H2C printer settings. Select the intended portable/nightly EXE and verify the H2C profile after opening.'
        )
        found = re.search(r'(\d+)\.(\d+)\.(\d+)', version)
        if source == 'OrcaSlicer' and found and tuple(map(int, found.groups())) < (2, 5, 0):
            warnings.append(f'Template identifies OrcaSlicer {version}, older than 2.5.0. Create a new H2C template with a compatible build.')
    return '  '.join(warnings)
