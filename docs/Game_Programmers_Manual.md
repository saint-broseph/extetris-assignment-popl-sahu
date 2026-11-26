# ExTetris — Game Programmer's Manual

*For game designers. No programming needed.*

You design a falling-block game by writing a short settings file called a **variant** (`.toml`). The ExTetris platform checks it, lets you play it, measures how hard it is, and packages it as a game you can share. This manual shows you how.

---

## Contents
1. [Before you start](#1-before-you-start)
2. [The five commands](#2-the-five-commands)
3. [Your first variant in 5 minutes](#3-your-first-variant-in-5-minutes)
4. [The pieces](#4-the-pieces)
5. [Landing holes, explained](#5-landing-holes-explained)
6. [`variant.toml` reference](#6-varianttoml-reference)
7. [Special events (triggers)](#7-special-events-triggers)
8. [When the validator complains](#8-when-the-validator-complains)
9. [The Variant Designer Studio notebook](#9-the-variant-designer-studio-notebook)
10. [Advanced appendix: extending ExTetris in Python](#10-advanced-appendix-extending-extetris-in-python)

---

## 1. Before you start

- Install **Python 3.11 or newer**, then run this once: `python -m pip install numpy` (add `pytest` if you want to run the tests).
- Open a terminal (Windows: *Command Prompt*) **in the project folder** `extetris-popl-sahu`.
- The commands are long, so make a short name for them:

| System | Type this once per terminal |
|---|---|
| Windows | `doskey extetris=python v2_platform_release\cli.py $*` |
| macOS / Linux | `alias extetris="python3 v2_platform_release/cli.py"` |

The rest of this manual writes `extetris ...`. Without the short name, type `python v2_platform_release/cli.py ...` instead.

---

## 2. The five commands

| Command | What it does | Example |
|---|---|---|
| `extetris new "<name>"` | Creates `variants/<name>.toml` from a template (`--template classic`, `chaos`, `zen` or `blank`) | `extetris new "Rainy Day" --template zen` |
| `extetris validate <file>` | Checks the file and explains every problem in plain English. Prints a summary if it is OK. | `extetris validate variants/rainy_day.toml` |
| `extetris play <file>` | Opens the game window. Use **Variant → Customize…** to change rules while playing, and **Save as variant…** to keep the changes. | `extetris play variants/rainy_day.toml --customize` |
| `extetris simulate <file> --games 100` | A computer player plays 100 games with no window and reports game length, lines, score, piece frequencies and a verdict (HARD / BALANCED / EASY) | `extetris simulate variants/rainy_day.toml --games 100` |
| `extetris package <file>` | Builds `dist/<name>-<version>.zip` containing everything a player needs: double-click `run.bat` (Windows) or `./run.sh` | `extetris package variants/rainy_day.toml --pyinstaller` |

There is also an extra command, `extetris pieces --preset Full`, which lists every piece name with a picture.

**In-game keys** (change them in `[controls]`): **←/→** move, **↑** rotate clockwise, **z** rotate anticlockwise, **↓** soft drop, **Space** hard drop, **p** pause. The **Game** menu has New Game, Save, Load and Quit.

---

## 3. Your first variant in 5 minutes

```
extetris new "Rainy Day" --template classic       1. create  -> variants/rainy_day.toml
(open the file in Notepad / any text editor)      2. edit    -> e.g. preset = "Extended-Easy"
extetris validate variants/rainy_day.toml         3. check   -> "OK ... is a valid variant."
extetris simulate variants/rainy_day.toml --games 50   4. balance -> read the verdict
extetris play variants/rainy_day.toml             5. play
extetris package variants/rainy_day.toml          6. share   -> dist/rainy_day-0.1.zip
```

A complete small variant:

```toml
[variant]
name = "Rainy Day"
version = "1.0"
authors = ["Asha"]
description = "Easy extended pieces on a wide board."

[board]
width = 12
height = 22
walls = "solid"

[pieces]
preset = "Extended-Easy"
exclude = ["X2x3.H1112.+", "X2x3.H1112.-"]

[distribution]
kind = "bag"

[levels]
base_ms = 1100
lines_per_level = 12
```

Every section is optional. Anything you leave out uses the classic default.

---

## 4. The pieces

Every piece is made of **4 squares**. Classic Tetris joins squares only by their **edges**. ExTetris also allows squares that touch only at a **corner**. That gives exactly **34 different pieces** (counting a piece and its rotations as one). They are organised like a family tree:

```
                               Piece  (34)
                    ┌────────────┴─────────────┐
        Tetromino  (7)                     ExTetromino  (27)
   squares joined by edges         at least one corner-only contact
     I  O  T  S  Z  L  J          sorted by the box that fits the piece:
                                  ┌──────┬──────┬──────┬──────┬──────┐
                                  2x3    2x4    3x3    3x4    4x4
                                  (2)    (9)    (9)    (6)    (1)
```

**Piece names.**
- Classic pieces use their letter (`I O T S Z L J`).
- Extended pieces use a **code** that describes their shape. For example, `X3x3.H2233.+` means:
  - `X` = extended;
  - `3x3` = the size of its box;
  - `H2233` = landing holes in its four rotations (see §5);
  - `+` / `-` / `0` = handedness. `+` and `-` are mirror-image twins. `0` is a piece that looks the same in a mirror.
- Copy codes exactly from this catalogue or from `extetris pieces`.

**Presets** (`[pieces] preset = ...`):

| Preset | Pieces | What it is |
|---|---|---|
| `Classic` | 7 | The original tetrominoes |
| `Extended-Easy` | 15 | Every piece that can land on flat ground leaving **at most one hole** (marked `*` below) |
| `Full` | 34 | Everything |

**Complete catalogue** (`#` = square; shown in the orientation the piece appears in; `*` = in Extended-Easy):

```
Tetromino  (7 pieces)
  I *               O *               T *               S *               Z *               
  ####              ##                .#.               .##               ##.               
                    ##                ###               ##.               .##               

  L *               J *               
  ..#               #..               
  ###               ###               

ExTetromino2x3  (2 pieces)
  X2x3.H1112.+ *    X2x3.H1112.- *    
  #.#               ##.               
  ##.               #.#               

ExTetromino2x4  (9 pieces)
  X2x4.H1133.+ *    X2x4.H1133.- *    X2x4.H1233.- *    X2x4.H1332.+ *    X2x4.H2222.+      
  ...#              #...              ..#.              .#..              ..##              
  ###.              .###              ##.#              #.##              ##..              

  X2x4.H2222.-      X2x4.H2323.+      X2x4.H2323.0      X2x4.H2323.-      
  ##..              .#.#              #..#              #.#.              
  ..##              #.#.              .##.              .#.#              

ExTetromino3x3  (9 pieces)
  X3x3.H1144.0 *    X3x3.H1343.0 *    X3x3.H2233.+      X3x3.H2233.0      X3x3.H2233.-      
  #..               .#.               #..               .#.               #..               
  #..               .#.               .#.               ##.               ##.               
  .##               #.#               .##               ..#               ..#               

  X3x3.H2234.-      X3x3.H2243.+      X3x3.H2244.0      X3x3.H3333.0      
  .#.               #..               #..               .#.               
  #..               #.#               .#.               #.#               
  .##               .#.               #.#               .#.               

ExTetromino3x4  (6 pieces)
  X3x4.H3355.+      X3x4.H3355.-      X3x4.H4444.+      X3x4.H4444.-      X3x4.H4445.+      
  ...#              #...              ...#              #...              ..#.              
  ..#.              .#..              .##.              .##.              .#.#              
  ##..              ..##              #...              ...#              #...              

  X3x4.H4445.-      
  #...              
  .#.#              
  ..#.              

ExTetromino4x4  (1 pieces)
  X4x4.H6666.0      
  #...              
  .#..              
  ..#.              
  ...#
```

---

## 5. Landing holes, explained

A **hole** is an empty square trapped under a piece, which you can no longer fill from above. ExTetris measures it by dropping the piece onto a flat floor in each of its four rotations:

```
 L piece, 4 rotations, dropped on a flat floor        holes
   ..#                                                 0
   ###        sits flat, nothing trapped
  ------
   #.                                                  0
   #.
   ##
  ------
   ###        two empty squares under the arm          2
   #xx        x = hole
  ------
   ##                                                  2
   x#
   x#
  ------
 hole signature of L = (0, 0, 2, 2)
```

```
 X2x4.H2222.+   (an extended piece)
   ..##         every rotation traps 2 squares:  H2222
   ##..
```

**Why this matters to a designer.**
- Pieces whose smallest number is 0 can always land cleanly, so they are *friendly*.
- Pieces with big numbers (the 4x4 diagonal is `H6666`) create mess, so they are *hard*.
- `max_holes = 1` keeps only friendly pieces (that is how `Extended-Easy` is defined).
- The distribution rule `favor_few_holes` makes them more common.

---

## 6. `variant.toml` reference

TOML basics: `[section]` starts a group, `key = value` sets something, text goes in `"quotes"`, lists in `[ ]`, and `true`/`false` have no quotes. Lines starting with `#` are comments.

### `[variant]`: information about your game
| Key | Type | Example | Meaning |
|---|---|---|---|
| `name` | text | `"Corner Chaos"` | Shown in the title bar; also the package name |
| `version` | text | `"1.0"` | Shown in the package name |
| `authors` | list of text | `["Asha", "Ravi"]` | Credits |
| `description` | text | `"..."` | First line of the generated guide |

### `[board]`
| Key | Allowed | Default | Meaning |
|---|---|---|---|
| `width` | 4–64 | 10 | Columns |
| `height` | 8–128 | 20 | Rows |
| `walls` | `"solid"`, `"wrap"` | `"solid"` | `wrap` joins the left and right edges, so pieces slide off one side and appear on the other |

### `[pieces]`: which pieces appear
| Key | Allowed | Meaning |
|---|---|---|
| `preset` | `"Classic"`, `"Extended-Easy"`, `"Full"` | Starting set (default `Classic`) |
| `bbox` | `"2x4"` or a list like `["2x3", "3x3"]` | Keep only pieces with these box sizes |
| `connectivity` | `"edge"` or `"corner"` | Keep classic-only or extended-only pieces |
| `handedness` | `"+"`, `"-"`, `"0"`, `"chiral"`, `"achiral"` | Keep by mirror type |
| `max_holes` | 0–6 | Keep pieces that can land with at most this many holes |
| `include` | list of names | Add these pieces back after filtering |
| `exclude` | list of names | Remove these pieces at the end |

Order of operations: **preset → filters → include → exclude**. The result must not be empty.

### `[distribution]`: how often each piece appears
Probabilities are per **piece**, so every piece counts once whatever its shape.

| `kind` | Extra keys | Behaviour |
|---|---|---|
| `"uniform"` | none | All pieces equally likely |
| `"weighted"` | `weights = { I = 2.0, S = 0.5 }`, `default_weight = 1.0` | Your numbers; unlisted pieces get `default_weight` |
| `"by_property"` | `rule`, `strength` | Weight from a rule: `favor_few_holes`, `favor_classic`, `favor_small_bbox`, `favor_symmetric`, `uniform`. `strength` 0–10 sharpens it. |
| `"bag"` | `copies` 1–7 | Every piece appears `copies` times per round, in shuffled order (no long droughts) |
| `"adaptive"` | `base` (`uniform`/`bag`/`by_property`/`weighted`), `drought_boost` 0–20, `repeat_penalty` 0–1 | Pieces you haven't seen for a while become more likely; an immediate repeat is less likely |
| `"mixture"` | one or more `[[distribution.parts]]` blocks, each with `weight` and `kind` (+ that kind's keys) | Blend several distributions |

`seed = 1234` (optional) makes every game start with the same piece sequence, which is useful for contests.

```toml
[distribution]
kind = "mixture"
[[distribution.parts]]
weight = 0.8
kind = "bag"
[[distribution.parts]]
weight = 0.2
kind = "weighted"
weights = { I = 3.0 }
```

### `[levels]`: speed
| Key | Allowed | Default | Meaning |
|---|---|---|---|
| `base_ms` | 20–10000 | 1000 | Milliseconds per row at level 0 |
| `factor` | 0.01–1 | 0.9 | Each level multiplies the time by this (smaller = speeds up faster) |
| `lines_per_level` | 1–1000 | 10 | Lines needed per level |
| `min_ms` | 1–10000 | 50 | Speed never gets faster than this |
| `start_level` | 0–99 | 0 | Starting level |

Fall time = `base_ms × factor^level`, never below `min_ms`. Example: 1000, 900, 810, … ms.

### `[scoring]`
| Key | Default | Meaning |
|---|---|---|
| `line_points` | `[0, 100, 300, 500, 800]` | Points for clearing 0, 1, 2, 3, 4 lines at once (× level + 1) |
| `extra_line_points` | 300 | Per line beyond the list (cascades can clear more than 4) |
| `chain_bonus` | 50 | Per extra cascade step |
| `soft_drop`, `hard_drop` | 1, 2 | Points per row dropped |
| `level_multiplier` | `true` | Multiply clear points by (level + 1) |

### `[physics]`
| Key | Allowed | Default | Meaning |
|---|---|---|---|
| `gravity` | `"naive_drop"`, `"cascade"` | `naive_drop` | After a clear: rows simply drop, **or** loose groups fall and may clear more lines (chains) |
| `rotation` | `"both"`, `"cw_only"`, `"none"` | `both` | Which rotations are allowed |
| `kicks` | `true`/`false` | `true` | Rotation may shift the piece 1–2 columns to fit |
| `hard_drop_locks` | `true`/`false` | `true` | Hard drop locks at once, or lets you slide until the next fall step |
| `spawn_column` | `"center"` or a number | `"center"` | Where new pieces appear |
| `spawn_row` | number | 0 | Row where new pieces appear |
| `game_over` | `"block_out"`, `"top_rows"` | `block_out` | Lose when a new piece can't appear, **or** when a block locks in the top `danger_rows` |
| `danger_rows` | 0–20 | 2 | Used by `top_rows` |
| `preview` | 1–6 | 3 | Next pieces shown |

### `[theme]`
| Key | Allowed | Meaning |
|---|---|---|
| `name` | `"dark"`, `"light"`, `"retro"` | Colour scheme |
| `cell_px` | 10–64 | Square size in pixels |
| `show_ghost` | `true`/`false` | Show where the piece will land |
| `colors` | `{ bg, grid, block, active, ghost, text, overlay }` as `"#rrggbb"` | Override individual colours |

### `[controls]`
`move_left`, `move_right`, `rotate_cw`, `rotate_ccw`, `soft_drop`, `hard_drop`, `pause`. Values are key names such as `"Left"`, `"space"`, `"a"`.

---

## 7. Special events (triggers)

A trigger changes a rule **once**, when something happens in the game:

```toml
[[triggers]]
id = "bonus-cascade"                       # any unique name
when = { lines_at_least = 10 }             # condition(s), all must be true
set = { "physics.gravity" = "cascade" }    # what changes
```

| Conditions you can use | | Settings a trigger can change |
|---|---|---|
| `lines_at_least` | | `board.walls` |
| `level_at_least` | | `physics.gravity`, `physics.rotation`, `physics.kicks`, `physics.hard_drop_locks`, `physics.preview`, `physics.game_over`, `physics.danger_rows` |
| `score_at_least` | | `levels.base_ms`, `levels.factor`, `levels.lines_per_level`, `levels.min_ms` |
| `pieces_at_least` | | *(board size can never change mid-game)* |
| `tick_at_least` | | |

Changes take effect at the start of the next game step, never in the middle of a move. `extetris simulate` reports how often each trigger fired.

---

## 8. When the validator complains

`extetris validate` lists **every** problem at once. These are real messages and what to do about them:

| Message (shortened) | Fix |
|---|---|
| `In [board], I don't recognise 'widht'. Did you mean 'width'?` | Spelling. Use the suggested name. |
| `In [board], 'height' must be a whole number from 8 to 128 (you wrote 3).` | Value out of range |
| `I don't recognise the section [bord]. Did you mean 'board'?` | Section name typo |
| `In [pieces], 'exclude' contains unknown piece names ['Q'].` | Use a letter or a code from §4 / `extetris pieces` |
| `In [distribution], kind = "weighted" also needs 'weights'.` | Add the missing key for that kind |
| `In [levels], 'min_ms' (the fastest speed) cannot be slower than 'base_ms'.` | Make `min_ms` smaller than `base_ms` |
| `colour 'block' must look like "#4f8cff"` | Use `#` followed by 6 hex digits |
| `Trigger 1 ('x'): 'lines' is not a condition I can check.` | Use a condition from §7 (e.g. `lines_at_least`) |
| `Trigger 1 ('x'): the board size cannot change during a game.` | Remove `board.width`/`board.height` from `set` |
| `The game engine rejected this combination: the piece family is empty` | Your filters/excludes removed every piece |
| `The file is not valid TOML: ...` | Check for a missing `]`, a missing `=`, or unclosed `"` quotes |

**Warnings** (the variant is still valid) appear as `warning ...` in the summary, e.g. a starting speed under 200 ms.

**`play` / `package` refuse my file.** They run the same validator. Run `validate` first.

**Loading a save fails with "different variant".** A save file only loads into the exact variant it was made with. This protects against cheating and corruption.

---

## 9. The Variant Designer Studio notebook

`v2_platform_release/Variant_Designer_Studio.ipynb` works in Jupyter, VS Code or Google Colab. Run the cells from top to bottom and change only the lines marked `# @param` (Colab shows them as menus and sliders):

1. Choose pieces (preset, add/remove).
2. See every chosen piece drawn.
3. Choose the distribution and see a bar chart of the chances.
4. Set the board, speed, physics and theme. Problems are shown in plain English.
5. Run a balance check (computer player, histogram of game lengths).
6. Save `variants/<file_name>.toml`, ready for `play` and `package`.

---

## 10. Advanced appendix: extending ExTetris in Python

*For application programmers. Designers can stop reading here.*

The library lives in `v1_core_system/`, and the generated reference is `docs/api/index.html`. Add the folder to `sys.path` (or run from inside it).

### A10.1 Pieces and families
```python
from piece import Tetromino, ExTetromino3x3, ExTetromino, Handedness, Piece
t = Tetromino("T")
x = ExTetromino3x3((2, 2, 3, 3), Handedness.PLUS)       # built from geometry, no matrices
x2 = ExTetromino.create("3x3", (2, 2, 3, 3), "+")       # same piece
print(x.rotated_cw(), x.mirror_image().code, x.hole_signature)

from family import FULL, CLASSIC, PieceFamily
corners = FULL.filter(connectivity="corner", max_holes=2) | CLASSIC.exclude("S", "Z")
```

### A10.2 Your own distribution (functional-OO)
```python
from distribution import ByPropertyDistribution, Distribution, mix, BagDistribution
gentle = ByPropertyDistribution(FULL, rule=lambda p: 1 / (1 + p.min_landing_holes) ** 2)

class EveryFifthIsI(Distribution):          # any subclass with a pure weights() works
    def __init__(self, family): self.family = family
    def weights(self, history=(), count=0):
        return {c: (1.0 if (count % 5 == 4) == (c == "T1x4.H0000.0") else 0.0) for c in self.family.codes}
```

### A10.3 Driving the engine headless
```python
from engine import Engine
from state import Action
e = Engine({"pieces": {"preset": "Full"}, "rules": {"walls": "wrap"}}, seed=42)
e.apply_action(Action.ROTATE_CW); e.apply_action(Action.HARD_DROP)
events = e.tick(1000)                           # time is passed in explicitly
e.request_update("rules.gravity", "cascade")    # applied at the next tick
text = e.save(); e2 = Engine.resume(text, {"pieces": {"preset": "Full"}, "rules": {"walls": "wrap"}})
```

### A10.4 A different front end
Write any class with `draw(engine)` and a loop that calls `engine.tick(ms)` and `engine.apply_action(...)`. `tk_adapter.py` (about 230 lines) is the reference. The engine never imports a UI library, and `test_engine_has_zero_tkinter` keeps it that way.

### A10.5 Rules, scoring and levels
`state.Rules`, `state.Scoring` and `state.LevelPolicy` are frozen dataclasses. Subclass `Scoring` (override `for_clear`) or `LevelPolicy` (override `level_for` / `gravity_ms`) and assign the instance to `engine.scoring` / `engine.level_policy` after construction. Note that a later `request_update()` or trigger rebuilds these objects from the config, so re-assign yours after one fires.

**Verify your changes:** `python -m pytest v1_core_system v2_platform_release` (48 tests).
