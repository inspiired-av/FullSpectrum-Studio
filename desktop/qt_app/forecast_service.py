"""Stage 4A: read-only source inspection and native FullSpectrum plan forecasts.

This module never writes a conversion 3MF, changes preferences, or invents metrics.
Work is performed by ForecastWorker off the Qt GUI thread.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from desktop.app_support import plan_forecast


@dataclass(frozen=True)
class ForecastRequest:
    model: str
    reference: str | None
    settings: dict
    disabled: frozenset[str]
    pinned: frozenset[str]
    protections: tuple[tuple[str, str], ...]


def make_request(model, reference, preferences, filament_preferences):
    """Snapshot the UI state, including unsaved edits, before starting a worker."""
    keys = ('strategy', 'source', 'custom', 'real_slots', 'quality_bias',
            'smart_quality', 'catalog_region', 'planner_mode', 'planning_sample',
            'max_output_colors', 'output_color_strategy', 'native_project_template')
    return ForecastRequest(
        model=str(model or ''), reference=str(reference or '') or None,
        settings={key: preferences.get(key) for key in keys},
        disabled=frozenset(filament_preferences.disabled),
        pinned=frozenset(filament_preferences.pinned),
        protections=tuple(sorted(filament_preferences.solid_assignments.items())),
    )


def inspect_model(model, engine=None):
    """Inspect the project palette without generating a preview or new output."""
    if engine is None:
        import fullspectrum_engine as engine
    path = Path(model)
    if not path.is_file():
        raise ValueError('Model file does not exist.')
    if path.suffix.lower() != '.3mf':
        return {'sourceSlots': None, 'note': 'Geometry-only inspection for OBJ/GLB.'}
    result = engine.inspect_project(path, metadata_only=True)
    return {'sourceSlots': result.get('sourceSlots'),
            'sourceColors': list(result.get('sourceColors') or []),
            'note': 'Read-only project inspection.'}


def _available_keys(engine, source, custom):
    """Use the same source-specific option normalizer as the Tkinter frontend."""
    from desktop.filament_options import selectable_filament_options
    inventory = None
    if source in ('inventory', 'catalog', 'all-bambu'):
        inventory = engine.read_bambu_inventory(required=False, minimum_colors=0)
    return selectable_filament_options(engine, source, inventory, custom)


def run_plan(request: ForecastRequest, engine=None, options_loader=None, progress=None):
    """Run the EXISTING optimizer strictly in plan-only mode.

    Directory scaffolding lives in an auto-cleaned temporary directory. No
    3MF, report, or settings are written to the user's source or Downloads.
    """
    if engine is None:
        import fullspectrum_engine as engine
    if progress is None:
        progress = lambda fraction, message: None
    path = Path(request.model)
    if not path.is_file() or path.suffix.lower() not in ('.3mf', '.obj', '.glb'):
        raise ValueError('Open an existing 3MF, OBJ, or GLB model first.')
    s = request.settings
    source = s['source']
    custom = s.get('custom') or None
    if source == 'custom' and (not custom or not Path(custom).is_file()):
        raise ValueError('Select a valid custom filament JSON library under Filaments.')
    if s['strategy'] == 'cmykw' and request.protections:
        raise ValueError('CMYKW cannot be combined with protected solid colors. Choose Bambu PLA or remove protection.')
    standard = path.suffix.lower() == '.3mf' and engine.is_standard_colored_3mf(path)
    if request.protections and not standard:
        raise ValueError('The existing optimizer only supports protected color assignments on standard material-colored 3MFs. Native-project protections are not passed to planning yet.')
    loader = options_loader or _available_keys
    options = loader(engine, source, custom) or []
    available = {str(option['key']) for option in options}
    enabled = available - request.disabled
    pinned = sorted(request.pinned & enabled)
    protected = dict(request.protections)
    for key in protected.values():
        if key not in enabled:
            raise ValueError('A protected source color targets a filament that is not enabled in the selected source.')
    if source != 'exact-cmykw' and len({str(o.get('color', '')).upper() for o in options if o['key'] in enabled}) < 2:
        raise ValueError('Enable at least two distinct available filament colors before forecasting.')
    bias = 'auto' if s['smart_quality'] else s['quality_bias']
    with TemporaryDirectory(prefix='fullspectrum_qt_forecast_') as workdir:
        output = engine.convert(
            path, s['strategy'], palette_source=source,
            output_dir=workdir, reveal=False, real_slots=s['real_slots'],
            direct_source_colors=standard,
            output_color_strategy=s['output_color_strategy'],
            max_output_colors=s['max_output_colors'], reference=request.reference,
            custom_catalog_path=custom, native_template_path=s.get('native_project_template') or None,
            quality_bias=bias, catalog_region=s['catalog_region'],
            planner_mode=s['planner_mode'], planning_sample=s['planning_sample'],
            mix_model='bambu', plan_only=True,
            allowed_anchor_keys=sorted(enabled) if request.disabled else None,
            pinned_anchor_keys=pinned, solid_color_overrides=protected,
            analysis_dir=None, progress=progress,
        )
    if output.get('type') != 'planPreview':
        raise RuntimeError('Engine returned a conversion result instead of a read-only plan preview.')
    forecast = plan_forecast(output)
    return {
        'forecast': forecast,
        'quality': dict(output.get('quality') or {}),
        'sourceSlots': output.get('sourceSlots'),
        'realSlots': output.get('realSlots'),
        'outputSlots': output.get('outputSlots'),
        'warnings': list(output.get('warnings') or []),
        'plannerMode': output.get('plannerMode'),
    }
