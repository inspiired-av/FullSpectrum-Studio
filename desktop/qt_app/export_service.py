"""Stage 4D-C: reuse the established converter, validate, then publish atomically.

Pure Python: no Qt widgets, modified model geometry or independent optimizer.
Forecast remains the read-only plan_only=True workflow in forecast_service.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, BadZipFile
import os
import shutil
import math

from desktop.qt_app.forecast_service import ForecastRequest, _available_keys

ARTIFACT_KEYS = ('csv', 'report', 'colorValidationReport', 'output')  # publish 3MF last
VALID_SLICERS = ('Bambu Studio', 'OrcaSlicer')


@dataclass(frozen=True)
class ExportRequest:
    plan: ForecastRequest
    destination: str
    slicer: str
    slicer_executable: str = ''
    auto_open: bool = False


def make_export_request(model, reference, preferences, filament_preferences, destination):
    """Snapshot unsaved UI edits and slicer choices; no settings are persisted."""
    from desktop.qt_app.forecast_service import make_request
    plan = make_request(model, reference, preferences, filament_preferences)
    slicer = preferences.get('output_application')
    if slicer not in VALID_SLICERS:
        raise ValueError('Choose Bambu Studio or OrcaSlicer as your output slicer.')
    key = ('bambu_studio_executable' if slicer == 'Bambu Studio'
           else 'orcaslicer_executable')
    return ExportRequest(plan, str(destination), slicer,
                         str(preferences.get(key) or ''),
                         bool(preferences.get('auto_open')))


def _validate_options(plan, engine, loader):
    """Mirror the current forecast source, pin, enable and protection contract."""
    s = plan.settings
    source = s['source']
    custom = s.get('custom') or None
    if source == 'custom' and (not custom or not Path(custom).is_file()):
        raise ValueError('Choose a valid custom filament JSON library in Filaments.')
    standard = (Path(plan.model).suffix.lower() == '.3mf'
                and engine.is_standard_colored_3mf(Path(plan.model)))
    if plan.protections and not standard:
        raise ValueError('Protected source-color assignments require a standard material-colored 3MF.')
    if s['strategy'] == 'cmykw' and plan.protections:
        raise ValueError('CMYKW cannot be used with protected solid-color assignments.')
    if not standard and Path(plan.model).suffix.lower() in ('.obj', '.glb'):
        pass
    if (standard or Path(plan.model).suffix.lower() in ('.obj', '.glb')) and not s.get('native_project_template'):
        raise ValueError('Choose a blank slicer-saved Native Project Template before exporting this source.')
    if not standard and Path(plan.model).suffix.lower() == '.3mf' and s.get('native_project_template'):
        raise ValueError('Native 3MF input already contains slicer settings; clear the template to preserve them.')
    options = (loader or _available_keys)(engine, source, custom) or []
    available = {str(item['key']) for item in options}
    enabled = available - plan.disabled
    if source != 'exact-cmykw' and len({str(item.get('color','')).upper()
            for item in options if item['key'] in enabled}) < 2:
        raise ValueError('Enable at least two distinct filament colors before exporting.')
    protected = dict(plan.protections)
    if any(key not in enabled for key in protected.values()):
        raise ValueError('A protected source color is assigned to a disabled filament.')
    return standard, sorted(plan.pinned & enabled), (sorted(enabled) if plan.disabled else None), protected


def _exclusive_publish(files, destination):
    """Never replace a user file, even if the destination changes during export.

    Reserve all final filenames exclusively. Roll back files created by this
    operation if any step fails. After a successful publish, don't re-raise a
    cancellation request, because the validated result is already on disk.
    """
    target = Path(destination).resolve()
    paths = {key: target / Path(file).name for key, file in files.items()}
    if len({str(p).casefold() for p in paths.values()}) != len(paths):
        raise ValueError('Converter returned colliding export filenames.')
    existing = [p.name for p in paths.values() if p.exists()]
    if existing:
        raise FileExistsError('Export files already exist: ' + ', '.join(existing) +
                              '. Move them or choose a different output folder; nothing was overwritten.')
    created = []
    try:
        for key in ARTIFACT_KEYS:
            source = Path(files[key])
            dest = paths[key]
            try:
                os.link(source, dest)  # same-volume atomic, exclusive creation
            except OSError:
                # FAT / restricted filesystem fallback: still no overwrites.
                with source.open('rb') as reader, dest.open('xb') as writer:
                    created.append(dest)
                    shutil.copyfileobj(reader, writer, 1024 * 1024)
                continue
            created.append(dest)
        return {key: str(paths[key]) for key in ARTIFACT_KEYS}
    except BaseException:
        for path in reversed(created):
            try: path.unlink(missing_ok=True)
            except OSError: pass
        raise


def _validated_assets(result, staging):
    if not isinstance(result, dict) or result.get('type') == 'planPreview' or result.get('validation') != 'OK':
        raise RuntimeError('Conversion did not return a validated 3MF result.')
    if not isinstance(result.get('colorValidation'), dict):
        raise RuntimeError('Converter did not provide color-validation evidence.')
    deviation = float(result['colorValidation'].get('maximumDeltaE', float('nan')))
    if not math.isfinite(deviation):
        raise RuntimeError('Converter returned invalid mixed-color validation data.')
    root = Path(staging).resolve()
    paths = {}
    for key in ARTIFACT_KEYS:
        raw = result.get(key)
        if not isinstance(raw, str) or not raw:
            raise RuntimeError(f'Converter omitted required {key} output.')
        path = Path(raw).resolve()
        if path.parent != root or not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f'Converter returned missing or unexpected {key} output.')
        paths[key] = path
    if paths['output'].suffix.lower() != '.3mf':
        raise RuntimeError('Converter returned a non-3MF output.')
    try:
        with ZipFile(paths['output']) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('Generated 3MF archive failed its integrity check.')
            if '3D/3dmodel.model' not in archive.namelist():
                raise RuntimeError('Generated 3MF lacks its main model.')
    except BadZipFile as exc:
        raise RuntimeError('Generated 3MF is not a valid archive.') from exc
    return paths



def _renamed_staged_assets(files, request):
    """Rename verified staging artifacts by planning mode, not launch application.

    The validated 3MF bytes stay identical. Only the human-readable report
    references are adjusted to reflect the published file names.
    """
    from desktop.app_support import APP_VERSION
    if request.slicer not in VALID_SLICERS:
        raise ValueError('Unknown output slicer')
    mode = str(request.plan.settings.get('strategy') or '').lower()
    if mode not in ('official', 'cmykw'):
        raise ValueError('Unknown palette mode for filenames')
    tag = 'CMYKW' if mode == 'cmykw' else 'Optimized'
    basename = f"{Path(request.plan.model).stem}_FS-{tag}_v{APP_VERSION}"
    names = {
        'output': basename + '.3mf',
        'csv': basename + '_recipes.csv',
        'report': basename + '_report.txt',
        'colorValidationReport': basename + '_color-validation.md',
    }
    if len(set(name.casefold() for name in names.values())) != len(names):
        raise ValueError('Export filenames must be distinct')
    renamed = {}
    for key in ARTIFACT_KEYS:
        before = Path(files[key])
        after = before.with_name(names[key])
        if after.exists():
            raise FileExistsError(f'Staging export filename already exists: {after.name}')
        before.rename(after)
        renamed[key] = after
    replacements = {Path(files[key]).name: renamed[key].name for key in ARTIFACT_KEYS}
    for key in ('report', 'colorValidationReport'):
        report = renamed[key]
        content = report.read_text(encoding='utf-8')
        for before, after in replacements.items():
            content = content.replace(before, after)
        report.write_text(content, encoding='utf-8')
    return renamed

def run_export(request: ExportRequest, *, engine=None, options_loader=None, progress=None):
    """Run established engine.convert(plan_only=False) with transactional publish."""
    if engine is None:
        import fullspectrum_engine as engine
    if progress is None:
        progress = lambda fraction, message: None
    if request.slicer not in VALID_SLICERS:
        raise ValueError('Unsupported slicer selected.')
    plan = request.plan
    path = Path(plan.model).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in ('.3mf', '.obj', '.glb'):
        raise ValueError('Select an existing 3MF, OBJ, or GLB model.')
    destination = Path(request.destination).expanduser().resolve()
    if not destination.is_dir():
        raise ValueError('Choose an existing output folder.')
    if not os.access(destination, os.W_OK):
        raise PermissionError('Output folder is not writable.')
    s = plan.settings
    standard, pinned, enabled, protected = _validate_options(plan, engine, options_loader)
    bias = 'auto' if s['smart_quality'] else s['quality_bias']
    progress(0, 'Preparing validated native 3MF export')
    # The legacy engine can replace its target files. NEVER invoke it in the
    # user's selected directory; stage on the same volume, and publish only
    # after its own preservation and color validation succeeds.
    with TemporaryDirectory(prefix='.fullspectrum_export_', dir=destination) as temporary:
        def engine_progress(fraction, message):
            # The engine's 100% means its staging files are ready. User-facing
            # completion occurs only after exclusive publication has succeeded.
            progress(min(.94, max(0.0, float(fraction) * .94)), message)
        result = engine.convert(
            path, s['strategy'], palette_source=s['source'],
            output_dir=temporary, reveal=False, real_slots=s['real_slots'],
            direct_source_colors=standard,
            output_color_strategy=s['output_color_strategy'],
            max_output_colors=s['max_output_colors'], reference=plan.reference,
            custom_catalog_path=s.get('custom') or None,
            native_template_path=s.get('native_project_template') or None,
            quality_bias=bias, catalog_region=s['catalog_region'],
            planner_mode=s['planner_mode'], planning_sample=s['planning_sample'],
            mix_model='bambu', plan_only=False,
            allowed_anchor_keys=enabled, pinned_anchor_keys=pinned,
            solid_color_overrides=protected,
            analysis_dir=None, progress=engine_progress,
        )
        paths = _validated_assets(result, temporary)
        # The converter validates its own staging filename before we rename it.
        paths = _renamed_staged_assets(paths, request)
        progress(.99, 'Publishing validated files without replacing existing outputs')
        published = _exclusive_publish(paths, destination)
        return {**result, **published, 'slicer': request.slicer,
                'autoOpen': request.auto_open,
                'slicerExecutable': request.slicer_executable}
