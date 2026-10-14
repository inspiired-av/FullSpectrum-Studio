#!/usr/bin/env python3
"""Cross-platform FullSpectrum Studio desktop shell for the shared engine."""

import importlib.util
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

MODULE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from desktop.app_support import (
    APP_ROOT,
    APP_VERSION,
    format_plan_preview,
    format_shareable_error_report,
    plan_forecast,
    privacy_safe_error_message,
)
from desktop.filament_options import selectable_filament_options
from desktop.settings_store import load_settings, save_settings
from orca_profile_warning import orca_h2c_warning
from native_project_template import inspect_template, TemplateError
from desktop.slicer_launcher import find_windows_slicer
from desktop.source_path_utils import same_source_path, find_original_material_source
from desktop.windows_mesh_preview import MeshPreviewCanvas
from desktop.source_color_preview import read_standard_color_mesh


def load_engine():
    engine_path = APP_ROOT / "fullspectrum_engine.py"
    root_path = str(APP_ROOT)
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    spec = importlib.util.spec_from_file_location("fullspectrum_engine", engine_path)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    return engine


ENGINE = load_engine()


class StudioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"FullSpectrum Studio {APP_VERSION}")
        self.geometry("1220x820")
        self.minsize(980, 660)
        self.configure(bg="#151719")
        self.project = tk.StringVar()
        self.reference = tk.StringVar()
        self.texture = tk.StringVar()
        self.custom = tk.StringVar()
        self.native_project_template = tk.StringVar()
        self.native_template_status = tk.StringVar(value="No template selected")
        self.slicer_compatibility_status = tk.StringVar(value="")
        self.strategy = tk.StringVar(value="official")
        self.planner_mode = tk.StringVar(value="best")
        self.planning_sample = tk.StringVar(value="preview")
        self.source = tk.StringVar(value="inventory")
        self.catalog_region = tk.StringVar(value="global")
        self.real_slots = tk.StringVar(value="auto")
        self.max_output_colors = tk.StringVar(value="auto")
        self.mix_model = tk.StringVar(value="bambu")
        self.quality_bias = tk.IntVar(value=60)
        self.smart_quality = tk.BooleanVar(value=True)
        self.auto_preview = tk.BooleanVar(value=True)
        self.auto_open = tk.BooleanVar(value=True)
        self.output_application = tk.StringVar(value="Bambu Studio")
        self.slicer_executable_paths = {"bambu_studio_executable": "", "orcaslicer_executable": ""}
        self.slicer_target_label = tk.StringVar(value="Automatic executable detection")
        self.progress = tk.DoubleVar(value=0)
        self.status = tk.StringVar(value="Choose a painted .3mf or textured OBJ / GLB source to begin.")
        self.cancel_requested = False
        self.worker_active = False
        self.last_progress_time = time.monotonic()
        self.last_engine_message = "Waiting for a model."
        self.last_error_report = ""
        self.last_error_log = None
        self.operation_name = "Operation"
        self.settings_revision = 0
        self.auto_preview_dirty = False
        self.auto_preview_after = None
        self.source_preview_photo = None
        self.preview_mode = tk.StringVar(value="Original")
        self.preview_meshes = {}
        self._source_exact_mesh = None
        self._selected_source_color = None
        self._solid_selector_active = False
        self.show_protected_overlay = tk.BooleanVar(value=False)
        self._preview_mode_manually_selected = False
        self._preview_request_id = 0
        self.last_plan_result = None
        self.inventory_snapshot = None
        self.disabled_anchor_keys = set()
        self.pinned_anchor_keys = set()
        self.solid_color_overrides = {}
        self.solid_override_summary = tk.StringVar(value="No protected source colors")
        self.filament_selection_summary = tk.StringVar(value="Loading filament colors...")
        self._restore_saved_settings()
        self._build()
        self._update_filament_selection_summary()
        threading.Thread(target=self._refresh_inventory, daemon=True).start()

    def _restore_saved_settings(self):
        """Only explicitly saved preferences survive restart (not open models)."""
        settings = load_settings()
        fields = (
            "custom", "strategy", "planner_mode", "planning_sample", "source",
            "catalog_region", "real_slots", "max_output_colors", "mix_model", "quality_bias",
            "smart_quality", "auto_preview", "auto_open", "output_application",
            "native_project_template",
        )
        for field in fields:
            if field in settings:
                getattr(self, field).set(settings[field])
        self.disabled_anchor_keys = set(settings.get("disabled_anchor_keys", []))
        self.pinned_anchor_keys = set(settings.get("pinned_anchor_keys", []))
        self._refresh_native_template_status()
        for key in self.slicer_executable_paths:
            self.slicer_executable_paths[key] = settings.get(key, "")

    def save_user_settings(self):
        """Persist settings to the user's config directory; do not bundle models."""
        fields = (
            "custom", "strategy", "planner_mode", "planning_sample", "source",
            "catalog_region", "real_slots", "max_output_colors", "mix_model", "quality_bias",
            "smart_quality", "auto_preview", "auto_open", "output_application",
            "native_project_template",
        )
        settings = {field: getattr(self, field).get() for field in fields}
        settings["disabled_anchor_keys"] = sorted(self.disabled_anchor_keys)
        settings["pinned_anchor_keys"] = sorted(self.pinned_anchor_keys)
        settings.update(self.slicer_executable_paths)
        try:
            save_settings(settings)
        except OSError as error:
            messagebox.showerror("Save Settings", f"Unable to save settings:\n{error}")
            return
        self.status.set("Settings saved. They will be restored at the next launch.")
        messagebox.showinfo("Save Settings", "Your custom filament library and preferences were saved locally.")

    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#151719", foreground="#eef2f3", fieldbackground="#24282b")
        style.configure("TButton", padding=8, foreground="#f6f8f8", background="#292e32")
        style.map("TButton", foreground=[("active", "#ffffff"), ("pressed", "#ffffff"), ("disabled", "#7f898f")], background=[("active", "#343b40"), ("pressed", "#202427")])
        style.configure("Accent.TButton", padding=9, foreground="#081113", background="#55bdcf", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#73ccda"), ("pressed", "#42aabc"), ("disabled", "#41575c")])
        style.configure("TCombobox", foreground="#f6f8f8", fieldbackground="#24282b", background="#292e32", arrowcolor="#f6f8f8")
        style.map("TCombobox", foreground=[("readonly", "#f6f8f8")], fieldbackground=[("readonly", "#24282b")], selectforeground=[("readonly", "#f6f8f8")], selectbackground=[("readonly", "#24282b")])
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#f7f9f9")
        style.configure("Section.TLabel", font=("Segoe UI", 9, "bold"), foreground="#75c6d4")
        style.configure("Metric.TLabel", font=("Segoe UI", 11, "bold"), foreground="#f1f5f5")
        style.configure("Small.TLabel", foreground="#98a5ab")
        style.configure("Warning.TLabel", foreground="#eba85e")
        self.configure(bg="#151719")

        shell = ttk.Frame(self, padding=(18, 14, 18, 18))
        shell.pack(fill="both", expand=True)
        title_row = ttk.Frame(shell)
        title_row.pack(fill="x", pady=(0, 12))
        ttk.Label(title_row, text="FullSpectrum Studio", style="Title.TLabel").pack(side="left")
        ttk.Label(title_row, text="Automatic palette forecast", style="Small.TLabel").pack(side="left", padx=(14, 0), pady=(6, 0))
        ttk.Label(title_row, text=f"v{APP_VERSION}", style="Small.TLabel").pack(side="right", pady=(6, 0))

        workspace = ttk.Panedwindow(shell, orient="horizontal")
        workspace.pack(fill="both", expand=True)
        left_shell = ttk.Frame(workspace, width=445)
        right = ttk.Frame(workspace, padding=(18, 0, 0, 0))
        workspace.add(left_shell, weight=0)
        workspace.add(right, weight=1)

        canvas = tk.Canvas(left_shell, bg="#151719", highlightthickness=0, borderwidth=0, width=430)
        scrollbar = ttk.Scrollbar(left_shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        frame = ttk.Frame(canvas, padding=(2, 2, 14, 18))
        content_window = canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(content_window, width=event.width))
        self.content_canvas = canvas

        ttk.Label(frame, text="SOURCE", style="Section.TLabel").pack(anchor="w", pady=(0, 7))

        for title, variable, action in [
            ("Painted 3MF or textured model", self.project, self.choose_project),
            ("OBJ texture", self.texture, self.choose_texture),
            ("Visual reference", self.reference, self.choose_reference),
            ("Custom filament library", self.custom, self.choose_custom),
        ]:
            ttk.Label(frame, text=title, style="Small.TLabel").pack(anchor="w", pady=(7, 3))
            row = ttk.Frame(frame)
            row.pack(fill="x")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse", command=action).pack(side="left", padx=(8, 0))

        # A native project template carries the printer/process/plate profile,
        # separately from the custom filament palette used by the color planner.
        ttk.Label(frame, text="Native Project Template (.3mf)", style="Small.TLabel").pack(anchor="w", pady=(12, 3))
        template_row = ttk.Frame(frame)
        template_row.pack(fill="x")
        ttk.Entry(template_row, textvariable=self.native_project_template).pack(side="left", fill="x", expand=True)
        ttk.Button(template_row, text="Browse", command=self.choose_native_template).pack(side="left", padx=(8, 0))
        template_actions = ttk.Frame(frame)
        template_actions.pack(fill="x", pady=(4, 0))
        ttk.Button(template_actions, text="About templates", command=self.show_native_template_help).pack(side="left")
        ttk.Button(template_actions, text="Clear", command=self.clear_native_template).pack(side="left", padx=(7, 0))
        ttk.Label(frame, textvariable=self.native_template_status, style="Small.TLabel", wraplength=400).pack(anchor="w", pady=(5, 0))
        ttk.Label(frame, textvariable=self.slicer_compatibility_status,
                  style="Warning.TLabel", wraplength=400, justify="left").pack(anchor="w", pady=(2, 0))

        ttk.Separator(frame).pack(fill="x", pady=18)
        ttk.Label(frame, text="PLAN", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        choices = ttk.Frame(frame)
        choices.pack(fill="x")
        self.combo(choices, "Strategy", self.strategy, ["official", "cmykw"], 0, 0)
        self.combo(choices, "Planner", self.planner_mode, ["best", "fast"], 1, 0)
        self.combo(choices, "Filaments", self.source, ["inventory", "catalog", "all-bambu", "custom", "exact-cmykw"], 2, 0)
        self.combo(choices, "Physical slots", self.real_slots, ["auto", "2", "3", "4", "5", "6", "7", "8"], 0, 1)
        self.combo(choices, "Catalog region", self.catalog_region, ["global", "eu", "us-ca", "uk", "au-nz", "asia"], 1, 1)
        self.combo(choices, "Planning sample", self.planning_sample, ["paint", "preview"], 2, 1)
        limit_row=ttk.Frame(frame)
        limit_row.pack(fill="x", pady=(0, 7))
        ttk.Label(limit_row, text="Max output colors", style="Small.TLabel").pack(side="left")
        ttk.Combobox(limit_row, textvariable=self.max_output_colors,
                     values=["auto"]+[str(i) for i in range(2,33)],
                     state="readonly", width=8).pack(side="left", padx=(9, 8))
        ttk.Label(limit_row, text="total physical + mixed; up to 32",
                  style="Small.TLabel").pack(side="left")

        filament_row = ttk.Frame(frame)
        filament_row.pack(fill="x", pady=(2, 10))
        self.filament_button = ttk.Button(
            filament_row, text="Choose Filament Colors", command=self.open_filament_selector
        )
        self.filament_button.pack(side="left")
        ttk.Button(filament_row, text="Save Settings", command=self.save_user_settings).pack(side="right", padx=(8, 0))
        ttk.Label(
            filament_row, textvariable=self.filament_selection_summary, style="Small.TLabel"
        ).pack(side="left", padx=(10, 0), fill="x", expand=True)
        solids_row = ttk.Frame(frame)
        solids_row.pack(fill="x", pady=(0, 12))
        ttk.Button(solids_row, text="Protect Solid Colors", command=self.open_solid_color_selector).pack(side="left")
        ttk.Label(solids_row, textvariable=self.solid_override_summary, style="Small.TLabel").pack(side="left", padx=(10, 0))

        handoff = ttk.Frame(frame)
        handoff.pack(fill="x", pady=(8, 12))
        ttk.Checkbutton(handoff, text="Open validated output in", variable=self.auto_open).pack(side="left")
        ttk.Combobox(
            handoff, textvariable=self.output_application,
            values=["Bambu Studio", "OrcaSlicer"], state="readonly", width=18
        ).pack(side="left", padx=(8, 0))
        # Explicit build selection supports standalone/portable and nightly slicers.
        slicer_target_row = ttk.Frame(frame)
        slicer_target_row.pack(fill="x", pady=(0, 8))
        ttk.Button(slicer_target_row, text="Choose slicer EXE", command=self.choose_slicer_executable).pack(side="left")
        ttk.Button(slicer_target_row, text="Auto", command=self.reset_slicer_executable).pack(side="left", padx=(6, 0))
        ttk.Label(frame, textvariable=self.slicer_target_label, style="Small.TLabel").pack(anchor="w", pady=(0, 10))

        slider = ttk.Frame(frame)
        slider.pack(fill="x", pady=(0, 14))
        ttk.Checkbutton(slider, text="Smart quality", variable=self.smart_quality).pack(side="left")
        tk.Scale(
            slider, from_=0, to=100, orient="horizontal", variable=self.quality_bias,
            bg="#151719", fg="#d9e1e3", highlightthickness=0, troughcolor="#24282b",
            activebackground="#55bdcf", length=220
        ).pack(side="left", fill="x", expand=True, padx=(12, 0))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(4, 10))
        self.preview_button = ttk.Button(buttons, text="Preview Plan", command=self.preview_plan)
        self.preview_button.pack(side="left")
        self.convert_button = ttk.Button(buttons, text="Compose Palette", command=self.convert, style="Accent.TButton")
        self.convert_button.pack(side="left", padx=(8, 0))
        self.cancel_button = ttk.Button(buttons, text="Cancel", command=self.cancel_conversion, state="disabled")
        self.cancel_button.pack(side="left", padx=8)

        tools = ttk.Frame(frame)
        tools.pack(fill="x")
        self.folder_button = ttk.Button(tools, text="Show Output", command=self.open_folder, state="disabled")
        self.folder_button.pack(side="left")
        self.copy_error_button = ttk.Button(tools, text="Copy Error Report", command=self.copy_error_report, state="disabled")
        self.copy_error_button.pack(side="left", padx=(8, 0))

        forecast_header = ttk.Frame(right)
        forecast_header.pack(fill="x", pady=(0, 9))
        ttk.Label(forecast_header, text="MODEL PREVIEW", style="Section.TLabel").pack(side="left")
        ttk.Checkbutton(forecast_header, text="Automatic", variable=self.auto_preview).pack(side="right")
        ttk.Button(forecast_header, text="Reset View", command=self._reset_preview_camera).pack(side="right", padx=(6, 8))
        self.preview_mode_combo = ttk.Combobox(
            forecast_header, textvariable=self.preview_mode,
            values=["Original", "Predicted", "Color loss", "Anchor influence", "Wireframe"],
            state="readonly", width=17,
        )
        self.preview_mode_combo.pack(side="right", padx=(8, 2))
        self.preview_mode_combo.bind("<<ComboboxSelected>>", self._select_preview_mode)

        self.preview_canvas = MeshPreviewCanvas(
            right, height=350, bg="#0f1112", highlightthickness=1,
            highlightbackground="#30363a", cursor="fleur",
        )
        self.preview_canvas.pack(fill="x")
        self.preview_canvas.create_text(260, 175, text="Open a model to preview", fill="#768187", font=("Segoe UI", 13))
        ttk.Label(right, text="Drag to orbit  •  Scroll to zoom  •  Reset View to recenter",
                  style="Small.TLabel").pack(anchor="w", pady=(5, 0))
        ttk.Checkbutton(
            right, text="Show protected faces (teal)",
            variable=self.show_protected_overlay,
            command=self._update_solid_view_highlights,
        ).pack(anchor="w", pady=(1, 0))

        forecast_row = ttk.Frame(right, padding=(0, 14, 0, 8))
        forecast_row.pack(fill="x")
        self.accuracy_canvas = tk.Canvas(forecast_row, width=112, height=112, bg="#151719", highlightthickness=0)
        self.accuracy_canvas.pack(side="left")
        self.accuracy_value = tk.StringVar(value="--%")
        self.confidence_value = tk.StringVar(value="--%")
        self.error_value = tk.StringVar(value="dE --")
        self.slots_value = tk.StringVar(value="No plan")
        metrics = ttk.Frame(forecast_row)
        metrics.pack(side="left", fill="both", expand=True, padx=(18, 0))
        for title, variable in [
            ("Estimated accuracy", self.accuracy_value),
            ("Confidence", self.confidence_value),
            ("Worst match", self.error_value),
            ("Palette", self.slots_value),
        ]:
            row = ttk.Frame(metrics)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=title, style="Small.TLabel").pack(side="left")
            ttk.Label(row, textvariable=variable, style="Metric.TLabel").pack(side="right")
        self._draw_accuracy(0, empty=True)

        ttk.Label(right, text="EXPECTED PALETTE", style="Section.TLabel").pack(anchor="w", pady=(7, 6))
        self.palette_canvas = tk.Canvas(right, height=44, bg="#151719", highlightthickness=0)
        self.palette_canvas.pack(fill="x")
        self.palette_allocation_status = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.palette_allocation_status,
                  style="Small.TLabel").pack(anchor="w", pady=(0, 5))
        self.gap_message = tk.StringVar(value="")
        gap_row = ttk.Frame(right)
        gap_row.pack(fill="x", pady=(5, 8))
        self.gap_label = ttk.Label(gap_row, textvariable=self.gap_message, style="Warning.TLabel", wraplength=520, justify="left")
        self.gap_label.pack(side="left", fill="x", expand=True)
        self.suggestion_button = ttk.Button(gap_row, text="Use suggestion", command=self.use_forecast_suggestion, state="disabled")
        self.suggestion_button.pack(side="right", padx=(10, 0))

        ttk.Progressbar(right, variable=self.progress, maximum=100).pack(fill="x", pady=(2, 7))
        ttk.Label(right, textvariable=self.status, style="Small.TLabel", wraplength=680, justify="left").pack(anchor="w")
        self.output = tk.Text(right, height=11, bg="#1c2023", fg="#dce4e6", insertbackground="white", relief="flat", padx=12, pady=12, wrap="word")
        self.output.pack(fill="both", expand=True, pady=(10, 0))

        watched = [
            self.project, self.reference, self.texture, self.custom, self.strategy,
            self.planner_mode, self.planning_sample, self.source, self.catalog_region,
            self.real_slots, self.max_output_colors, self.quality_bias, self.smart_quality,
        ]
        for variable in watched:
            variable.trace_add("write", self.schedule_auto_preview)
        self.auto_preview.trace_add("write", self.schedule_auto_preview)
        self.project.trace_add("write", self._clear_model_solid_overrides)
        self.output_application.trace_add("write", self._refresh_slicer_target_label)
        self.output_application.trace_add("write", self._refresh_slicer_compatibility_warning)
        self.source.trace_add("write", self._update_filament_selection_summary)
        self.custom.trace_add("write", self._update_filament_selection_summary)
        self._refresh_slicer_target_label()
        self._refresh_slicer_compatibility_warning()

    def combo(self, parent, title, variable, values, column, row=0):
        parent.columnconfigure(column, weight=1)
        ttk.Label(parent, text=title).grid(row=row * 2, column=column, sticky="w", padx=(0, 20), pady=(0, 2))
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=13).grid(row=row * 2 + 1, column=column, sticky="ew", padx=(0, 12), pady=(0, 8))

    def _refresh_inventory(self):
        try:
            snapshot = ENGINE.read_bambu_inventory(required=False, minimum_colors=0)
        except Exception:
            snapshot = None
        self.after(0, lambda: self._finish_inventory_refresh(snapshot))

    def _finish_inventory_refresh(self, snapshot):
        self.inventory_snapshot = snapshot
        self._update_filament_selection_summary()

    def _clear_model_solid_overrides(self, *_):
        """Overrides belong to the imported model, not user-global preferences."""
        self.solid_color_overrides.clear()
        self.solid_override_summary.set("No protected source colors")

    def open_solid_color_selector(self):
        """Load exact source colors off-thread, with all Tk operations on the GUI thread."""
        source = Path(self.project.get())
        if not source.is_file() or source.suffix.lower() != ".3mf":
            messagebox.showerror("Protect Solid Colors", "Select a standard colored 3MF model first.")
            return
        try:
            if not ENGINE.is_standard_colored_3mf(source):
                original = find_original_material_source(
                    source, ENGINE.is_standard_colored_3mf
                )
                if original is None:
                    raise ValueError(
                        "This SOURCE is a slicer-native or FullSpectrum-generated 3MF, "
                        "not an original material-colored 3MF.\n\n"
                        f"Selected: {source.name}\n\n"
                        "Protect Solid Colors currently needs the original "
                        "material-colored source (for example, "
                        "VSLA v4_SOLID_NoFilter.3mf). Choose it under "
                        "'Painted 3MF or textured model'.\n\n"
                        "Keep your H2C Bambu/Orca blank project under "
                        "'Native Project Template'. That template is not a "
                        "source model and does not disable solid-color protection."
                    )
                if not messagebox.askyesno(
                    "Use original colored 3MF?",
                    "You selected a FullSpectrum-generated project rather "
                    "than its original material-colored model.\n\n"
                    f"Current: {source.name}\n"
                    f"Original: {original.name}\n\n"
                    "Switch SOURCE to the original so Protect Solid Colors "
                    "can use the exact imported colors?\n\n"
                    "Your Native Project Template selection will be retained.",
                    parent=self,
                ):
                    return
                self.project.set(str(original))
                self.load_source_thumbnail(str(original))
                source = original
            options = [
                item for item in self._filament_options()
                if item["key"] not in self.disabled_anchor_keys
            ]
        except (OSError, ValueError, RuntimeError) as error:
            self.status.set("Unable to open solid-color selector.")
            messagebox.showerror("Protect Solid Colors", str(error))
            return
        if not options:
            self.status.set("No enabled filaments available for solid-color protection.")
            messagebox.showerror(
                "Protect Solid Colors",
                "Choose and enable a custom or Bambu filament source first."
            )
            return

        # Each click gets its own token and channel. An obsolete scan cannot
        # open a dialog after a different model or newer scan is selected.
        token = object()
        self._solid_color_scan_token = token
        channel = queue.Queue(maxsize=1)
        self.status.set("Reading exact source colors for solid-filament selection...")

        def worker():
            try:
                result = ("ok", ENGINE.available_solid_source_colors(source))
            except Exception as error:
                result = ("error", str(error) or type(error).__name__)
            # Never call Tk/Tcl methods from this worker thread.
            channel.put(result)

        def poll():
            if getattr(self, "_solid_color_scan_token", None) is not token:
                return
            if not same_source_path(self.project.get(), source):
                self.status.set("Solid-color scan cancelled: source model changed.")
                return
            try:
                outcome, payload = channel.get_nowait()
            except queue.Empty:
                self.after(80, poll)
                return
            self._solid_color_scan_token = None
            if outcome == "error":
                self.status.set("Failed to read exact source colors.")
                messagebox.showerror("Protect Solid Colors", payload)
                return
            if not payload:
                self.status.set("No supported colored faces were found in this model.")
                messagebox.showwarning("Protect Solid Colors", "This 3MF contains no supported face colors.")
                return
            try:
                self._show_solid_color_selector(source, payload, options)
                self.status.set(
                    f"Loaded {len(payload)} exact source colors. Select the colors to protect."
                )
            except Exception as error:
                # Tk callbacks otherwise only print to stderr and can leave the
                # status stuck on 'Reading...' in a windowed executable.
                self.status.set("Could not display the solid-color selector.")
                messagebox.showerror(
                    "Protect Solid Colors",
                    f"Source colors loaded, but the selector could not open:\n{error}"
                )
                raise  # Keep the full traceback in the terminal/debug log.

        # Schedule polling from the UI thread before starting the worker.
        self.after(80, poll)
        threading.Thread(target=worker, daemon=True, name="SolidColorScan").start()

    def _update_solid_view_highlights(self):
        """Show selections during editing, protected faces only when requested."""
        show_protected = self._solid_selector_active or self.show_protected_overlay.get()
        self.preview_canvas.set_highlights(
            selected=self._selected_source_color if self._solid_selector_active else None,
            protected=self.solid_color_overrides if show_protected else (),
        )

    def _set_source_color_highlight(self, selected_color):
        """Identify exact source faces while the protected-color dialog is open."""
        self._selected_source_color = selected_color
        self._update_solid_view_highlights()
        if getattr(self, "_source_exact_mesh", None):
            self.preview_mode.set("Original")
            self._preview_mode_manually_selected = True
            self._show_preview_mode()

    def _show_solid_color_selector(self, source, counts, options):
        if not same_source_path(self.project.get(), source):
            return
        if not counts or not options:
            messagebox.showwarning("Protect Solid Colors", "No colored faces or available filaments were found.")
            return
        panel = tk.Toplevel(self)
        panel.title("Protected Solid Colors")
        panel.geometry("840x650")
        panel.minsize(680, 520)
        panel.transient(self)
        self._solid_selector_active = True

        ttk.Label(panel, text="Choose a 3MF source color and assign a physical filament."
                  " Amber faces = current selection; teal faces = already protected.",
                  wraplength=780).pack(anchor="w", padx=14, pady=(14, 8))
        ttk.Label(panel, text="Exact source colors (before 32-slot quantization)").pack(anchor="w", padx=14)

        colors = list(counts)
        color_area = ttk.Frame(panel)
        color_area.pack(fill="both", expand=True, padx=14, pady=(4, 9))
        color_list = tk.Listbox(color_area, height=12, exportselection=False,
                                font=("Consolas", 10), selectmode="browse",
                                selectbackground="#ffcf65", selectforeground="#181818",
                                highlightthickness=0, relief="flat")
        color_scroll = ttk.Scrollbar(color_area, orient="vertical", command=color_list.yview)
        color_list.configure(yscrollcommand=color_scroll.set)
        color_list.pack(side="left", fill="both", expand=True)
        color_scroll.pack(side="right", fill="y")

        preview_row = ttk.Frame(panel)
        preview_row.pack(fill="x", padx=14, pady=(0, 10))
        ttk.Label(preview_row, text="Selected source color:").pack(side="left")
        color_patch = tk.Canvas(preview_row, width=35, height=25, bg="#9098A8",
                                borderwidth=0, highlightthickness=1,
                                highlightbackground="#646a6f")
        color_patch.pack(side="left", padx=(10, 8))
        selected_label = ttk.Label(preview_row, text="", style="Small.TLabel")
        selected_label.pack(side="left", fill="x", expand=True)

        ttk.Label(panel, text="Force this physical filament").pack(anchor="w", padx=14)
        filaments = {f"{item['name']} ({item['color']}) [{item['key']}]": item
                     for item in options}
        filament_label = tk.StringVar(value=next(iter(filaments)))
        filament_row = ttk.Frame(panel)
        filament_row.pack(fill="x", padx=14, pady=(4, 10))
        filament_box = ttk.Combobox(filament_row, textvariable=filament_label,
                                    values=list(filaments), state="readonly")
        filament_box.pack(side="left", fill="x", expand=True)
        filament_patch = tk.Canvas(filament_row, width=35, height=26, bg="#9199A4",
                                   borderwidth=0, highlightthickness=1,
                                   highlightbackground="#646a6f")
        filament_patch.pack(side="left", padx=(8, 0))

        columns = ("source", "filament")
        table = ttk.Treeview(panel, columns=columns, show="headings", height=6, selectmode="extended")
        table.heading("source", text="Protected source color")
        table.heading("filament", text="Solid physical filament")
        table.column("source", width=180, stretch=False)
        table.column("filament", width=550)
        table.pack(fill="both", expand=True, padx=14, pady=(4, 8))

        def contrast(hex_color):
            channels = [int(hex_color[i:i+2], 16) for i in (1, 3, 5)]
            return "#101115" if sum(x*w for x,w in zip(channels,(0.299,0.587,0.114))) > 142 else "#F6F8F9"

        def update_filament_patch(*_):
            chosen = filaments.get(filament_label.get())
            if chosen:
                filament_patch.configure(bg=chosen["color"])

        def selected_color():
            choices = color_list.curselection()
            return colors[choices[0]] if choices else None

        def select_color(*_):
            color = selected_color()
            if not color:
                return
            color_patch.configure(bg=color)
            suffix = "  •  PROTECTED" if color in self.solid_color_overrides else ""
            selected_label.configure(text=f"{color}  •  {counts[color]:,} faces{suffix}")
            self._set_source_color_highlight(color)

        def refresh(select=None):
            current = select or selected_color() or (colors[0] if colors else None)
            color_list.delete(0, "end")
            for index, color in enumerate(colors):
                marker = "[SOLID]" if color in self.solid_color_overrides else "       "
                color_list.insert("end", f"{marker}  {color}    {counts[color]:>7,} faces")
                color_list.itemconfig(index, background=color, foreground=contrast(color))
            if current in colors:
                idx = colors.index(current)
                color_list.selection_set(idx)
                color_list.see(idx)
            for iid in table.get_children():
                table.delete(iid)
            for color, key in sorted(self.solid_color_overrides.items()):
                label = next((item["name"] + " (" + item["color"] + ")"
                              for item in options if item["key"] == key), key)
                table.insert("", "end", iid=color, values=(f"■  {color}", label))
            amount = len(self.solid_color_overrides)
            self.solid_override_summary.set(f"{amount} protected solid color(s)" if amount
                                            else "No protected source colors")
            self._update_solid_view_highlights()
            select_color()

        def add():
            color = selected_color()
            chosen = filaments.get(filament_label.get())
            if not color or not chosen:
                return
            self.solid_color_overrides[color] = chosen["key"]
            refresh(color)
            self.schedule_auto_preview()

        def remove():
            items = table.selection()
            for color in items:
                self.solid_color_overrides.pop(color, None)
            refresh()
            if items:
                self.schedule_auto_preview()

        controls = ttk.Frame(panel)
        controls.pack(fill="x", padx=14, pady=(0, 14))
        ttk.Button(controls, text="Add / Update Rule", command=add).pack(side="left")
        ttk.Button(controls, text="Remove Selected", command=remove).pack(side="left", padx=(8, 0))
        def close_dialog():
            self._solid_selector_active = False
            self._selected_source_color = None
            self._update_solid_view_highlights()
            panel.destroy()

        panel.protocol("WM_DELETE_WINDOW", close_dialog)
        ttk.Button(controls, text="Done", command=close_dialog).pack(side="right")
        color_list.bind("<<ListboxSelect>>", select_color)
        filament_box.bind("<<ComboboxSelected>>", update_filament_patch)
        update_filament_patch()
        refresh()
        panel.deiconify()
        panel.lift()
        panel.focus_force()

    def _filament_options(self):
        try:
            return selectable_filament_options(
                ENGINE, self.source.get(), self.inventory_snapshot, self.custom.get()
            )
        except (OSError, ValueError, RuntimeError):
            # A missing or invalid library is explained when opening the chooser.
            # Keep forecast/status refreshes non-modal.
            return []

    def _update_filament_selection_summary(self, *_):
        source = self.source.get()
        if source not in ("inventory", "catalog", "all-bambu", "custom"):
            self.filament_selection_summary.set("Automatic for this filament source")
            return
        if source == "custom":
            custom_path = self.custom.get().strip()
            if not custom_path:
                self.filament_selection_summary.set("Choose a custom JSON library")
                return
            if not Path(custom_path).is_file():
                self.filament_selection_summary.set("Custom JSON library not found")
                return
        elif self.inventory_snapshot is None:
            self.filament_selection_summary.set("Loading filament colors...")
            return
        options = self._filament_options()
        if not options:
            self.filament_selection_summary.set("No usable colors in current source")
            return
        option_keys = {item["key"] for item in options}
        self.disabled_anchor_keys.intersection_update(option_keys)
        self.pinned_anchor_keys.intersection_update(option_keys)
        enabled = len(option_keys - self.disabled_anchor_keys)
        pins = len(self.pinned_anchor_keys)
        self.filament_selection_summary.set(
            f"{enabled} of {len(options)} enabled" + (f" | {pins} pinned" if pins else "")
        )

    def open_filament_selector(self):
        try:
            options = selectable_filament_options(
                ENGINE, self.source.get(), self.inventory_snapshot, self.custom.get()
            )
        except (OSError, RuntimeError, ValueError) as error:
            messagebox.showerror("Filament colors", f"Could not open filament library:\n{error}")
            return
        if not options:
            if self.source.get() == "custom":
                messagebox.showinfo("Filament colors", "Choose a custom filament JSON library first.")
            elif self.inventory_snapshot is None and self.source.get() in ("inventory", "catalog", "all-bambu"):
                messagebox.showinfo("Filament colors", "The Bambu Studio filament inventory is still loading.")
            else:
                messagebox.showinfo("Filament colors", "No selectable filament colors for this source.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Filament Colors")
        dialog.geometry("650x650")
        dialog.minsize(520, 470)
        dialog.configure(bg="#151719")
        dialog.transient(self)
        dialog.grab_set()

        shell = ttk.Frame(dialog, padding=16)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="FILAMENT COLORS", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            shell,
            text="Enable colors the planner may use. Pin only colors that must occupy a physical slot.",
            style="Small.TLabel",
            wraplength=590,
            justify="left",
        ).pack(anchor="w", pady=(5, 12))

        toolbar = ttk.Frame(shell)
        toolbar.pack(fill="x", pady=(0, 9))
        search = tk.StringVar()
        ttk.Entry(toolbar, textvariable=search).pack(side="left", fill="x", expand=True)
        selected = {
            item["key"]: tk.BooleanVar(value=item["key"] not in self.disabled_anchor_keys)
            for item in options
        }
        pinned = {
            item["key"]: tk.BooleanVar(value=item["key"] in self.pinned_anchor_keys)
            for item in options
        }

        canvas = tk.Canvas(shell, bg="#151719", highlightthickness=1, highlightbackground="#30363a")
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        rows = ttk.Frame(canvas, padding=(8, 6))
        window = canvas.create_window((0, 0), window=rows, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        rows.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def toggle_pin(key):
            if pinned[key].get():
                selected[key].set(True)

        def rebuild(*_):
            for child in rows.winfo_children():
                child.destroy()
            query = search.get().strip().lower()
            visible = [
                item for item in options
                if not query or query in str(item.get("name") or "").lower()
                or query in str(item.get("series") or "").lower()
                or query in str(item.get("color") or "").lower()
            ]
            for item in visible:
                key = item["key"]
                row = ttk.Frame(rows, padding=(2, 5))
                row.pack(fill="x")
                ttk.Checkbutton(row, variable=selected[key]).pack(side="left")
                swatch = tk.Frame(row, width=22, height=22, bg=item.get("color") or "#777777")
                swatch.pack(side="left", padx=(3, 9))
                swatch.pack_propagate(False)
                label = ttk.Frame(row)
                label.pack(side="left", fill="x", expand=True)
                ttk.Label(label, text=item.get("name") or key).pack(anchor="w")
                grams = item.get("remainingGrams")
                detail = (
                    f"{item.get('series', '')} | {item.get('color', '')} | {grams:.0f} g remaining"
                    if grams is not None else
                    f"{item.get('series', '')} | {item.get('color', '')} | catalog color"
                )
                ttk.Label(label, text=detail, style="Small.TLabel").pack(anchor="w")
                ttk.Checkbutton(
                    row, text="Pin", variable=pinned[key], command=lambda value=key: toggle_pin(value)
                ).pack(side="right", padx=(8, 2))
            if not visible:
                ttk.Label(rows, text="No matching filament colors.", style="Small.TLabel").pack(pady=24)

        search.trace_add("write", rebuild)
        rebuild()

        footer = ttk.Frame(dialog, padding=(16, 0, 16, 16))
        footer.pack(fill="x")

        def select_all():
            for value in selected.values():
                value.set(True)

        def clear_pins():
            for value in pinned.values():
                value.set(False)

        def apply_selection():
            enabled = {key for key, value in selected.items() if value.get()}
            colors = {item.get("color") for item in options if item["key"] in enabled}
            if len(colors) < 2:
                messagebox.showerror("Filament colors", "Enable at least two distinct filament colors.", parent=dialog)
                return
            selected_pins = {key for key, value in pinned.items() if value.get()} & enabled
            maximum = int(self.real_slots.get()) if self.real_slots.get().isdigit() else 6
            if len(selected_pins) > maximum:
                messagebox.showerror(
                    "Filament colors",
                    f"This plan allows at most {maximum} pinned physical colors.",
                    parent=dialog,
                )
                return
            all_keys = {item["key"] for item in options}
            self.disabled_anchor_keys = all_keys - enabled
            self.pinned_anchor_keys = selected_pins
            self._update_filament_selection_summary()
            dialog.destroy()
            self.schedule_auto_preview()

        ttk.Button(footer, text="All", command=select_all).pack(side="left")
        ttk.Button(footer, text="Clear Pins", command=clear_pins).pack(side="left", padx=(8, 0))
        ttk.Button(footer, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(footer, text="Apply", command=apply_selection, style="Accent.TButton").pack(side="right", padx=(0, 8))

    def schedule_auto_preview(self, *_):
        self.settings_revision += 1
        if self.auto_preview_after is not None:
            self.after_cancel(self.auto_preview_after)
            self.auto_preview_after = None
        if not self.auto_preview.get():
            self.auto_preview_dirty = False
            return
        source = Path(self.project.get())
        if not source.is_file() or source.suffix.lower() not in (".3mf", ".obj", ".glb"):
            return
        if self.source.get() == "custom" and not Path(self.custom.get()).is_file():
            return
        if self.worker_active:
            self.auto_preview_dirty = True
            return
        self.auto_preview_dirty = False
        revision = self.settings_revision
        self.status.set("Live forecast queued for the current choices.")
        self.auto_preview_after = self.after(
            750,
            lambda: self.start_operation(plan_only=True, automatic=True, operation_revision=revision),
        )

    def _draw_accuracy(self, score, empty=False):
        canvas = self.accuracy_canvas
        canvas.delete("all")
        canvas.create_arc(10, 10, 102, 102, start=90, extent=-359.9, style="arc", width=9, outline="#2b3033")
        if not empty:
            color = "#58c488" if score >= 88 else ("#55bdcf" if score >= 70 else "#eba85e")
            canvas.create_arc(10, 10, 102, 102, start=90, extent=-359.9 * max(0, min(100, score)) / 100, style="arc", width=9, outline=color)
        canvas.create_text(56, 51, text="--%" if empty else f"{round(score):.0f}%", fill="#f1f5f5", font=("Segoe UI", 18, "bold"))
        canvas.create_text(56, 72, text="accuracy", fill="#88959b", font=("Segoe UI", 8, "bold"))

    def _draw_palette(self, colors):
        self.palette_canvas.delete("all")
        if not colors:
            self.palette_canvas.configure(height=44)
            self.palette_canvas.create_text(6, 22, anchor="w", text="No forecast palette", fill="#768187", font=("Segoe UI", 10))
            return
        width = max(320, self.palette_canvas.winfo_width())
        gap = 5
        columns = min(16, len(colors))
        rows = (len(colors) + columns - 1) // columns
        swatch_width = max(18, (width - gap * (columns - 1)) / columns)
        self.palette_canvas.configure(height=8 + rows * 33 + max(0, rows - 1) * gap)
        for index, color in enumerate(colors):
            if not isinstance(color, str) or len(color) != 7 or not color.startswith("#"):
                continue
            column = index % columns
            row = index // columns
            x0 = column * (swatch_width + gap)
            y0 = 4 + row * (33 + gap)
            self.palette_canvas.create_rectangle(x0, y0, x0 + swatch_width, y0 + 33, fill=color, outline="#4a5155", width=1)

    def update_forecast(self, result):
        self.last_plan_result = result
        forecast = plan_forecast(result)
        score = forecast["accuracy"]
        confidence = forecast["confidence"]
        maximum = forecast["maximumDeltaE"]
        self.accuracy_value.set(f"{score:.0f}%")
        self.confidence_value.set(f"{confidence:.0f}%")
        self.error_value.set(f"dE {maximum:.1f}")
        self.slots_value.set(forecast["slotSummary"])
        self._draw_accuracy(score)
        self._draw_palette(forecast["colors"])
        requested = self.max_output_colors.get()
        count = len(result.get("outputColors") or forecast["colors"])
        if requested == "auto":
            self.palette_allocation_status.set(f"Using {count} total colors (Auto)")
        else:
            detail = "All allowed slots used" if count == int(requested) else "Only useful printable recipes added"
            self.palette_allocation_status.set(f"Using {count}/{requested} total colors — {detail}")

        suggestion = forecast["suggestion"]
        self.forecast_suggestion = suggestion
        self.suggestion_button.configure(state="normal" if suggestion else "disabled")
        self.gap_message.set(forecast["gapMessage"])
        self._update_plan_meshes(result)

    def use_forecast_suggestion(self):
        suggestion = getattr(self, "forecast_suggestion", None)
        if not suggestion:
            return
        if suggestion.get("availability") == "not in My Inventory":
            self.source.set("all-bambu")
        else:
            self.planner_mode.set("best")
        key = suggestion.get("key")
        if key:
            self.disabled_anchor_keys.discard(key)
            self.pinned_anchor_keys.add(key)
            self._update_filament_selection_summary()
        self.schedule_auto_preview()

    def _reset_preview_camera(self):
        self.preview_canvas.reset_camera()

    def _select_preview_mode(self, *_):
        self._preview_mode_manually_selected = True
        self._show_preview_mode()

    def _show_preview_mode(self):
        selected = self.preview_mode.get()
        if selected in ("Original", "Wireframe") and self._source_exact_mesh:
            try:
                self.preview_canvas.selected_color = (self._selected_source_color
                    if self._solid_selector_active else None)
                self.preview_canvas.protected_colors = (set(self.solid_color_overrides)
                    if self._solid_selector_active or self.show_protected_overlay.get() else set())
                self.preview_canvas.load_source_mesh(*self._source_exact_mesh)
                self.preview_canvas.wireframe = (selected == "Wireframe")
                if selected == "Wireframe":
                    self.preview_canvas.redraw()
                return
            except (OSError, ValueError) as error:
                self._show_preview_message(f"Couldn't display original model\n{error}")
                return
        key = "Original" if selected == "Wireframe" else selected
        candidate = self.preview_meshes.get(key)
        if candidate and Path(candidate).is_file():
            try:
                self.preview_canvas.set_highlights(selected=None, protected=())
                self.preview_canvas.load_mesh(candidate, wireframe=(selected == "Wireframe"))
                return
            except (OSError, ValueError) as error:
                self._show_preview_message(f"Couldn't display {selected.lower()} mesh\n{error}")
                return
        if selected == "Original":
            self._show_preview_message("Loading source 3D model..." if self.project.get() else "Open a model to preview")
        else:
            self._show_preview_message("Run Preview Plan to generate this view.")

    def _update_plan_meshes(self, result):
        if not same_source_path(result.get("input"), self.project.get()):
            return
        assets = result.get("analysisAssets") or {}
        for label, key in (("Predicted", "predictedMesh"),
                           ("Color loss", "heatmapMesh"),
                           ("Anchor influence", "anchorInfluenceMesh")):
            value = assets.get(key)
            if value and Path(value).is_file():
                self.preview_meshes[label] = str(value)
        if "Predicted" in self.preview_meshes and not self._preview_mode_manually_selected:
            self.preview_mode.set("Predicted")
        self._show_preview_mode()

    def load_source_thumbnail(self, path):
        source = Path(path)
        self._preview_request_id += 1
        request_id = self._preview_request_id
        self.preview_meshes.clear()
        self._source_exact_mesh = None
        self._selected_source_color = None
        self._solid_selector_active = False
        self.preview_canvas.set_highlights(selected=None, protected=())
        self._preview_mode_manually_selected = False
        self.last_plan_result = None
        self.preview_mode.set("Original")
        self._show_preview_mode()
        if source.suffix.lower() not in (".3mf", ".obj", ".glb"):
            self._show_preview_message("Choose a colored 3MF or textured OBJ/GLB model")
            return
        directory = Path(tempfile.gettempdir()) / "FullSpectrumStudio" / "windows-viewer"
        destination = directory / f"source-{time.time_ns()}.png"
        mesh_destination = destination.with_suffix(".obj")

        channel = queue.Queue(maxsize=1)
        texture = self.texture.get() or None

        def worker():
            try:
                inspected = ENGINE.inspect_project(
                    source, thumbnail_dest=destination, preview_mesh_dest=mesh_destination,
                    texture_override=texture, metadata_only=False,
                )
                # Keep the original 3MF's exact face colors for selection
                # highlighting; the ordinary engine display remains the fallback.
                if source.suffix.lower() == ".3mf" and ENGINE.is_standard_colored_3mf(source):
                    try:
                        inspected["_exactSourcePreview"] = read_standard_color_mesh(source)
                    except (OSError, ValueError, RuntimeError):
                        inspected["_exactSourcePreview"] = None
                channel.put(("ok", inspected))
            except Exception as error:
                channel.put(("error", str(error) or type(error).__name__))

        def poll():
            if request_id != self._preview_request_id or not same_source_path(self.project.get(), source):
                return
            try:
                status, payload = channel.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            if status == "error":
                self._show_preview_message(f"Unable to preview source\n{payload}")
                return
            self._source_exact_mesh = payload.get("_exactSourcePreview")
            thumbnail, mesh = payload.get("thumbnail"), payload.get("previewMesh")
            if mesh and Path(mesh).is_file():
                self.preview_meshes["Original"] = str(mesh)
                if self.preview_mode.get() in ("Original", "Wireframe"):
                    self._show_preview_mode()
            elif thumbnail:
                self._show_source_thumbnail(thumbnail)
            else:
                self._show_preview_message("Source loaded\nNo preview geometry available")

        self.after(100, poll)
        threading.Thread(target=worker, daemon=True, name="SourceMeshPreview").start()

    def _show_source_thumbnail(self, path):
        if not path or not Path(path).is_file():
            self._show_preview_message("Source loaded\nPreview image unavailable")
            return
        try:
            with Image.open(path) as source_image:
                image = source_image.convert("RGB")
            width = max(420, self.preview_canvas.winfo_width() - 24)
            image.thumbnail((width, 276), Image.Resampling.LANCZOS)
            self.source_preview_photo = ImageTk.PhotoImage(image)
            self.preview_canvas.clear_mesh()
            self.preview_canvas.create_image(
                max(210, self.preview_canvas.winfo_width() / 2),
                150,
                image=self.source_preview_photo,
            )
        except Exception:
            self._show_preview_message("Source loaded\nPreview image unavailable")
        finally:
            Path(path).unlink(missing_ok=True)

    def _show_preview_message(self, message):
        self.source_preview_photo = None
        self.preview_canvas.clear_mesh()
        self.preview_canvas.create_text(
            max(210, self.preview_canvas.winfo_width() / 2), 150,
            text=message, fill="#768187", font=("Segoe UI", 12), justify="center",
        )

    def choose_project(self):
        path = filedialog.askopenfilename(filetypes=[("FullSpectrum sources", "*.3mf *.obj *.glb"), ("Bambu 3MF", "*.3mf"), ("Textured model", "*.obj *.glb")])
        if path:
            if self.project.get() != path:
                self.texture.set("")
            self.project.set(path)
            self.load_source_thumbnail(path)

    def choose_reference(self):
        path = filedialog.askopenfilename(filetypes=[("Reference assets", "*.obj *.glb *.png *.jpg *.jpeg *.bmp *.tif *.tiff")])
        if path:
            self.reference.set(path)

    def choose_texture(self):
        path = filedialog.askopenfilename(filetypes=[("Base-color texture", "*.png *.jpg *.jpeg")])
        if path:
            self.texture.set(path)

    def _refresh_slicer_compatibility_warning(self, *_):
        path = self.native_project_template.get().strip()
        message = ""
        if path:
            try:
                details = inspect_template(path)
                message = orca_h2c_warning(details, self.output_application.get())
            except (OSError, ValueError, TemplateError):
                pass  # Invalid templates already have their own visible status.
        self.slicer_compatibility_status.set(message)

    def _refresh_native_template_status(self):
        self._refresh_slicer_compatibility_warning()
        value=self.native_project_template.get().strip()
        if not value:
            self.native_template_status.set("No template selected (required to compose generic colored 3MF)")
            return
        try:
            info=inspect_template(value)
        except (TemplateError, OSError, ValueError) as exc:
            self.native_template_status.set(f"Invalid template: {exc}")
            return
        self.native_template_status.set(
            f"{info['slicer']} {info['slicerVersion']} | {info['printerPreset']} | "
            f"{info['nozzle']} mm | {info['processPreset']}"
        )

    def choose_native_template(self):
        name=filedialog.askopenfilename(
            parent=self, title="Choose a blank native Bambu/Orca 3MF project",
            filetypes=[("Native slicer projects", "*.3mf")],
        )
        if not name:
            return
        try:
            info=inspect_template(name)
        except (TemplateError, OSError, ValueError) as exc:
            messagebox.showerror("Invalid native template", str(exc), parent=self)
            return
        self.native_project_template.set(info['path'])
        self._refresh_native_template_status()
        self.status.set("Native slicer template selected; Save Settings to remember it.")

    def clear_native_template(self):
        self.native_project_template.set("")
        self._refresh_native_template_status()

    def show_native_template_help(self):
        messagebox.showinfo(
            "About native project templates",
            "A template is an EMPTY .3mf project saved using Bambu Studio or OrcaSlicer.\n\n"
            "To create one:\n"
            "1. Select your printer, nozzle, build plate, and process settings in your slicer.\n"
            "2. Remove every model from the plate.\n"
            "3. Save the empty project as a .3mf.\n"
            "4. Select it here and use Compose Palette.\n\n"
            "FullSpectrum combines the imported mesh and computed mixed-filament recipes "
            "with the template's native printer and process settings. "
            "It never overwrites the original template.\n\n"
            "A separate filament JSON library still controls the colors you can plan with. "
            "Review printer/nozzle/material settings and mixed recipes in the slicer before printing. "
            "This feature currently applies to generic colored 3MF, OBJ, and GLB imports.",
            parent=self,
        )

    def choose_custom(self):
        path = filedialog.askopenfilename(filetypes=[("JSON filament library", "*.json")])
        if path:
            self.custom.set(path)
            self.source.set("custom")

    def preview_plan(self):
        self.start_operation(plan_only=True)

    def convert(self):
        self.start_operation(plan_only=False)

    def start_operation(self, plan_only, automatic=False, operation_revision=None):
        self.auto_preview_after = None
        if self.worker_active:
            if automatic:
                self.auto_preview_dirty = True
            return
        source = Path(self.project.get())
        if not source.is_file() or source.suffix.lower() not in (".3mf", ".obj", ".glb"):
            if not automatic:
                messagebox.showerror("FullSpectrum Studio", "Choose a colored .3mf or textured OBJ / GLB source first.")
            return
        if self.source.get() == "custom" and not Path(self.custom.get()).is_file():
            if not automatic:
                messagebox.showerror("FullSpectrum Studio", "Choose a custom filament JSON library.")
            return
        self.preview_button.configure(state="disabled")
        self.convert_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.folder_button.configure(state="disabled")
        self.copy_error_button.configure(state="disabled")
        if not automatic:
            self.output.delete("1.0", "end")
        self.progress.set(0)
        self.cancel_requested = False
        self.worker_active = True
        self.last_error_report = ""
        self.last_error_log = None
        self.operation_name = "Plan preview" if plan_only else "Conversion"
        self.record_progress(0, "Updating live forecast." if automatic else ("Starting plan preview." if plan_only else "Starting conversion."))
        self.start_heartbeat()
        operation_revision = self.settings_revision if operation_revision is None else operation_revision
        filament_options = self._filament_options()
        option_keys = {item["key"] for item in filament_options}
        disabled_keys = self.disabled_anchor_keys & option_keys
        options = {
            "strategy": self.strategy.get(),
            "source": self.source.get(),
            "catalog_region": self.catalog_region.get(),
            "planner_mode": self.planner_mode.get(),
            "planning_sample": self.planning_sample.get(),
            "real_slots": self.real_slots.get(),
            "max_output_colors": self.max_output_colors.get(),
            "quality_bias": "auto" if self.smart_quality.get() else self.quality_bias.get(),
            "mix_model": self.mix_model.get(),
            "reference": self.reference.get() or None,
            "texture": self.texture.get() or None,
            "custom": self.custom.get() or None,
            "native_project_template": self.native_project_template.get().strip() or None,
            "auto_open": self.auto_open.get(),
            "output_application": self.output_application.get(),
            "allowed_anchor_keys": sorted(option_keys - disabled_keys) if disabled_keys else None,
            "pinned_anchor_keys": sorted(self.pinned_anchor_keys & option_keys),
            "analysis_dir": str(Path(tempfile.gettempdir()) / "FullSpectrumStudio" /
                                "windows-forecast" / str(os.getpid())),
            "solid_color_overrides": dict(self.solid_color_overrides),
        }
        threading.Thread(
            target=self._run_operation,
            args=(source, options, plan_only, automatic, operation_revision),
            daemon=True,
        ).start()

    def _run_operation(self, source, options, plan_only, automatic, operation_revision):
        def report(fraction, message):
            if self.cancel_requested:
                raise RuntimeError("Operation cancelled by user.")
            self.last_progress_time = time.monotonic()
            self.last_engine_message = message
            self.after(0, lambda: self.record_progress(fraction, message))
        try:
            result = ENGINE.convert(
                source,
                options["strategy"],
                palette_source=options["source"],
                output_dir=source.parent,
                reveal=False,
                real_slots=options["real_slots"],
                max_output_colors=options["max_output_colors"],
                reference=options["reference"],
                custom_catalog_path=options["custom"],
                native_template_path=options["native_project_template"],
                texture_override=options["texture"],
                quality_bias=options["quality_bias"],
                catalog_region=options["catalog_region"],
                planner_mode=options["planner_mode"],
                planning_sample=options["planning_sample"],
                mix_model=options["mix_model"],
                plan_only=plan_only,
                allowed_anchor_keys=options["allowed_anchor_keys"],
                pinned_anchor_keys=options["pinned_anchor_keys"],
                solid_color_overrides=options["solid_color_overrides"],
                analysis_dir=options["analysis_dir"],
                progress=report,
            )
            if plan_only:
                text = format_plan_preview(result)
                self.after(0, lambda: self.finish_plan(result, text, automatic, operation_revision))
                return
            text = [
                f"Validated output: {result['output']}",
                f"Physical slots: {result['realSlots']}   Mixed slots: {result['outputSlots'] - result['realSlots']}",
                f"Quality/waste: {result.get('qualityBiasMode', 'manual')} {result.get('qualityBias', options['quality_bias'])}",
                f"Planner: {result.get('plannerMode', options['planner_mode'])}",
                f"Catalog planning region: {result.get('catalogRegionLabel', options['catalog_region'])}",
                f"Quality: {result['quality']['qualityScore']:.1f} / 100   Mean dE: {result['quality']['estimatedDeltaE']:.2f}   Max dE: {result['quality']['maximumDeltaE']:.2f}",
                f"Confidence: {result['quality']['confidenceScore']:.1f} / 100   Contrast: {result['quality'].get('contrastRetention', 0):.1f}%",
                f"Bambu color synchronization: dE {result['colorValidation']['maximumDeltaE']:.2f} max (verified)",
                f"Printability: {result['printability']['difficulty']}   Mixed paint: {result['printability']['paintedMixedShare']:.1f}%",
                "Geometry, textures and decoded paint remap: verified",
                "Actual time and filament usage require slicing in Bambu Studio.",
            ]
            text.extend(f"Suggestion: {suggestion}" for suggestion in result["printability"]["recommendations"])
            text.extend(f"Warning: {warning}" for warning in result["warnings"])
            self.last_output = result["output"]
            self.after(0, lambda: self.finish(result, "\n".join(text)))
            if options["auto_open"]:
                self.after(0, self.open_validated_output, result["output"], options["output_application"])
        
        except Exception as error:
            details = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            self.after(
                0,
                self.fail,
                str(error) or type(error).__name__,
                details,
                automatic,
            )

    def finish(self, result, text):
        self.worker_active = False
        self.inventory_snapshot = result.get("inventory") or self.inventory_snapshot
        self._update_filament_selection_summary()
        self.preview_button.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.update_forecast(result)
        self.status.set("Conversion validated and ready.")
        self.progress.set(100)
        self.convert_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.folder_button.configure(state="normal")
        self._resume_auto_preview_if_needed()

    def finish_plan(self, result, text, automatic=False, operation_revision=None):
        self.worker_active = False
        self.preview_button.configure(state="normal")
        self.convert_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.folder_button.configure(state="disabled")
        if automatic and operation_revision != self.settings_revision:
            self.status.set(
                "Choices changed. Refreshing the live forecast."
                if self.auto_preview.get() else "Automatic forecast paused."
            )
            self._resume_auto_preview_if_needed(force=True)
            return
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.update_forecast(result)
        self.status.set(
            f"Live forecast ready: {result['quality']['qualityScore']:.0f}% estimated accuracy."
            if automatic else "Plan preview ready. No 3MF was written."
        )
        self.progress.set(100)
        self._resume_auto_preview_if_needed()

    def fail(self, message, details=None, quiet=False):
        self.worker_active = False
        if self.cancel_requested:
            self.status.set(f"{self.operation_name} cancelled.")
            self.preview_button.configure(state="normal")
            self.convert_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")
            self._resume_auto_preview_if_needed()
            return
        suffix = "cancelled." if self.cancel_requested else "failed."
        self.status.set(f"{self.operation_name} {suffix}")
        self.preview_button.configure(state="normal")
        self.convert_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.copy_error_button.configure(state="normal")
        self.output.delete("1.0", "end")
        report = self.build_error_report(message, details)
        self.output.insert("1.0", report)
        if not quiet:
            messagebox.showerror("FullSpectrum Studio", privacy_safe_error_message(message))
        self._resume_auto_preview_if_needed()

    def _resume_auto_preview_if_needed(self, force=False):
        should_resume = force or self.auto_preview_dirty
        self.auto_preview_dirty = False
        if should_resume and self.auto_preview.get():
            self.schedule_auto_preview()

    def cancel_conversion(self):
        self.cancel_requested = True
        self.status.set("Cancelling at the next safe engine checkpoint...")

    def record_progress(self, fraction, message):
        self.progress.set(fraction * 100)
        self.status.set(message)

    def start_heartbeat(self):
        self.after(5000, self.check_heartbeat)

    def check_heartbeat(self):
        if not self.worker_active:
            return
        if self.cancel_requested:
            self.status.set("Cancelling at the next safe engine checkpoint...")
        else:
            idle = time.monotonic() - self.last_progress_time
            if idle >= 90:
                self.status.set(f"Possibly stuck at: {self.last_engine_message}")
            elif idle >= 20:
                self.status.set(f"Still working: {self.last_engine_message}")
        self.after(5000, self.check_heartbeat)

    def build_error_report(self, message, details=None):
        private_body = "\n".join([
            "FullSpectrum Studio conversion error",
            "",
            message,
            "",
            details or message,
        ])
        self.last_error_log = self.write_debug_log(private_body)
        self.last_error_report = format_shareable_error_report(
            message,
            log_created=self.last_error_log is not None,
        )
        return self.last_error_report

    def write_debug_log(self, report):
        try:
            if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
                root = Path(os.environ["LOCALAPPDATA"]) / "FullSpectrumStudio" / "Logs"
            elif sys.platform == "darwin":
                root = Path.home() / "Library" / "Logs" / "FullSpectrumStudio"
            else:
                root = Path.home() / ".cache" / "FullSpectrumStudio" / "Logs"
            root.mkdir(parents=True, exist_ok=True)
            path = root / f"conversion-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
            path.write_text(
                "\n".join([
                    "FullSpectrum Studio desktop debug log",
                    f"Created: {datetime.now(timezone.utc).isoformat()}",
                    "",
                    report,
                ]),
                encoding="utf-8",
            )
            return path
        except Exception:
            return None

    def copy_error_report(self):
        if not self.last_error_report:
            return
        self.clipboard_clear()
        self.clipboard_append(self.last_error_report)
        self.status.set("Privacy-safe error report copied.")

    def open_folder(self):
        if not hasattr(self, "last_output"):
            return
        output = str(Path(self.last_output))
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", output])
        else:
            subprocess.run(["open", "-R", output])

    def _current_slicer_executable_key(self):
        return ("bambu_studio_executable" if self.output_application.get() == "Bambu Studio"
                else "orcaslicer_executable")

    def _refresh_slicer_target_label(self, *_):
        selection = self.slicer_executable_paths.get(self._current_slicer_executable_key(), "")
        if selection:
            self.slicer_target_label.set(f"Selected: {Path(selection).name} (custom path)")
        else:
            self.slicer_target_label.set("Automatic executable detection")

    def choose_slicer_executable(self):
        """Pick a specific installed, standalone or nightly build for this slicer."""
        if os.name != "nt":
            messagebox.showinfo("Slicer selection", "Custom executable selection is currently available on Windows.", parent=self)
            return
        application = self.output_application.get()
        if application not in ("Bambu Studio", "OrcaSlicer"):
            return
        filename = filedialog.askopenfilename(
            parent=self, title=f"Choose {application} executable (nightly / portable supported)",
            filetypes=[("Windows executables", "*.exe"), ("All files", "*.*")],
        )
        if not filename:
            return
        candidate = Path(filename).expanduser()
        if not candidate.is_file() or candidate.suffix.lower() != ".exe":
            messagebox.showerror("Invalid slicer executable", "Select an existing .exe file.", parent=self)
            return
        self.slicer_executable_paths[self._current_slicer_executable_key()] = str(candidate.resolve())
        self._refresh_slicer_target_label()
        self.status.set(f"Using custom {application} executable. Click Save Settings to remember this version.")

    def reset_slicer_executable(self):
        """Return this application to automatic installed-slicer lookup."""
        self.slicer_executable_paths[self._current_slicer_executable_key()] = ""
        self._refresh_slicer_target_label()
        self.status.set("Using automatic slicer discovery. Click Save Settings to remember this choice.")

    def open_validated_output(self, output, application):
        """Open the validated 3MF in the chosen slicer, not the OS default viewer."""
        output = str(Path(output).expanduser().resolve())
        if application not in ("Bambu Studio", "OrcaSlicer"):
            messagebox.showerror("Unknown slicer", f"Unsupported output application: {application}")
            return

        if os.name == "nt":
            key = ("bambu_studio_executable" if application == "Bambu Studio"
                   else "orcaslicer_executable")
            configured = self.slicer_executable_paths.get(key, "")
            if configured:
                executable = Path(configured)
                if not executable.is_file():
                    messagebox.showwarning(
                        "Selected slicer unavailable",
                        f"The selected executable no longer exists:\n{configured}\nChoose a replacement executable.",
                        parent=self,
                    )
                    self.choose_slicer_executable()
                    configured = self.slicer_executable_paths.get(key, "")
                    executable = Path(configured) if configured else None
                    if executable is None or not executable.is_file():
                        return
            else:
                executable = find_windows_slicer(application)
            if executable is None:
                # Portable or custom-location installations are common. This
                # dialog must run on Tk's main thread, not the conversion worker.
                selected = filedialog.askopenfilename(
                    parent=self,
                    title=f"Locate {application} executable",
                    filetypes=[("Windows applications", "*.exe"), ("All files", "*.*")],
                )
                if not selected:
                    messagebox.showwarning(
                        f"{application} not found",
                        "The output 3MF was saved successfully, but the selected slicer "
                        "could not be located. You can open the file from the slicer manually.",
                        parent=self,
                    )
                    return
                executable = Path(selected)
                if not executable.is_file():
                    messagebox.showerror("Invalid slicer path", "The selected executable does not exist.", parent=self)
                    return
            try:
                subprocess.Popen([str(executable), output], cwd=str(executable.parent))
            except OSError as error:
                messagebox.showerror(
                    f"Could not open {application}",
                    f"The 3MF was saved, but the slicer could not be launched:\n{error}",
                    parent=self,
                )
            return

        # On macOS, force the chosen application instead of the default viewer.
        app_names = ("BambuStudio", "Bambu Studio") if application == "Bambu Studio" else ("OrcaSlicer", "Orca Slicer")
        for app_name in app_names:
            lookup = subprocess.run(["open", "-Ra", app_name], capture_output=True)
            if lookup.returncode == 0:
                try:
                    subprocess.Popen(["open", "-a", app_name, output])
                except OSError as error:
                    messagebox.showerror(f"Could not open {application}", str(error), parent=self)
                return
        messagebox.showwarning(
            f"{application} not found",
            "The output 3MF was saved successfully, but the selected slicer "
            "could not be found. Open the file manually in your slicer.",
            parent=self,
        )


if __name__ == "__main__":
    StudioApp().mainloop()

# Native output-colors/thumbnail patch v1

# Palette and Orca H2C warning patch v2
