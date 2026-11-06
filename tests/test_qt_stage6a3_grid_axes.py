"""Stage 6A3: grid policy, resource safety, preferences, and source contracts.

Headless tests require no PySide6 or GPU. Real Qt/OpenGL validation should be
run on Windows with a mesh and an installed OrcaSlicer/Bambu Studio plate.
"""
from __future__ import annotations

import ast
import importlib.util
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'desktop' / 'qt_app'


def module_from_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


policy = module_from_path('stage6a3_policy', PKG / 'preview_grid_policy.py')
geometry = module_from_path('stage6a3_geometry', PKG / 'preview_grid_geometry.py')


class GridPolicyTests(unittest.TestCase):
    def test_automatic_chooses_one_grid_and_keeps_logo_only_plates_measurable(self):
        self.assertEqual(policy.choose_grid_layers('automatic', plate_visible=False,
                          plate_has_art=False), (False, True))
        self.assertEqual(policy.choose_grid_layers('automatic', plate_visible=True,
                          plate_has_art=False), (True, False))
        # Existence of a texture (e.g. brand logo) is not evidence of a grid.
        self.assertEqual(policy.choose_grid_layers('automatic', plate_visible=True,
                          plate_has_art=True), (True, False))

    def test_explicit_plate_overrides_texture_and_hides_world_grid(self):
        self.assertEqual(policy.choose_grid_layers('plate', plate_visible=True,
                          plate_has_art=True), (True, False))
        self.assertEqual(policy.choose_grid_layers('plate', plate_visible=False,
                          plate_has_art=True), (False, False))
        self.assertEqual(policy.choose_grid_layers('perspective', plate_visible=True,
                          plate_has_art=True), (False, True))

    def test_off_never_draws_any_grid(self):
        for plate in (False, True):
            self.assertEqual(policy.choose_grid_layers('off', plate_visible=plate,
                              plate_has_art=True), (False, False))

    def test_quick_toggle_restores_last_grid_mode(self):
        settings = policy.set_grid_mode(policy.DEFAULT_GRID_SETTINGS, 'perspective')
        settings = policy.toggle_grid(settings, False)
        self.assertEqual(settings['mode'], 'off')
        self.assertEqual(settings['last_mode'], 'perspective')
        self.assertEqual(policy.toggle_grid(settings, True)['mode'], 'perspective')

    def test_preferences_roundtrip_and_separate_from_plate_state(self):
        with TemporaryDirectory() as folder:
            plate = Path(folder) / 'plate_workspace.json'
            plate.write_text('{"visible": false}', encoding='utf-8')
            prefs = policy.settings_path(plate)
            self.assertEqual(prefs.name, 'preview_grid.json')
            self.assertEqual(policy.read_grid_settings(prefs), policy.DEFAULT_GRID_SETTINGS)
            data = {'mode': 'plate', 'last_mode': 'plate', 'axes': False}
            policy.write_grid_settings(prefs, data)
            self.assertEqual(policy.read_grid_settings(prefs), data)
            self.assertEqual(plate.read_text(encoding='utf-8'), '{"visible": false}')

    def test_invalid_saved_preferences_are_safely_defaulted(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'preview_grid.json'
            path.write_text('unreadable', encoding='utf-8')
            self.assertEqual(policy.read_grid_settings(path), policy.DEFAULT_GRID_SETTINGS)
            path.write_text('{"mode":"unknown", "axes": false}', encoding='utf-8')
            saved = policy.read_grid_settings(path)
            self.assertEqual(saved['mode'], 'automatic')
            self.assertFalse(saved['axes'])


class WorldGridTests(unittest.TestCase):
    def test_bounded_geometry_for_tiny_and_huge_models(self):
        for scale in (0.01, 1., 256., 1e6):
            data, step = geometry.world_grid_vertices(
                (0, 0, 0, scale, scale, scale), -0.75)
            self.assertLessEqual(len(data)//14, 220)
            self.assertEqual(len(data) % 14, 0)
            self.assertTrue(all(math.isfinite(n) for n in data))
            self.assertGreater(step, 0)

    def test_lines_use_display_only_floor_z(self):
        data, _ = geometry.world_grid_vertices((0, 0, 0, 200, 200, 50), -3.5)
        self.assertTrue(data)
        self.assertTrue(all(abs(data[i] + 3.5) < 1.e-5
                            for i in range(2, len(data), 7)))

    def test_floor_tracks_tall_model_instead_of_using_tiny_xy_footprint(self):
        # E.g. a 120 mm tall sign with a 4 x 3 mm footprint.
        verts, step = geometry.world_grid_vertices((0, 0, 0, 4, 3, 120), -0.5)
        xs = verts[0::7]
        ys = verts[1::7]
        extent = max(max(xs) - min(xs), max(ys) - min(ys))
        self.assertGreaterEqual(extent, 100)
        self.assertLessEqual(extent, 240)
        self.assertGreaterEqual(step, 5)

    def test_floor_remains_proportional_for_small_flat_models(self):
        verts, step = geometry.world_grid_vertices((0, 0, 0, 2, 1, 0.1), -0.02)
        xs = verts[0::7]
        ys = verts[1::7]
        extent = max(max(xs) - min(xs), max(ys) - min(ys))
        self.assertLess(extent, 5.0)  # No legacy 25 mm minimum.
        self.assertGreater(extent, 2.0)
        self.assertLess(step, 1.0)

    def test_grid_is_centered_near_off_origin_model(self):
        verts, _ = geometry.world_grid_vertices((100, -50, 0, 120, -30, 20), -1)
        xs, ys = verts[0::7], verts[1::7]
        self.assertLess(abs((min(xs) + max(xs)) / 2 - 110), 3)
        self.assertLess(abs((min(ys) + max(ys)) / 2 + 40), 3)

    def test_invalid_bounds_rejected(self):
        with self.assertRaises(ValueError):
            geometry.world_grid_vertices((0, 0, 0, -1, 2, 3), -1)
        with self.assertRaises(ValueError):
            geometry.world_grid_vertices((0, 0, 0, 1, 2, 3), float('nan'))


class GridIntegrationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = (PKG / 'main_window.py').read_text(encoding='utf-8-sig')
        cls.viewport = (PKG / 'gl_viewport.py').read_text(encoding='utf-8-sig')
        cls.plate = (PKG / 'plate_gl.py').read_text(encoding='utf-8-sig')
        cls.icons = (PKG / 'preview_toolbar_icons.py').read_text(encoding='utf-8-sig')
        for filename, src in (('main', cls.main), ('viewport', cls.viewport),
                              ('plate', cls.plate), ('icons', cls.icons)):
            ast.parse(src, filename=filename)

    def test_toolbar_and_preview_options_are_independent_of_plate_eye(self):
        self.assertIn("setObjectName('previewGridButton')", self.main)
        self.assertIn("self.preview_grid_menu = self.preview_options_menu.addMenu('Grid and Axes')", self.main)
        self.assertIn('self.plate_visibility_button.clicked.connect(self._toggle_plate_visibility)', self.main)
        self.assertIn('self.preview_grid_button.toggled.connect(self._toggle_preview_grid)', self.main)
        self.assertIn('self._grid_settings_path = preview_grid_settings_path(', self.main)

    def test_renderer_is_display_only_and_lifecycle_safe(self):
        self.assertIn('self._world_grid = WorldGridRenderer()', self.viewport)
        self.assertIn('self._world_grid.release(self._gl)', self.viewport)
        self.assertIn('self._plate_renderer.grid_enabled = show_plate_grid', self.viewport)
        self.assertIn('grid_render_error.emit(', self.viewport)
        self.assertIn("gl.glUniform1i(gl.glGetUniformLocation(self.program, 'showGrid')", self.plate)
        self.assertIn('fwidth(minorCell)', self.plate)
        self.assertIn('normalize(vNormal).z > 0.60', self.plate)
        self.assertNotIn('write_workspace(', self.viewport)

    def test_orbit_updates_axis_overlay_and_new_icon_exists(self):
        self.assertIn('self._axis_indicator.update()', self.viewport)
        self.assertIn("name == 'grid'", self.icons)
        self.assertIn("'grid'", self.icons)
        self.assertIn("ViewAxisIndicator(self)", self.viewport)


class WorldGridResourceTests(unittest.TestCase):
    """Mock OpenGL to verify buffer reuse and deterministic resource cleanup."""

    def test_gl_buffer_reused_on_camera_orbit_and_released(self):
        renderer_module = module_from_path('stage6a3_gl', PKG / 'preview_grid_gl.py')
        from types import SimpleNamespace

        class FakeGL:
            GL_VERTEX_SHADER = 1
            GL_FRAGMENT_SHADER = 2
            GL_COMPILE_STATUS = 3
            GL_LINK_STATUS = 4
            GL_ARRAY_BUFFER = 5
            GL_STATIC_DRAW = 6
            GL_FLOAT = 7
            GL_FALSE = 0
            GL_TRUE = 1
            GL_BLEND = 8
            GL_DEPTH_WRITEMASK = 9
            GL_SRC_ALPHA = 10
            GL_ONE_MINUS_SRC_ALPHA = 11
            GL_LINES = 12
            def __init__(self):
                self.uploads = 0
                self.draws = 0
                self.deleted = []
            def glCreateShader(self, *args): return 101
            def glCreateProgram(self): return 102
            def glGetShaderiv(self, *args): return True
            def glGetProgramiv(self, *args): return True
            def glGenVertexArrays(self, *args): return 103
            def glGenBuffers(self, *args): return 104
            def glGetUniformLocation(self, *args): return 1
            def glIsEnabled(self, *args): return False
            def glGetBooleanv(self, *args): return True
            def glBufferData(self, *args): self.uploads += 1
            def glDrawArrays(self, *args): self.draws += 1
            def glDeleteBuffers(self, *args): self.deleted.append('vbo')
            def glDeleteVertexArrays(self, *args): self.deleted.append('vao')
            def glDeleteProgram(self, *args): self.deleted.append('program')
            def __getattr__(self, name):
                if name.startswith('gl'):
                    return lambda *args: None
                raise AttributeError(name)

        class FakeMatrix:
            def copyDataTo(self): return [1.0] * 16

        gl = FakeGL()
        renderer = renderer_module.WorldGridRenderer()
        bounds = (0, 0, 0, 200, 200, 30)
        renderer.draw(gl, FakeMatrix(), bounds, -0.75)
        renderer.draw(gl, FakeMatrix(), bounds, -0.75)
        self.assertEqual(gl.uploads, 1)
        self.assertEqual(gl.draws, 2)
        renderer.draw(gl, FakeMatrix(), bounds, -5.75)
        self.assertEqual(gl.uploads, 2)
        renderer.release(gl)
        self.assertEqual(sorted(gl.deleted), ['program', 'vao', 'vbo'])
        self.assertEqual(renderer.program, 0)


if __name__ == '__main__':
    unittest.main()
