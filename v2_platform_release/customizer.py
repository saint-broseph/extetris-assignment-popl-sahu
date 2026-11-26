"""
customizer.py -- in-game Variant Customizer dialog (used by `cli.py play`).

The designer changes live settings while the game is paused. Every change goes
through Engine.request_update(): it is validated immediately and takes effect at the
next tick boundary. "Save as variant..." writes a new .toml that includes the changes.
Board size cannot change mid-game; edit the .toml for that.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from spec import TRIGGER_TARGETS, SpecError, VariantSpec
from state import ConfigError

__all__ = ["VariantCustomizer", "attach_customizer"]

FIELDS = [  # (designer path, label, widget kind, options)
    ("board.walls", "Walls", "choice", ("solid", "wrap")),
    ("physics.gravity", "Line-clear gravity", "choice", ("naive_drop", "cascade")),
    ("physics.rotation", "Rotation", "choice", ("both", "cw_only", "none")),
    ("physics.kicks", "Wall kicks", "bool", None),
    ("physics.hard_drop_locks", "Hard drop locks at once", "bool", None),
    ("physics.preview", "Next pieces shown", "int", (1, 6)),
    ("levels.base_ms", "Starting fall time (ms)", "int", (100, 3000)),
    ("levels.lines_per_level", "Lines per level", "int", (1, 50)),
]


class VariantCustomizer:
    def __init__(self, controller, spec: VariantSpec):
        self.controller, self.spec, self.changes = controller, spec, {}

    def _current(self, path: str):
        engine = self.controller.engine
        section, key = TRIGGER_TARGETS[path].split(".")
        return getattr(engine.rules if section == "rules" else engine.level_policy, key)

    def open(self) -> None:
        self.controller._paused_dialog(self._dialog)

    def _dialog(self) -> None:
        root = self.controller.root
        win = tk.Toplevel(root)
        win.title(f"Customize - {self.spec.name}")
        win.transient(root)
        vars_ = {}
        for row, (path, label, kind, opts) in enumerate(FIELDS):
            ttk.Label(win, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=3)
            value = self._current(path)
            if kind == "choice":
                var = tk.StringVar(value=value)
                ttk.Combobox(win, textvariable=var, values=opts, state="readonly", width=12).grid(row=row, column=1, padx=8)
            elif kind == "bool":
                var = tk.BooleanVar(value=value)
                ttk.Checkbutton(win, variable=var).grid(row=row, column=1, sticky="w", padx=8)
            else:
                var = tk.IntVar(value=int(value))
                ttk.Spinbox(win, from_=opts[0], to=opts[1], textvariable=var, width=10).grid(row=row, column=1, padx=8)
            vars_[path] = var
        ttk.Label(win, text="Board size: edit the .toml file (needs a new game).",
                  foreground="gray").grid(row=len(FIELDS), column=0, columnspan=2, padx=8, pady=4)

        def collect() -> dict:
            out = {}
            for path, var in vars_.items():
                v = var.get()
                if v != self._current(path):
                    out[path] = v
            return out

        def apply(close: bool = True) -> bool:
            try:
                changes = collect()
                for path, v in changes.items():
                    self.controller.engine.request_update(TRIGGER_TARGETS[path], v)
                self.changes.update(changes)
            except (ConfigError, tk.TclError) as exc:
                messagebox.showerror("Cannot apply", str(exc), parent=win)
                return False
            if close:
                win.destroy()
            return True

        def save_as() -> None:
            if not apply(close=False):
                return
            try:
                new_spec = self.spec.with_changes(self.changes)
            except SpecError as exc:
                messagebox.showerror("Invalid variant", str(exc), parent=win)
                return
            path = filedialog.asksaveasfilename(parent=win, defaultextension=".toml",
                                                initialfile=f"{self.spec.slug}_custom.toml",
                                                filetypes=[("Variant", "*.toml")])
            if path:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(new_spec.to_toml())
                messagebox.showinfo("Saved", f"Variant saved to\n{path}", parent=win)

        buttons = ttk.Frame(win)
        buttons.grid(row=len(FIELDS) + 1, column=0, columnspan=2, pady=8)
        ttk.Button(buttons, text="Apply", command=apply).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Save as variant...", command=save_as).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side=tk.LEFT, padx=4)
        win.grab_set()
        root.wait_window(win)


def attach_customizer(controller, spec: VariantSpec) -> VariantCustomizer:
    """Add a 'Variant > Customize...' menu to a running TkinterController."""
    customizer = VariantCustomizer(controller, spec)
    menubar = controller.root.nametowidget(controller.root["menu"])
    menu = tk.Menu(menubar, tearoff=False)
    menu.add_command(label="Customize...", command=customizer.open)
    menubar.add_cascade(label="Variant", menu=menu)
    return customizer
