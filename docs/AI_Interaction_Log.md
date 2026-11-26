# AI Interaction & Development Log (CS F301 PoPL — ExTetris)

## Log Update 1 — 2026-11-26 (covers Prompts 1–3)
- **AI assistant:** Claude (Anthropic), model Claude Opus 5.5, used through claude.ai with tool use (code-execution sandbox, web search, file delivery, link to a desktop computer).
- **Session timeline (IST):** Prompt 1 sent 16:28. Message A, containing Prompts 2 and 3, sent 16:56. Message B, re-sending Prompts 2 and 3 with edits plus the "Workspace & File Guardrails", sent 16:59 while the AI was still working on Message A. The AI sent one reply covering Messages A and B. LOG UPDATE requested 17:04.
- **Notation:** Prompts are reproduced verbatim as typed. AI replies are reproduced verbatim as the final chat message, rendered as Markdown. The AI's intermediate tool activity was not shown verbatim in chat, so it is summarised separately under each reply.
- **Folder naming:** The AI's outputs refer to `v0/`. In this repository that folder is `v0_starter/` (see Entry 2).

---

### Entry 1 — Prompt 1: Starter Code Extraction & Bug Audit

#### (1) Prompt (verbatim)
Attachment: `PoPL2026AssignmentExTetris_2.pdf` (assignment specification, 16 pages).

`@"/mnt/user-data/uploads/3e3dbd85-PoPL2026AssignmentExTetris_2.pdf"` This applies to the entire chat: My CS F301 PoPL submission requires a complete, candid AI usage log covering 8 specific points for every prompt: (1) Verbatim prompt, (2) Verbatim AI response, (3) My interpretation, (4) My plan based on it, (5) What I implemented, (6) Outcome / did it work, (7) Manual modifications / debugging / independent research I did, and (8) Strengths, weaknesses, and trade-offs. 

Whenever I type `LOG UPDATE`, generate a clean Markdown block for `docs/AI_Interaction_Log.md` covering all prompts since the last log update. Fill in (1) and (2) verbatim from our actual chat history, draft (4), (5), and (8) from the code produced, and leave `[USER TO FILL/VERIFY]` placeholders for (3), (6), and (7).

Prompt 1 (Starter Code Extraction & Bug Audit): I am working on my CS F301 (Principles of Programming Languages) assignment on designing and developing an Extended Tetris (ExTetris) engine and platform. I have attached the assignment specification PDF, which includes the starter code in the Appendices (`engine.py`, `board.py`, `shape.py`, `allextetrominoes.py`). First, do not write the final solution yet. Extract the exact starter code from the PDF appendices cleanly into four separate files so I can run it as my baseline `v0`. While extracting, audit the code for syntax/OCR errors from the PDF as well as actual runtime bugs in Prof. Joshi's starter implementation (such as pause bugs, speed-up skipping bugs, `eval()` usage, and distribution bias). List every bug you find with line references.

#### (2) AI response (verbatim)

<details>
<summary>Final chat reply (click to expand)</summary>

I've extracted the four starter files into a runnable v0/ baseline with the professor's code unchanged and every bug left in. They compile and run on Python 3.12, Tk 8.6 and numpy 2.5.5. Line numbers in the files match the PDF's line numbers exactly, so every reference below works against both. I confirmed each runtime bug below with a test script, except the wide-glyph display issue (#22) and those found by reading the code alone (the .strip() misalignment in #5 and #14, #17, #19, #21).
To play it, run python3 v0/engine.py and answer 0 at the prompt to get the classic 7 pieces.
Problems with the PDF itself (fixed during extraction)
- Copy-paste from the PDF won't run. Its hidden text layer puts spaces inside names (e x t e t r o m i n o _ d i s t r i b u t i o n) and mixes in the line numbers. I rebuilt each line from the character positions and checked it against the printed pages.
  - Smaller fixes:72 curly ’ quotes changed to '.
  - The 2-space indentation restored.
  - 30 lines that the PDF wrapped were joined back up. Careful with engine.py line 226: it wraps inside "*.txt", and joining it with a space would quietly change the file filter to " *.txt".
- No corrupted shape data. All 73 shapes have 4 cells, connected edge-to-edge or corner-to-corner. pasueStatus (line 184) is really in the printed code, so it's a genuine bug, not a PDF error.
Runtime bugs (E = engine.py, B = board.py, S = shape.py, A = allextetrominoes.py; H = high, M = medium, L = low)
#SevWhereBug1HB 45–53 (→E 80, B 38)A negative column index wraps around instead of raising an error. Pieces walk through the left wall and are drawn and locked on the right edge.2HS 29–40; E 88–89, 98–99, 208; A 104, 116Shapes are never copied, and rotation changes the shared original. One rotation of an S turns every later S into a Z, and a blocked rotation still mirrors the falling piece.3HE 53, 119–125Pause bug: Down isn't blocked while paused, and each press starts an extra gravity timer. 5 presses made pieces fall 6× faster (18 steps in 3 s instead of 3). New Game doesn't clear them.4HE 184The pasueStatus typo means the game stays paused after About, with the help text stuck on the board.5HE 141–150Game Over is broken: <ul><li>The screen refresh wipes the "Game Over" message within 100 ms.</li><li>Topping out with Down opens a second, nested Game Over dialog.</li><li>quit() closes the program, so New Game is impossible.</li><li>game_over_status is never set, so the check at line 213 never runs.</li><li>.strip() at line 146 shifts some rows of the final board.</li></ul>6HE 138Speed-up skipping: % 100 only fires when the line count lands exactly on 100. Going from 98 to 102 skips it, and a player who always clears 3 rows never speeds up.7ME 162–16650 clicks of Speed-Up reach 0 ms, a busy loop that freezes the window. Slow-down can't get back from 0, since 0 × 1.1 = 0.8ME 253eval() runs a fixed string, so it does nothing useful. Input isn't checked: <ul><li>a non-number crashes;</li><li>N ≤ −7 crashes at the first piece;</li><li>N ≥ 67 crashes at some random later piece.</li></ul>9MA 104, 116 (B 83, S 63)eval() is used to look up shapes by name. Index 0 or ≥ 74 raises NameError. If the index is ever a string, it runs arbitrary code (my test shows this).10MA 113 (27)The docstring says range(count) gives a uniform choice, but that includes 0, which crashes at random. It also leaves out the last piece.11MA 30–102, A 116Distribution bias: <ul><li>Shapes 1, 10 and 11 are all the same I piece, so I is 3× as likely.</li><li>The 73 entries are only 34 distinct pieces under rotation, listed 1 to 4 times each, a 4:1 skew. For example, #23 is just a vertical S, so S is 2× as likely.</li><li>The random generator is global and never seeded, so games can't be reproduced.</li></ul>12ME 36–44You can click into the board and type. While paused the text stays, and Save writes it out.13ME 149, 183tk.simpledialog is never imported. It only works because filedialog happens to load it. On Python 3.7 and earlier, Game Over and About crash.14ME 137, 163, 166, 215numpy is never imported in engine.py. It only exists because of from allextetrominoes import *.15ME 71mainloop() runs inside __init__, so creating a TetrisEngine never returns. That blocks the API you're meant to build.16ME 199, 225–230"Save state" only saves the screen text and there's no load. The game keeps running behind the Save dialog.17LE 96–104, 232–240Anticlockwise rotation has no key. The 'UP' direction is never used, and an unknown direction crashes with UnboundLocalError.18LE 212–223New Game always unpauses, line 213 never runs, and the extra timers from #3 survive.19LE 190–205Exit and Quit do the same thing, the menu has a tear-off line, the Pause label never changes, and there's no pause key.20LS 19–23The default shape array is shared by every Shape. The type check compares strings, so it rejects lists. It raises a bare Exception.21LE 22–23, 77, 139, 219Unused imports and a variable, plus extra cursor resets.22LB 29, S 54, E 38The board uses ⬛ but Shape uses □. A wide ⬛ glyph could wrap rows, depending on the font; it didn't happen here.23LB 56–79, S 59–69The self-tests have bugs: while(i+j) stops on (3, −3), and the tests change the shared shapes.Checked and correct, so don't "fix" these:
- clearing several rows at once, even non-adjacent ones;
- the rotation maths itself;
- collisions with the right wall and the floor.
docs/v0_bug_audit.md has the full explanation for each bug, plus a few design choices to decide on (hard drop doesn't lock, no wall kicks). The test scripts are in tests/, with their saved output in docs/v0_repro_output.txt.
Your computer is connected now, so I can put the extetris/ folder straight into your project directory if you tell me which one.
Sources: CPython 3.7 tkinter/filedialog.py, CPython 3.8 tkinter/filedialog.py
Files are in:
- engine.py
- board.py
- shape.py
- allextetrominoes.py
- v0_bug_audit.md
- extetris_v0.zip

</details>

Files delivered with this reply: `v0/engine.py`, `v0/board.py`, `v0/shape.py`, `v0/allextetrominoes.py`, `docs/v0_bug_audit.md`, and `extetris_v0.zip`.

AI tool activity behind this reply (summary; not shown verbatim in chat):
- Extracted the PDF text with `pdftotext` and rebuilt every code line from glyph x-positions using `pdfplumber`.
- Rendered PDF pages 6–12 as images to verify the rebuilt code visually and confirmed exact line counts (253 / 97 / 69 / 116).
- Ran GUI tests under `Xvfb` on Linux (Python 3.12, Tk 8.6, numpy 2.5.5) and verified CPython `tkinter/filedialog.py` import behavior.

#### (3) My interpretation
- Direct copy-paste from the PDF fails due to character-level text spacing and line wrapping, so reconstructing the files while preserving exact line numbers was necessary to create a valid baseline.
- Beyond simple typos (`pasueStatus` at `engine.py` line 184), the starter architecture suffers from deep structural defects: shared mutable `numpy` arrays across `Shape` instances, `mainloop()` blocking inside `TetrisEngine.__init__()`, negative-index wrap-around instead of left-wall collision checks, `eval()`-based shape lookup, and up to a 4:1 probability bias because duplicate/rotated shapes are listed multiple times in `allextetrominoes.py`.
- Preserving `v0` untouched while using these 23 audited bugs as our `v1` requirements backlog gives us a clear, verifiable engineering baseline.

#### (4) My plan based on it
- Freeze the AI-extracted code, bug-for-bug, as the `v0` baseline (`v0_starter/`). Fix nothing in it.
- Treat the 23 audited bugs as the requirements backlog for `v1` (explicit bounds checking, immutable pieces, single timer ownership, proper game-over state, threshold-crossing speed-ups `old // 100 != new // 100`, registry-based shape lookup without `eval()`, functional-OO probability distributions, and headless `Engine` decoupling from `tkinter`).
- Reproduce key bugs manually on Windows before building `v1`.
- Preserve working behaviors identified in the audit (multi-row clearing and core rotation math).

#### (5) What I implemented
- Saved the four AI-extracted files unmodified into `v0_starter/` (`engine.py`, `board.py`, `shape.py`, `allextetrominoes.py`).
- Saved the full audit document as `docs/v0_bug_audit.md` and initialized the local Git repository on Windows (`C:\Users\HP\Desktop\extetris-popl-sahu`) to snapshot `v0_starter/` permanently.

#### (6) Outcome / did it work?
- **Yes.** All four extracted files compiled and ran cleanly on Windows (Python 3.12) without requiring any syntax patches, matching the PDF's exact line numbering.

#### (7) Manual modifications / debugging / independent research
- Replaced Unix-style directory setup commands (`mkdir -p`, `touch`) with Windows `cmd.exe` equivalents (`mkdir`, `type nul >`) when initializing the workspace and log files.
- Manually inspected the extracted files against Appendices A–D of `PoPL2026AssignmentExTetris (2).pdf` to confirm that `pasueStatus` (line 184) and the negative-index collision logic (`board.py` lines 45–53) matched the printed specification verbatim.

#### (8) Strengths, weaknesses, trade-offs
- **Strengths:** Rebuilding from PDF glyph positions avoided silent errors (such as breaking `"*.txt"` at `engine.py` line 226); line numbers match the PDF 1:1; and the audit uncovered subtle architectural flaws (shape aliasing, 4:1 distribution bias, nested Game Over dialogs) beyond surface typos.
- **Weaknesses:** Initial reproduction tests were run by the AI on Linux/Xvfb rather than Windows, and a few low-severity items (#14, #17, #19, #21, #22) were identified via static code inspection rather than live execution.
- **Trade-offs:** Keeping `v0` bug-for-bug faithful prevents playing a smooth game in `v0`, but provides an undeniable before/after baseline for the Continued Development Report.

---

### Entry 2 — Prompt 2: Recording v0 Run Results

#### (1) Prompt (verbatim)
Prompt 2 was sent twice: in Message A (16:56) and again, edited, in Message B (16:59).

Message A (16:56), Prompt 2 portion:
Prompt 2 (Recording `v0` Run Results): I saved the extracted files into `v0_starter/` and ran `python v0_starter/engine.py` on Windows (Python 3.12). It launched cleanly, and I personally reproduced and captured a screenshot of the `About` menu freeze (`pasueStatus` typo at line 184 leaving the help text stuck on the board) as well as the left-wall negative-index wrap-around bug. Since `v0_starter/` runs as a faithful unedited baseline, we will keep `v0_starter/` completely untouched as our `v0` artifact and move straight to mathematical exploration before designing `v1`.

Message B (16:59), Prompt 2 portion:
Prompt 2 (Recording `v0` Run Results): I ran `python v0_starter/engine.py` on Windows (Python 3.12). It launched cleanly, and I personally reproduced and saved a screenshot (`docs/screenshots/v0_about_freeze.png`) of the `About` menu freeze (`pasueStatus` typo at line 184 leaving the help text stuck on the board) as well as the left-wall negative-index wrap-around bug. We will keep `v0_starter/` completely untouched as our `v0` artifact and move to mathematical exploration before designing `v1`.

#### (2) AI response (verbatim)
No separate AI response. Prompt 2 was a status record sent in the same messages as Prompt 3. The AI's single reply (Entry 3, point 2) confirmed that `v0_starter/` remained completely unmodified.

#### (3) My interpretation
- Live execution on Windows confirmed that the AI's Linux audit accurately predicted real user-facing failures: clicking `About` permanently locks the board on the help text screen due to the `pasueStatus` typo, and moving past column `0` wraps pieces onto the right side of the board via negative array indexing in Python/NumPy.
- Having visual screenshot evidence of `v0` running and failing on the target OS strengthens the empirical record for our report.

#### (4) My plan based on it
- Freeze `v0_starter/` as a committed, untouched Git artifact.
- Store visual screenshot evidence (`docs/screenshots/v0_about_freeze.png`) alongside the bug audit.
- Proceed directly to combinatorial verification of all 4-cell king-connected polyominoes before designing the `v1` class hierarchy.

#### (5) What I implemented
- Executed `python v0_starter\engine.py` on Windows (Python 3.12), entering `0` at the `How many EXtetrominoes?` prompt.
- Manually triggered and verified `BUG-04` (`About` menu freeze via `pasueStatus` at line 184) and `BUG-01` (left-wall negative-index wrap-around).
- Captured and saved `docs/screenshots/v0_about_freeze.png` and committed the baseline to Git.

#### (6) Outcome / did it work?
- **Yes.** The game launched properly, both target bugs were reproduced firsthand on Windows, and the screenshot clearly captures the frozen help screen state.

#### (7) Manual modifications / debugging / independent research
- Manually tested keyboard controls and menu actions on Windows `Tkinter` to verify window responsiveness and confirm how `tk.Text` allows cursor clicks inside the live board (`BUG-12`).

#### (8) Strengths, weaknesses, trade-offs
- **Strengths:** Provides independent, platform-native (Windows Python 3.12) confirmation and visual screenshot proof of the starter code's behavior without relying solely on AI sandbox tests.
- **Weaknesses:** Manually tested a targeted subset of the 23 bugs rather than writing a full Windows GUI automation harness for `v0`, as effort is better invested in building `v1`.
- **Trade-offs:** Moving directly to polyomino combinatorics maintains project momentum while keeping `v0_starter/` preserved for evaluators.

---

### Entry 3 — Prompt 3: Mathematical Verification of ExTetrominoes (with Workspace & File Guardrails)

#### (1) Prompt (verbatim)
Message A (16:56), Prompt 3 portion:
Prompt 3 (Mathematical Verification of ExTetrominoes): Before we design the class hierarchy, let's analyze the combinatorics of ExTetrominoes. In `allextetrominoes.py`, the starter code hard-codes 73 matrices generated by an Octave script, with duplicates (like `Extetromino1`, `8`, and `9` all being the I-piece). Write a standalone exploratory Python script (`explore_polyominoes.py`, not part of the game yet) that enumerates all 4-cell polyominoes connected by edges OR corners (king's-graph connectivity on a 2D grid). Count:

1. Total fixed orientations (verify if it is 110)
2. Unique shapes up to 90° rotations (one-sided / chiral — verify if it is 34: 7 classic + 27 extended)
3. Unique shapes up to rotations AND reflections (free — verify if it is 22) Also check what geometric invariants (bounding box, edge-vs-corner connectivity, landing-hole signature across rotations, and chirality/handedness) uniquely identify every single one of those 34 shapes without hard-coding boolean matrices.

Message B (16:59, sent while the AI was working on Message A), guardrails and Prompt 3 portion:
Workspace & File Guardrails: My project root is `C:\Users\HP\Desktop\extetris-popl-sahu`. You have permission to read and write files directly inside this directory, subject to three strict rules:

1. Never modify `v0_starter/`—it is already committed as our untouched starter baseline.
2. Never delete `v0.5_failed_attempt/` once we create it—we must preserve earlier failed/flawed attempts for our Continued Development Report.
3. Maintain `docs/AI_Interaction_Log.md` directly: Whenever I say `LOG UPDATE`, append the formatted log blocks directly to `docs/AI_Interaction_Log.md` (keeping all previous entries intact) with `[USER TO FILL/VERIFY]` placeholders for my personal interpretations and manual verification notes so I can review and edit them before committing.

Prompt 3 (Mathematical Verification of ExTetrominoes): Before designing the class hierarchy, let's analyze the combinatorics of ExTetrominoes. In `v0_starter/allextetrominoes.py`, the starter code hard-codes 73 matrices generated by an Octave script, with duplicates (like `Extetromino1`, `8`, and `9` all being the I-piece). Create a standalone exploratory script `scripts/explore_polyominoes.py` (not part of the game yet) and run it to enumerate all 4-cell polyominoes connected by edges OR corners (king's-graph connectivity on a 2D grid). Count and verify:

1. Total fixed orientations (verify if 110)
2. Unique shapes up to 90° rotations (one-sided / chiral — verify if 34: 7 classic + 27 extended)
3. Unique shapes up to rotations AND reflections (free — verify if 22) Also verify which geometric invariants (bounding box, edge-vs-corner connectivity, landing-hole signature across rotations, and chirality/handedness) uniquely identify every single one of those 34 shapes without hard-coding boolean matrices.

#### (2) AI response (verbatim)

<details>
<summary>Final chat reply (click to expand)</summary>

I wrote and ran scripts/explore_polyominoes.py, and all three of your target counts are correct. But I couldn't put it in your project folder: the computer linked to this chat doesn't have C:\Users\HP\Desktop\extetris-popl-sahu.
Your folder. The linked computer is desktop-f5ptnnm. It only has the user folders Admin, Default and Public, and the repo isn't in its Desktop, Documents or Downloads. It's probably not the laptop your project is on. To fix it, open this chat in the Claude desktop app on the computer that has the repo and choose "Add folder" from the + menu for extetris-popl-sahu. Or, if the project is on this computer, tell me the real path. Until then I can't run the script on your machine or write LOG UPDATE entries to docs/AI_Interaction_Log.md. For now, the files to drop in are listed at the end. The script only reads v0_starter/ and never changes it (the file was identical before and after the run).
A correction to Prompt 3. The duplicate I-pieces are Extetromino1, 10 and 11, not 1, 8 and 9. Shapes 8 and 9 are the same extended piece (##. / #.#) stored in two different orientations.
Counts. I enumerated the shapes two independent ways (every 4-cell subset of a 4×4 box, and growing shapes one cell at a time), and both give the same 110. All five numbers below also match the published sequences: fixed n-polyplets are 1, 4, 20, 110, …; one-sided are 1, 2, 6, 34, …; free are 1, 2, 5, 22, … [in-chat source citation: Wolfram MathWorld, "Polyplet", https://mathworld.wolfram.com/Polyplet.html]
CountResultFixed orientations110 ✓One-sided (rotations count as the same)34 ✓ = 7 classic + 27 extendedFree (rotations and mirror images count as the same)22 ✓ = 5 classic + 17 extendedFree shapes that are their own mirror image10Free shapes that come as mirror pairs12What each invariant means in the script. None of these depends on how the piece is rotated:
- Bounding box: the size of the smallest rectangle around the piece, ignoring which way round it is (e.g. 2x4). There are 7 possible sizes, and they split the 34 shapes as 1 / 1 / 7 / 9 / 9 / 6 / 1. The 9 "4x2" pieces the spec mentions are one of those groups.
- Edge-vs-corner connectivity: how many pairs of cells share an edge, and how many touch only at a corner. A shape whose cells are all joined by edges is a classic tetromino.
- Landing-hole signature: drop the piece on a flat floor and count empty cells left underneath it. Do this for each of the 4 rotations, in clockwise order, to get 4 numbers. This is my own definition, so please check it against the 6 Nov tutorial video. It's one small function (landing_holes()) if it needs changing.
- Handedness: a number calculated from the cell positions. It stays the same when you rotate the piece and changes sign when you mirror it. The script checks that it is 0 for exactly the 10 symmetric shapes and has opposite signs for every mirror pair: L and S come out +, J and Z come out −.
Which invariants identify all 34 shapes.
- Your four together give 34 different values, so every shape is identified without storing any matrices.
- Three are enough: bounding box (or edge/corner pairs) + landing-hole signature + handedness. No two of them are enough. The closest pair, hole signature + handedness, only fails to tell I from O, because neither ever leaves a hole.
- The hole signature does most of the work. On its own it gives 21 different values. Bounding box gives only 7, and edge/corner pairs 9.
- Handedness can't be dropped. Without it, 10 of the 12 mirror pairs (L/J, S/Z, …) look identical. The order of the hole counts only separates 2 of them.
- The simple yes/no "is it symmetric" check is redundant once you have handedness. It's still needed if you want to ignore mirror images: bounding box + edge/corner pairs + edge components + symmetric-or-not + the four hole counts in any order identify all 22 free shapes.
The starter file's 73 matrices. They contain all 34 shapes, with none missing. But each shape is listed between 1 and 4 times, so picking a random index gives some shapes 4/73 odds and others 1/73.
Files are in:
- explore_polyominoes.py
- explore_polyominoes_output.txt

</details>

Files delivered with this reply: `scripts/explore_polyominoes.py` and `docs/explore_polyominoes_output.txt`.

AI tool activity behind this reply (summary; not shown verbatim in chat):
- Verified polyplet sequences (`110`, `34`, `22`) against OEIS / Wolfram MathWorld.
- Implemented dual independent enumerations (subset filtering over a 4×4 grid and constructive cell-by-cell growth) and verified invariant uniqueness in Python.
- Caught and fixed an omission in its initial free-level uniqueness check before delivering the final script.

#### (3) My interpretation
- The combinatorics are mathematically airtight: the 73 matrices in `allextetrominoes.py` collapse into exactly **34 unique one-sided (chiral) pieces** (7 classic tetrominoes + 27 corner-connected extended tetrominoes), which correspond to **110 fixed orientations** and **22 free shapes**.
- Crucially, the invariant analysis proves why **bounding box alone (7 buckets) or connectivity alone (9 buckets) is insufficient** to uniquely construct all 34 pieces—whereas the triple **(bounding box, landing-hole signature, handedness)** yields **34/34 distinct keys** with zero collisions and zero hard-coded boolean matrices.
- Using the 34 canonical pieces as the base unit of our `Distribution` classes will also eliminate the starter code's 4:1 sampling bias.

#### (4) My plan based on it
- Correct my earlier note: the duplicate I-pieces in `allextetrominoes.py` are `Extetromino1`, `10`, and `11` (whereas `8` and `9` are rotated orientations of the same extended piece).
- Design the `v1` `Piece` hierarchy around constructive geometric generation rather than hard-coded arrays:
  - split subclasses by connectivity (`Tetromino` vs. `ExTetromino`) and bounding box (`2x3`, `2x4`, `3x3`, `3x4`, `4x4`);
  - identify and instantiate individual pieces uniquely via `(landing_hole_signature, handedness)`.
- First build a `v0.5` prototype using only `(bounding_box, diagonal_count)` to empirically demonstrate the exact chiral collisions before finalizing `v1`.

#### (5) What I implemented
- Created `scripts/` and saved `scripts/explore_polyominoes.py` and `docs/explore_polyominoes_output.txt` into the local repository.
- Executed `python scripts\explore_polyominoes.py --starter v0_starter\allextetrominoes.py` locally on Windows (Python 3.12).

#### (6) Outcome / did it work?
- **Yes.** Running `scripts\explore_polyominoes.py` locally on Windows Python 3.12 confirmed all assertions: `110` fixed orientations, `34` one-sided pieces (`7` classic + `27` extended), `22` free pieces (`10` achiral + `12` chiral mirror pairs), and `34/34` unique identification using `(bounding_box, landing_hole_signature, handedness)`.

#### (7) Manual modifications / debugging / independent research
- Decided to keep workflow browser-based (downloading artifacts directly into local folders rather than linking Claude Desktop), maintaining strict manual control over Git commits and directory boundaries.
- Verified the starter-file mapping output (`--starter v0_starter\allextetrominoes.py`) and confirmed Claude's correction regarding `Extetromino1, 10, 11` vs. `8, 9` by inspecting lines 30–40 of `v0_starter/allextetrominoes.py`.

#### (8) Strengths, weaknesses, trade-offs
- **Strengths:** Dual independent enumeration methods plus OEIS cross-verification guarantee correctness; exact integer arithmetic avoids floating-point issues in handedness (`spin-4` moment); and the exhaustive invariant search gives an objective mathematical justification for our `v1` class constructors.
- **Weaknesses:** The spin-4 moment sign convention (`+` for L/S, `-` for J/Z) is mathematically clean for internal constructors but needs human-readable labels (`left-handed` / `right-handed` / `symmetric`) in the Game Programmer's Manual.
- **Trade-offs:** Classifying pieces via geometric invariants requires slightly more constructor validation logic than storing raw matrices, but directly fulfills Section 3.2 of the assignment specification and enables property-based filtering (`max_holes`, `handedness`, `bbox`) for game designers.