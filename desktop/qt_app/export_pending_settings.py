"""A compact, non-sensitive summary of unsaved Qt export preferences."""
from __future__ import annotations

LABELS = {
    'export_recipe_csv': 'Recipe CSV',
    'export_report_txt': 'Conversion TXT',
    'export_validation_md': 'Validation MD',
    'native_project_template': 'Native template',
    'auto_open': 'Open after export',
    'output_application': 'Output slicer',
    'bambu_studio_executable': 'Bambu executable',
    'orcaslicer_executable': 'Orca executable',
    'source': 'Filament source',
    'custom': 'Custom library',
    'planner_mode': 'Planning effort',
    'quality_bias': 'Quality',
    'real_slots': 'Physical slots',
    'max_output_colors': 'Palette limit',
    'strategy': 'Palette base',
    'output_color_strategy': 'Color optimization',
}


def summarize_pending(preferences, *, maximum=3):
    """Show edited key names and meaningful safe values, not file paths."""
    keys = sorted(getattr(preferences, 'dirty_keys', ()))
    if not keys:
        return ''
    descriptions = []
    for key in keys[:maximum]:
        label = LABELS.get(key, key.replace('_', ' ').capitalize())
        value = preferences.get(key)
        if isinstance(value, bool):
            shown = 'On' if value else 'Off'
        elif key in ('native_project_template', 'custom',
                     'bambu_studio_executable', 'orcaslicer_executable'):
            shown = 'Selected' if value else 'Cleared'
        elif isinstance(value, (str, int, float)):
            shown = str(value)[:40]
        else:
            shown = 'Changed'
        descriptions.append(f'{label}: {shown}')
    remaining = len(keys) - len(descriptions)
    return ('Pending: ' + ' · '.join(descriptions)
            + (f' · +{remaining} more' if remaining > 0 else ''))
