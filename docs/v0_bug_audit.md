# ExTetris v0 — Starter Code Extraction & Bug Audit

Baseline: the four listings in Appendices A–D of *Extended Tetris Design and Development* (CS F301 PoPL, Sem-I 2026-27), extracted into `v0/` with **no behavioural changes**. Line numbers below are the PDF's own listing numbers, and they match the line numbers of the files in `v0/` exactly (engine.py 253, board.py 97, shape.py 69, allextetrominoes.py 116 lines).

Each runtime claim has a reproduction in `tests/`. The ID in brackets (e.g. `[B1]`, `[G3]`) points to the section of the script that shows it:

```
python3 tests/repro_v0_logic.py                 # board / shape / distribution / arithmetic
xvfb-run -a python3 tests/repro_v0_gui.py       # Tk event-loop bugs (drop xvfb-run on a desktop)
```

Run v0 with `python3 v0/engine.py` (needs `numpy` ≥ 1.17 and `tkinter`). Answer `0` at the prompt for the classic 7 pieces.

---

## 1. Extraction / OCR artefacts (fixed during extraction, not bugs in the code)

| # | Artefact in the PDF | What was done |
|---|---|---|
| X-1 | The PDF text layer letter-spaces identifiers and interleaves the line-number gutter (`e x t e t r o m i n o _ d i s t r i b u t i o n`, `m ov e _d ow n _f or ce`). Copy-pasting from the PDF does not give runnable code. | Rebuilt every line from glyph x-positions on the monospace grid. Cross-checked against the rendered pages. |
| X-2 | 72 typographic `’` in place of `'` (every single-quoted string and every `'''` docstring). These are a `SyntaxError` if pasted. | Normalised to ASCII `'`. No other non-ASCII characters exist in the code (the `⬛` is written as the escape `\N{BLACK LARGE SQUARE}`). |
| X-3 | Plain text extraction loses indentation (the code uses 2-space indents). | Recovered from x-coordinates. |
| X-4 | 30 listing lines are wrapped. **engine.py** comment wraps at L26, 29–31, 38, 47–49, 56–57, 59, 62, 65, 73–74. Three wraps fall mid-code: **L80** (`self.cursor` / `[1]] = True`), **L128** (`area[row` / `])]`), and **L226**, which breaks *inside the string literal* `"*.txt"`. Rejoining L226 with a space would silently change the file filter to `" *.txt"`. **allextetrominoes.py** wraps at L87–91 and L96–102. | Comments rejoined with a space. Code rejoined with no space, except after a trailing comma. |
| X-5 | Data check: all 73 matrices have exactly 4 cells, are 8-connected and have tight bounding boxes, so no `True`/`False` was corrupted. All four files compile on Python 3.12. | — |
| X-6 | `self.pasueStatus` (engine L184) looks like an OCR slip but is **in the typeset listing** (checked on the rendered page). | Kept as-is: it is a real bug (BUG-04). |

---

## 2. Runtime bugs

Severity: **H** = breaks gameplay or crashes · **M** = wrong behaviour or latent crash · **L** = quality or maintainability.

### BUG-01 (H) Left wall is porous: negative indices wrap around — `board.py` L45–53, effects at `engine.py` L80 and `board.py` L38
`collision()` relies on `IndexError` to detect the walls (L52–53). A negative column (`cx + off_x = -1`) does not raise: Python/numpy index `-1` is the **last** column. If that cell is empty, `collision()` returns `False` and the move is allowed. The piece walks off the left edge. `render()` (engine L80) then draws it wrapped onto the right edge, and on locking `insertShape()` (board L38) writes the blocks into the right-hand columns. The right wall and the floor only work because they *do* raise `IndexError`.
Repro `[B1]` gives `collision(I, (5,-1)) == False`. Locking at x = −2 produces the row `##......##`. Repro `[G5]`: 6 Left presses give cursor `(0,-2)`, rendered as `⬛|⬛| | | | | | |⬛|⬛|`.

### BUG-02 (H) Rotation corrupts shared piece templates (aliasing) — `engine.py` L88–89, L98–99, L208; `shape.py` L29–37, L39–40; `allextetrominoes.py` L104, L116
Nothing is ever copied:
- `get_any_extetromino()` returns the module-global array itself.
- `Shape(mat)` stores that same object.
- `rotate_CW` builds `Shape(self.piece.matrix)`, which is again the same object.
- `flipud()` swaps rows **in place**, and `transpose()` returns a **view** of the same memory.

Consequences:
1. **Every rotation permanently rewrites the global `ExtetrominoN`.** After one rotation of an S, `Extetromino6` *is* the Z, so every later "S" spawns as a Z. L becomes J the same way. `[S1]`
2. **A rejected rotation still mutates the live piece.** `flipud()` runs before the collision test, so a blocked rotation leaves the current piece flipped upside-down, i.e. turned into its mirror image (L becomes J). `[S2]`
3. As a result, the effective piece distribution drifts during a game (see BUG-11).

### BUG-03 (H) Pause bug: Down while paused spawns extra, permanent gravity loops — `engine.py` L53, L119–125, L151–152
`move_down_force` (bound to `<Down>`) has no `pauseStatus` guard. It calls `move_down_step(True)`. The paused branch (L123–125) then schedules a fresh, **non-accelerated** `move_down_step()`, which reschedules itself forever, so every Down press during a pause adds one more gravity loop. After resuming, the piece falls N times faster. New Game (L212–223) does not cancel the loops.
Repro `[G1]`: 5 presses while paused take the pending timers from 2 to 7, and the game then makes **18 gravity ticks in 3 s instead of 3**. `[G2]`: still 7 timers after New Game.

### BUG-04 (H) About dialog leaves the game permanently paused — `engine.py` L184 (also L169)
`self.pasueStatus = False` is a typo. It creates a new attribute and `pauseStatus` stays `True`, so the help text stays on the board and the game is frozen until the user finds Pause in the menu. Even with the typo fixed, the method unconditionally unpauses, which would resume a game the player had paused on purpose.
Repro `[G3]`: `pauseStatus == True`, stray `pasueStatus == False`, help text still displayed.

### BUG-05 (H) Game-over handling is broken in five ways — `engine.py` L141–150, L65, L154–160, L213
1. `update_step` keeps running during the modal dialog and overwrites the "Game Over" board **within 100 ms**. `[G6]`: the message is present when the dialog opens and gone at t = 0.02 s.
2. Any other live gravity loop keeps firing during the modal dialog, stamps more pieces and opens a **second, nested "Game Over!" dialog**. This happens whenever game over is triggered with the Down key, or when BUG-03 loops exist. `[G6]`: 2 dialogs open at t = 2.6 s.
3. L150 `window.quit()` ends the program, so "New Game" after a game over is impossible.
4. `game_over_status` (L65) is never set to `True`, so the check at L213 is dead code. `[G6]`
5. L146 `.strip()` removes the leading space of rows that start with an empty cell, so the final board is shifted one column left on those rows.

### BUG-06 (H) Speed-up threshold is skipped — `engine.py` L138
`if not(self.deleted_lines % 100)` fires only when the running total lands **exactly** on a multiple of 100. Multi-row clears jump over it: 98 + 4 = 102 gives no speed-up. A player who always clears 3 rows never speeds up (249 lines, 0 speed-ups). `[E1]` The 100-line threshold also means the game effectively never speeds up in normal play.
Correct test: `old // 100 != new // 100`, applying `new//100 - old//100` speed-ups.

### BUG-07 (M) Speed has no lower bound, and 0 ms is irreversible — `engine.py` L162–166, L196–197
50 clicks of "Speed-Up" take `move_down_duration` to 0. That gives `after(0, …)`, a busy loop that starves the UI. `slow_down()` cannot recover, because `ceil(0 × 1.1) = 0`. Only New Game resets it. `[E2]`

### BUG-08 (M) `eval()` in the entry point, with no input validation — `engine.py` L253
`eval('int(input("How many EXtetrominoes? "))+8')` evaluates a **constant string**, so it is equivalent to `int(input(...)) + 8`. The `eval` adds nothing and hides intent. (The typed text goes through `int()`, so this particular call is not an injection vector.) There is no validation:
- non-integer input gives a `ValueError` traceback;
- N ≤ −7 gives an empty range, so `randint(0)` raises `ValueError` at the first spawn;
- N ≥ 67 gives a `NameError` at some *random later* spawn, when an index ≥ 74 is drawn.

The prompt is also ambiguous: N means "extra pieces beyond the classic 7", because `range(1, N+8)` holds N + 7 pieces.

### BUG-09 (M) `eval()` as a variable lookup — `allextetrominoes.py` L103–104, L116 (also `board.py` L83, `shape.py` L63 in test code)
`eval("Extetromino"+str(i))` is a name lookup done by parsing code. Index 0 or ≥ 74 raises `NameError`. If an index is ever a string (for example from a config file or user input in the redesigned API), it is **arbitrary code execution**: `[X1]` runs an injected `print`. It also re-parses on every spawn. A tuple or dict of shapes is the fix.

### BUG-10 (M) Documented "uniform" usage crashes at random — `allextetrominoes.py` L113 (and L27)
The docstring says uniform sampling is "achieved by just `range(count)`". `range(count)` includes **0**, so it raises `NameError: Extetromino0` on about 1/count of spawns. It also drops the last piece. Correct usage is `range(1, count+1)`. `[X1]`

### BUG-11 (M) Distribution bias — `allextetrominoes.py` L30–102 (esp. L39–40, L52); `engine.py` L26–31; L116
Sampling is uniform over **indices**, but indices do not correspond one-to-one with distinct pieces:
- **Exact duplicates:** `Extetromino1`, `10` and `11` are the same I piece. The I is 3× as likely over `range(1,74)`, and already 2/10 once N ≥ 3. `[D1]`
- **Same piece, different stored orientation:** the 73 entries are only **34 distinct pieces** under rotation. That is exactly the complete set of 34 one-sided 4-cell king-connected pieces, so coverage is complete, but each piece is listed 1, 2, 3 or 4 times:

  | Multiplicity | Pieces | P(each) over `range(1,74)` | Index groups |
  |---|---|---|---|
  | ×4 | 8 | 4/73 ≈ 5.5 % | {25,38,50,54} {26,43,46,53} {27,33,39,57} {28,30,37,56} {29,34,48,52} {31,36,41,55} {32,40,45,49} {35,42,47,51} |
  | ×3 | 1 (I) | 3/73 ≈ 4.1 % | {1,10,11} |
  | ×2 | 13 | 2/73 ≈ 2.7 % | {6,23} (S, with 23 = vertical S) {8,9} {12,18} {13,20} {15,21} {17,19} {22,24} {58,61} {60,62} {63,66} {67,70} {69,71} {72,73} |
  | ×1 | 12 | 1/73 ≈ 1.4 % | the rest |

  That is a **4 : 1 skew** between the most and least frequent pieces, decided by how an Octave enumeration happened to emit orientations, not by design.
- The only control is repeating indices in a list (engine L29–31 comment), which is what the spec asks you to replace.
- It uses the global, unseeded `numpy.random`, so games are not reproducible or testable.
- BUG-02 makes the realised distribution drift during play.

### BUG-12 (M) The board is an editable text box — `engine.py` L36–44 (state never set to disabled), L225–230
Clicking and typing inserts characters into the board. While paused, the edits persist, and "Save state" writes them out. When the board has keyboard focus, the arrow keys and Space trigger the Text widget's own class bindings as well as the window bindings. `[G4]`

### BUG-13 (M) `tk.simpledialog` is never imported — `engine.py` L149, L183
It works only because `from tkinter import filedialog` (L18) happens to import `tkinter.simpledialog` internally. That holds in current CPython 3.8+ branches but not in 3.7 and earlier, where both the Game Over and About paths raise `AttributeError`. `[G0]` Also, `simpledialog.Dialog` is an abstract base: it shows an empty body with OK/Cancel and no message.

### BUG-14 (M) `numpy` is used but never imported in engine.py — `engine.py` L137, L163, L166, L215 (relies on L20)
The name only exists because `from allextetrominoes import *` leaks the module. Adding an `__all__` to allextetrominoes would break the engine.

### BUG-15 (M) The constructor never returns — `engine.py` L71
`__init__` calls `self.window.mainloop()`, so `TetrisEngine(...)` blocks until the window closes. An application programmer cannot construct, configure or subclass-then-start an engine, and `tetris_engine` at L253 is only bound after the game ends. This directly blocks the assignment's "API for game programmers" goal.

### BUG-16 (M) "Save state" is not a state save — `engine.py` L199, L225–230
It writes whatever text is in the widget, which may be help text (BUG-04) or user edits (BUG-12). There is no Load. **The game keeps running behind the modal file dialog**: `[G8]` shows the piece falling from row 0 to row 2 while the dialog is open. `asksaveasfilename` is also called without `parent=self.window`. The window title changes to an inconsistent "Python Tetris Board - …".

### BUG-17 (L) Dead or unsafe movement paths — `engine.py` L96–104, L232–240
`rotate_AntiCW` is never bound to a key. The `'UP'` direction is never used. An unknown direction leaves `offset` unbound and raises `UnboundLocalError`.

### BUG-18 (L) New Game side effects — `engine.py` L212–223
It unconditionally unpauses (L223), has a dead game-over check (L213), and keeps extra timer loops (BUG-03).

### BUG-19 (L) Menu issues — `engine.py` L190–205
"Exit" and "Quit" duplicate each other (L201, L203). The default tear-off line is shown. The "Pause" label never changes to "Resume". There is no keyboard shortcut for pause.

### BUG-20 (L) Shape constructor — `shape.py` L19–23
The default argument is one shared mutable array (`Shape().matrix is Shape().matrix`), which combines badly with BUG-02. `[S3]` The type check is a string comparison of `type()`, which rejects lists and ndarray subclasses (`[S4]`) and raises a bare `Exception`.

### BUG-21 (L) Lint — `engine.py` L22–23, L77, L139, L219
Unused imports (`time`, `sleep`, `copy`), an unused local `piece`, and redundant cursor resets (`new_piece()` already does it).

### BUG-22 (L) Glyph mismatch and wrap risk — `board.py` L29, `shape.py` L54, `engine.py` L38
The board uses ⬛ U+2B1B, an emoji-width glyph, while `Shape.__str__` uses □ U+25A1. With wrap=CHAR and a 20-character-wide widget, a font whose ⬛ is wider than one cell will wrap rows (the author's own L38 comment flags this). **Not reproduced here**: the fallback font measured equal widths, so this is platform-dependent.

### BUG-23 (L) Test harness issues — `board.py` L56–79; `shape.py` L59–69
`while(i+j)` exits on any pair that sums to 0, e.g. (3, −3). Negative i or j wrap (BUG-01). `shape0` is unused. The shape self-test's rotations mutate the global templates (BUG-02).

---

## 3. Behaviours to decide on (not bugs as such)
- **Hard drop does not lock** (`engine.py` L114–117). The piece can still slide left or right until the next gravity tick (up to 1 s).
- **Rotation has no pivot or wall kicks** (`engine.py` L86–104). Pieces rotate about the bounding-box top-left, so they jump, and an I against the right wall cannot rotate.
- **Full redraw plus `deepcopy` every 100 ms** (`engine.py` L75–81, L154–160). It works, but it is wasteful and can flicker.
- `width`/`height` are hard-coded in `__init__` (L34–35) despite the "programmable" comments.

## 4. Verified correct (do not "fix")
- **Multi-row clearing** (`engine.py` L128–137), including non-adjacent rows: processing full rows top-down keeps lower indices valid. `[G7]` clears rows 17 and 19 and matches a reference implementation exactly.
- **`rotateCW` / `rotateAntiCW` maths** (`shape.py` L42–48): flipud+transpose is CW and transpose+flipud is ACW. The problem is only the aliasing (BUG-02).
- **Right-wall and floor collision** (via `IndexError`).
