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
    # OrcaSlicer 2.5.0 officially supports H2C. A template's recorded
    # version is NOT the installed launcher version: warn only about a known
    # outdated H2C/Orca template. 2.5.0-alpha/RC share that generation.
    if h2c and source == 'OrcaSlicer' and target == 'OrcaSlicer':
        found = re.search(r'(\d+)\.(\d+)\.(\d+)', version)
        if found and tuple(map(int, found.groups())) < (2, 5, 0):
            warnings.append(
                f'This H2C template was saved by OrcaSlicer {version} (older than 2.5.0). '
                'Re-save the H2C project with OrcaSlicer 2.5.0 or newer and '
                'check that its printer profile is preserved.'
            )
    return '  '.join(warnings)
