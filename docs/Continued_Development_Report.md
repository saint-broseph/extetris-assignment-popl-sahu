# Continued Development Report — ExTetris

*From a quick-and-dirty starter (v0) through a failed design (v0.5) and a verified class library (v1) to a no-code platform (v2).*

| | |
|---|---|
| **Course** | CS F301 PoPL, Sem-I 2026-27 |
| **Repository** | `extetris-popl-sahu` |
| **AI assistant** | Claude (Anthropic), model Claude Opus 5.5, via claude.ai with a code-execution sandbox |
| **Session** | 2026-11-26, 16:28–18:03 IST (Prompts 1–21) |
| **Companion documents** | `AI_Interaction_Log.md` (Prompts 1–21), `Design_Document_UML.md`, `Game_Programmers_Manual.md`, `Design_Decisions_And_Quiz_Alignment.md` |

---

## 1. Summary

| Version | Folder | What it is | Evidence it works |
|---|---|---|---|
| **v0** | `v0_starter/` | The professor's starter code, extracted from the PDF and kept frozen | Runs on Windows/Python 3.12 (team); 23 bugs audited, most reproduced by script |
| **v0.5** | `v0.5_failed_attempt/` | First constructor design: pieces chosen by `(bounding box, diagonal connections)` | `verify_v05.py` proves it ambiguous: 27 pieces → 11 keys |
| **v1** | `v1_core_system/` | Programming System: 34-piece constructive hierarchy, functional-OO distributions, immutable headless engine, Tk adapter | `verify_piece.py` 9/9; `test_v1.py` **23/23** |
| **v2** | `v2_platform_release/`, `variants/`, build scripts | No-code platform: TOML specs, CLI, notebook, customizer, packager | `test_v2.py` 25/25 (48/48 total); 3 variants × 100 simulated games |

---

## 2. v0 — Starter audit

**Extraction.** The PDF's text layer was unusable for copy-paste: identifiers were letter-spaced, line numbers were interleaved, curly quotes replaced straight ones, and indentation was lost. Each line was rebuilt from glyph x-positions and checked against rendered page images. 30 wrapped lines were rejoined. One of them (`engine.py` L226) wrapped inside the string `"*.txt"`, where a naive join would have silently changed the file filter. All 73 shape matrices were validated (4 cells, king-connected, tight bounding box).

**Audit.** 23 runtime bugs, rated High (6), Medium (10) and Low (7), with line references (`docs/v0_bug_audit.md`). Most were reproduced by scripts (`tests/repro_v0_logic.py`, `tests/repro_v0_gui.py`). The most consequential:

| Bug | Effect | Found by |
|---|---|---|
| BUG-01 | Negative index wraps, so pieces pass through the left wall | script + **team on Windows** |
| BUG-02 | Rotation mutates the shared shape templates: rotate an S once and every later S is a Z | script |
| BUG-03 | Pressing Down while paused stacks gravity timers (6× fall speed after 5 presses) | script |
| BUG-04 | `pasueStatus` typo means About freezes the game | script + **team on Windows** (`docs/screenshots/v0_about_freeze.png`) |
| BUG-06 | `% 100` speed-up check is skipped by multi-line clears | script |
| BUG-11 | 73 matrices = 34 pieces listed 1–4×, a 4:1 probability bias | script |

**Lesson.** The starter's problems are mostly *shared mutable state* (BUG-02), *time handled in several places* (BUG-03/05) and *code in data* (`eval`, BUG-08/09). These became v1's principles: immutable values, one clock, no `eval`.

---

## 3. Interlude — combinatorics

`scripts/explore_polyominoes.py` enumerated all 4-cell shapes whose squares are joined by edges or corners, by two independent methods. The counts matched OEIS: **110 fixed, 34 one-sided (7 + 27), 22 free**, with 10 mirror-symmetric pieces and 12 mirror pairs. It also tested which invariants identify every piece. The minimal sufficient sets are `bbox + hole signature + handedness` and `edge/corner pairs + hole signature + handedness`.

The prompt claimed "`Extetromino1`, `8` and `9` are all the I-piece". The script showed the duplicates are actually **1, 10, 11**; 8 and 9 are two orientations of one extended piece.

---

## 4. v0.5 — The failed constructor (kept on purpose)

**Idea.** Extended-piece subclasses are chosen by bounding box. The constructor takes one parameter, the number of diagonal connections. It generates candidate shapes and silently takes the first.

**Why it failed** (`verify_v05.py`, exit code 0 = proof complete):
- Only **11 distinct constructor calls exist for 27 pieces**, so 16 pieces are unreachable.
- `ExTetromino3x3(diagonals=2)` matches **6 different pieces**.
- **All 10 extended mirror pairs collide.** Reflection preserves both the bounding box and the diagonal count, so *no key built only from mirror-invariant properties can ever separate twins*.
- Adding the hole signature alone separates 18/27. Adding handedness alone separates 20/27. **Both: 27/27.**

**What changed.** v1's constructor parameters became `(landing-hole signature, handedness)` within each bounding-box subclass. The failure was a design insight, not a bug fix: it showed handedness is *logically required*.

---

## 5. v1 — Programming System

| Module | Key decisions |
|---|---|
| `piece.py` (759 lines) | Abstract, immutable `Piece`; `Tetromino` (7) and `ExTetromino` with 5 bbox subclasses (2/9/9/6/1). No matrices: the 110 orientations are generated, and the catalogue self-checks uniqueness at build time. The spawn orientation (fewest holes, flattest) reproduces the Tetris Guideline spawn for all 7 classics. |
| `family.py` | Immutable `PieceFamily`: 6 filters, set algebra, presets Classic 7 / Extended-Easy 15 / Full 34 |
| `distribution.py` | 6 immutable distributions with pure `weights(history, count)`; bag state derived from history, so there is no hidden mutable state |
| `board.py`, `state.py` | Immutable `Board` and `GameState`; solid/wrap walls; naive/cascade gravity; `LevelPolicy` with threshold crossing and `1000·0.9^level`, clamped |
| `engine.py` | Headless, deterministic; layered config defaults→spec→player→runtime; tick-boundary updates; fire-once whitelisted triggers; JSON save/resume with variant hash and payload checksum |
| `tk_adapter.py` | The only tkinter module; Canvas renderer; a single `after()` loop; dialogs pause and then restore the previous mode |

**Verification.**
- `verify_piece.py` 9/9: AST scan finds 0 matrix literals and 0 `eval`; 73/73 starter matrices match, cross-checked with `numpy.rot90`.
- `test_v1.py` **23/23**, including 300 simulated games, zero tkinter in the engine (AST scan and a subprocess with tkinter blocked), and a save/resume equivalence test.
- Tested on Python 3.11 and 3.12.

---

## 6. v2 — No-code platform

| Component | Highlights |
|---|---|
| `spec.py` | TOML schema with 10 sections; `SpecValidator` reports every error in plain English with spelling suggestions; minimal TOML writer that round-trips |
| `cli.py` | `new / validate / play / simulate / package / pieces` |
| `customizer.py` | In-game Variant Customizer: live changes at the next tick, "Save as variant…" |
| `simulator.py` | Greedy bot that plays only through `apply_action`; verdicts and frequency check |
| `packager.py` | Zip with engine, variant, generated guide, run scripts and a PyInstaller spec; `run.py --check` |
| Notebook | 14 cells with Colab `@param` forms; executed end-to-end in the sandbox |
| Variants | Classic 1984; Corner Chaos (34 pieces, wrap, adaptive); Zen Sandbox (14×24, Extended-Easy, 3 bonus triggers) |

**Results of 100 simulated games per variant** (`docs/phase4_cli_output.txt`). All three are BALANCED, with piece frequencies within 0.6 percentage points of design. Zen Sandbox's bonus triggers fired 88 / 75 / 54 times.

---

## 7. AI-assisted effort vs. effort without AI

### 7.1 Quantitative

| Measure | Value | Source |
|---|---|---|
| Chat wall-clock, Prompt 1 to Prompt 21 | **≈ 95 min** (16:28–18:03 IST) | message timestamps |
| Production code written (v1 + v2) | ≈ 3,365 lines (v1 2,256 + v2 1,109) | `wc -l` |
| Verification and test code | ≈ 1,049 lines (+ 349 lines in v0.5) | `wc -l` |
| Automated checks | 48 pytest + 9 `verify_piece` + `verify_v05` proof + 3 × 100-game simulations | test output files |
| Documentation | 6 Markdown documents + generated API docs | `docs/` |
| Team time reviewing, running on Windows, Git | **≈ 2.5 hours** (setup, Windows verification, reviews, Git checkpoints) | local Git log & session |

**Estimate without AI.** These figures are assumptions for comparison, not measurements.
- **Assumed rate:** 15–30 tested lines/hour for a student pair, including design time. At that rate, 3,365 production + 1,049 test lines would take ≈ **150–290 person-hours**.
- **Extra work outside that rate:** the combinatorics study, the PDF extraction tooling and the documentation, plausibly another 30–60 hours.
- **Total:** roughly **180–350 person-hours**, compared with ≈ 1.5 hours of chat plus ≈ 2.5 hours of hands-on review, Windows testing, and Git management.
- **Caveat:** without AI the team would almost certainly have built a smaller system, so the honest comparison is *scope*, not just hours.
- **Team review of estimate:** We endorse the 180–350 person-hour baseline as a realistic estimate for designing, implementing, testing, and documenting a ~4,400-line modular system and platform from scratch without AI assistance.

### 7.2 Qualitative

**Where AI helped most:**
- Exhaustive, mechanical verification that people often skip: AST scans, two-method enumeration, Mermaid parsing, executing the notebook, re-running everything on two Python versions.
- Breadth: one session covered the extraction tooling, a combinatorial proof, an engine, a platform and the documentation.
- Turning vague requirements ("functional-OO distribution") into concrete, testable designs.

**Where AI was wrong or limited (all recorded in the logs):**
- **Wrong expected values in its own tests, three times:**
  - the v0.5 collision count (6 instead of 7);
  - the cascade test outcome;
  - the number of wrap-test moves.

  In each case the code was right and the test was wrong; they were caught only because the tests were run.
- **Mermaid syntax errors twice** (the reserved word `loop`, and `;` inside a message). Caught by a parser, not by reading.
- **A test-harness hang** (several Tk roots in one process) while reproducing v0 bugs.
- **An analysis bug:** the free-level check initially left out chirality and printed "NOT unique". Fixed before delivery.
- **A wrong assumption about the linked computer.** It offered to write into a project folder that turned out to be on a different machine, so it could never write to the repo directly.
- **Unchecked assumptions:**
  - the landing-hole definition was never checked against the 6 Nov tutorial;
  - Windows-only paths (`build.bat`, the PyInstaller build) were not executed by the AI;
  - the Moodle quiz questions were supplied during the final documentation pass (`X6`) to complete Part D of `Design_Decisions_And_Quiz_Alignment.md`.

**Trade-offs:**
- **Review burden.** About 4,400 lines of generated code is more than a team can read line by line. The team relied on tests the AI also wrote, which is a risk of correlated errors. Mitigations: independent checks (OEIS counts, `numpy.rot90` cross-check), and the team's own Windows reproductions.
- **Understanding.** Fast generation risks shallow understanding. The v0.5 failure and the quiz alignment are where the team's own reasoning shows.
- **Team verification & reflection:** We personally extracted and ran `v0_starter/` on Windows (Python 3.12) to verify the `About` freeze (`docs/screenshots/v0_about_freeze.png`) and left-wall wrap-around bugs, ran `scripts/explore_polyominoes.py` locally to verify the `110 / 34 / 22` counts, enforced clean phase-by-phase Git commits (`v0` → `v0.5` → `v1` → `v2` → `docs`), and audited all 4 starter quiz answers against the final `v2` codebase. With more time, we would package the CLI via `pyproject.toml` so `extetris` runs without a shell alias and add SRS-style wall kicks as an optional rule toggle.

---

## 8. Git checkpoints

| Checkpoint | Commit message | Status |
|---|---|---|
| v0 baseline & combinatorics | `Phase 1 complete: v0 audit, polyomino combinatorics, and Log Update 1` | Committed (`v0_starter/` frozen) |
| v0.5 & v1 pieces | `Phase 2: architecture blueprint, v0.5 collision proof, and v1 pieces` | Committed (`v0.5_failed_attempt/` + `piece.py`) |
| v1 core system | `Phase 3: complete v1 core programming system (23/23 pytest passing)` | Committed (`v1_core_system/`, commit `883af89`) |
| v2 platform & variants | `Phase 4: v2 no-code platform, CLI, Jupyter studio, packager, and 48/48 passing tests` | Committed (`v2_platform_release/` + `variants/`) |
| Final docs & AI logs | `Final submission: complete ExTetris system, platform, docs, quiz alignment, and AI logs` | Final submission commit |

---

## 9. Future Extensions (Beyond Assignment Scope)

All core Programming System (`v1`) and No-Code Platform (`v2`) deliverables are complete and verified (`48/48` automated tests passing). Potential post-submission enhancements include:

1. **Packaging & CLI Entry Point:** Adding a `pyproject.toml` console-script entry point so `extetris` runs globally without a shell alias, alongside building standalone Windows/Linux executables via the generated PyInstaller spec.
2. **Advanced Rotation & Hold Mechanics:** Adding optional Super Rotation System (SRS) wall kicks and a piece-hold slot as configurable flags in `Rules` and `variant.toml`.