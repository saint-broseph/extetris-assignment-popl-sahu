"""
tk_adapter.py -- Tkinter front end for the headless Engine (v1 core, layer 5).

This is the ONLY module in v1_core_system that imports tkinter.

    python v1_core_system/tk_adapter.py [--variant variants/x.toml] [--seed N]

Fixes for the starter's UI bugs:
  * One repeating timer. TkinterController owns a single after() loop, and start()
    cancels any existing one first. Pause is an engine mode, not a timer, so timers
    can never stack (v0 BUG-03).
  * Game over is a mode. An overlay is drawn, the window stays open, and New Game works (BUG-05).
  * Dialogs pause the game and restore the previous mode afterwards (BUG-04, BUG-16).
  * The board is a Canvas of rectangles: nothing editable, no emoji-width glyphs (BUG-12, 22).
  * A next-piece preview, plus Save/Load that use the engine's hashed JSON format.
  * The constructor does not call mainloop(); run() does (BUG-15).
"""
from __future__ import annotations

import argparse
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from engine import Engine, SaveError, load_spec
from state import Action, Mode

__all__ = ["TkinterRenderer", "TkinterController", "main"]

THEMES = {
    "dark": {"bg": "#14161c", "grid": "#22252e", "block": "#4f8cff", "active": "#ffb347",
             "ghost": "#3a3f4d", "text": "#e8e8e8", "overlay": "#000000"},
    "light": {"bg": "#f4f4f4", "grid": "#dddddd", "block": "#2f6fdf", "active": "#e07b00",
              "ghost": "#c8c8c8", "text": "#202020", "overlay": "#ffffff"},
}


class TkinterRenderer:
    """Draws the engine's state on Canvas widgets. Read-only: it never changes the engine."""

    def __init__(self, root: tk.Misc, engine: Engine) -> None:
        ui = engine.config["ui"]
        self.cell = int(ui.get("cell_px", 28))
        self.colors = THEMES.get(ui.get("theme", "dark"), THEMES["dark"])
        self.show_ghost = bool(ui.get("show_ghost", True))
        r = engine.rules
        self.board = tk.Canvas(root, width=r.width * self.cell, height=r.height * self.cell,
                               bg=self.colors["bg"], highlightthickness=0)
        self.side = tk.Canvas(root, width=6 * self.cell, height=r.height * self.cell,
                              bg=self.colors["bg"], highlightthickness=0)
        self.board.pack(side=tk.LEFT)
        self.side.pack(side=tk.LEFT, fill=tk.Y)

    def _rect(self, canvas, r, c, color, size=None, ox=0, oy=0, outline=None):
        s = size or self.cell
        x, y = ox + c * s, oy + r * s
        canvas.create_rectangle(x + 1, y + 1, x + s - 1, y + s - 1, fill=color,
                                outline=outline or color)

    def draw(self, engine: Engine) -> None:
        st, col = engine.state, self.colors
        self.board.delete("all")
        for r in range(engine.rules.height):
            for c in range(engine.rules.width):
                self._rect(self.board, r, c, col["bg"], outline=col["grid"])
        if self.show_ghost:
            for r, c in engine.ghost_cells():
                self._rect(self.board, r, c, col["ghost"])
        for r, c in st.board.filled:
            self._rect(self.board, r, c, col["block"])
        for r, c in engine.active_cells():
            self._rect(self.board, r, c, col["active"])
        self.side.delete("all")
        s = self.cell
        lines = [f"Score  {st.score}", f"Lines  {st.lines}", f"Level  {st.level}",
                 f"Speed  {engine.level_policy.gravity_ms(st.level)} ms", "", "Next"]
        for i, text in enumerate(lines):
            self.side.create_text(8, 10 + i * 20, text=text, anchor="nw", fill=col["text"],
                                  font=("Helvetica", 11, "bold" if i == 5 else "normal"))
        small, y = max(8, s // 2), 10 + len(lines) * 20
        for piece in st.queue[: engine.rules.preview]:
            for r, c in piece.cells:
                self._rect(self.side, r, c, col["block"], size=small, ox=12, oy=y)
            y += (piece.height + 1) * small
        if st.mode in (Mode.PAUSED, Mode.GAME_OVER):
            w, h = engine.rules.width * s, engine.rules.height * s
            self.board.create_rectangle(0, h // 2 - 40, w, h // 2 + 40, fill=col["overlay"], stipple="gray50")
            msg = "PAUSED  (P)" if st.mode is Mode.PAUSED else f"GAME OVER\nscore {st.score}\nGame > New Game"
            self.board.create_text(w // 2, h // 2, text=msg, fill=col["text"], justify="center",
                                   font=("Helvetica", 16, "bold"))


class TkinterController:
    """Owns the only clock and the input mapping; drives the Engine and the renderer."""

    def __init__(self, engine: Engine, root: tk.Tk | None = None, *, spec=None, player=None,
                 frame_ms: int = 16) -> None:
        self.engine, self.spec, self.player = engine, spec, player
        self.root = root or tk.Tk()
        self.root.title(f"ExTetris - {engine.config['variant'].get('name', 'variant')}")
        self.root.resizable(False, False)
        self.frame_ms = frame_ms
        self._after_id: str | None = None
        self._last = time.monotonic()
        self.renderer = TkinterRenderer(self.root, engine)
        self._build_menu()
        self._bind_keys()

    # -- setup --------------------------------------------------------------------------
    def _build_menu(self) -> None:
        bar = tk.Menu(self.root)
        game = tk.Menu(bar, tearoff=False)
        game.add_command(label="New Game", command=self.new_game)
        game.add_command(label="Pause / Resume (P)", command=lambda: self.act(Action.PAUSE))
        game.add_separator()
        game.add_command(label="Save...", command=self.save_dialog)
        game.add_command(label="Load...", command=self.load_dialog)
        game.add_separator()
        game.add_command(label="Quit", command=self.quit)
        bar.add_cascade(label="Game", menu=game)
        bar.add_command(label="About", command=self.about)
        self.root.config(menu=bar)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

    def _bind_keys(self) -> None:
        keys = self.engine.config["ui"]["keys"]
        mapping = {"move_left": Action.MOVE_LEFT, "move_right": Action.MOVE_RIGHT,
                   "rotate_cw": Action.ROTATE_CW, "rotate_ccw": Action.ROTATE_CCW,
                   "soft_drop": Action.SOFT_DROP, "hard_drop": Action.HARD_DROP, "pause": Action.PAUSE}
        for name, action in mapping.items():
            key = keys.get(name)
            if key:
                seq = f"<{key}>" if len(key) > 1 else key
                self.root.bind(seq, lambda _e, a=action: self.act(a))

    # -- the single loop ----------------------------------------------------------------------
    def start(self) -> None:
        if self._after_id is not None:              # never two loops
            self.root.after_cancel(self._after_id)
        self._last = time.monotonic()
        self._after_id = self.root.after(self.frame_ms, self._frame)

    def _frame(self) -> None:
        now = time.monotonic()
        self.engine.tick((now - self._last) * 1000.0)
        self._last = now
        self.renderer.draw(self.engine)
        self._after_id = self.root.after(self.frame_ms, self._frame)

    def run(self) -> None:
        self.start()
        self.root.mainloop()

    def act(self, action: Action) -> None:
        self.engine.apply_action(action)
        self.renderer.draw(self.engine)

    # -- dialogs: pause around them and restore the previous mode ------------------------------
    def _paused_dialog(self, fn):
        was_running = self.engine.state.mode is Mode.RUNNING
        if was_running:
            self.engine.apply_action(Action.PAUSE)
        try:
            return fn()
        finally:
            if was_running and self.engine.state.mode is Mode.PAUSED:
                self.engine.apply_action(Action.PAUSE)
            self._last = time.monotonic()            # dialog time does not count as game time
            self.renderer.draw(self.engine)

    def new_game(self) -> None:
        self.engine.reset()
        self.renderer.draw(self.engine)

    def about(self) -> None:
        self._paused_dialog(lambda: messagebox.showinfo(
            "About ExTetris", "ExTetris v1 - CS F301 PoPL assignment.\nBuilt on the headless ExTetris engine.",
            parent=self.root))

    def save_to(self, path: str | Path) -> None:
        Path(path).write_text(self.engine.save(), encoding="utf-8")

    def load_from(self, path: str | Path) -> None:
        engine = Engine.resume(Path(path).read_text(encoding="utf-8"), self.spec, player=self.player)
        if (engine.rules.width, engine.rules.height) != (self.engine.rules.width, self.engine.rules.height):
            raise SaveError("board size differs from the running variant")
        self.engine = engine
        self.renderer.draw(self.engine)

    def save_dialog(self) -> None:
        def go():
            path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".json",
                                                filetypes=[("ExTetris save", "*.json")])
            if path:
                self.save_to(path)
        self._paused_dialog(go)

    def load_dialog(self) -> None:
        def go():
            path = filedialog.askopenfilename(parent=self.root, filetypes=[("ExTetris save", "*.json")])
            if path:
                try:
                    self.load_from(path)
                except (SaveError, OSError) as exc:
                    messagebox.showerror("Cannot load", str(exc), parent=self.root)
        self._paused_dialog(go)

    def quit(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.root.destroy()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Play an ExTetris variant")
    ap.add_argument("--variant", help="variant file (.toml or .json); default: classic")
    ap.add_argument("--seed", type=int)
    args = ap.parse_args(argv)
    spec = load_spec(args.variant) if args.variant else {}
    engine = Engine(spec, seed=args.seed)
    TkinterController(engine, spec=spec).run()


if __name__ == "__main__":
    main()
