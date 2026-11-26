# ExTetris — Design Document (UML)

| | |
|---|---|
| **Course** | CS F301 Principles of Programming Languages, Sem-I 2026-27 |
| **Repository** | `extetris-popl-sahu` |
| **Covers** | `v1_core_system/` (ExTetris Programming System) and `v2_platform_release/` (ExTetris Game Variant Development Platform) |
| **Supersedes** | `docs/architecture_v1_blueprint.md` (rev 1.1), which was the plan. This document describes what was built. |
| **API reference** | `docs/api/index.html`, generated from the source docstrings with `pdoc` |
| **Verification** | `pytest v1_core_system v2_platform_release` → 48 passed (23 core + 25 platform). `verify_piece.py` → 9/9. `verify_v05.py` → proof complete. |

---

## 1. System vs Platform

The deliverable is a **platform** for non-programmers that contains a **programming system** (a Python library) as a strict subset. The library was built and verified first, so the API existed before any user interface.

```mermaid
flowchart TB
    subgraph PLATFORM["ExTetris Game Variant Development Platform  (v2_platform_release/)"]
        direction TB
        DESIGNER(["Game designer - no Python"])
        TOML["variants/*.toml"]
        NB["Variant_Designer_Studio.ipynb"]
        CLI["cli.py: new / validate / play / simulate / package / pieces"]
        SPEC["spec.py: VariantSpec + SpecValidator"]
        SIM["simulator.py: headless bot balance check"]
        CUST["customizer.py: in-game Variant Customizer"]
        PACK["packager.py: zip + run.bat/run.sh + VARIANT_GUIDE.md + PyInstaller spec"]
        DESIGNER --> TOML
        DESIGNER --> NB
        NB --> SPEC
        TOML --> CLI
        CLI --> SPEC
        CLI --> SIM
        CLI --> CUST
        CLI --> PACK
    end
    subgraph SYSTEM["ExTetris Programming System  (v1_core_system/)"]
        direction TB
        L5["L5 adapter: tk_adapter.py - TkinterRenderer, TkinterController (the only tkinter import)"]
        L3["L3 engine.py - Engine: layered config, triggers, save/resume"]
        L2["L2 state.py - Rules, Scoring, LevelPolicy, GameState, Mode, Action, Event"]
        L1["L1 family.py - PieceFamily | distribution.py - Distributions | board.py - Board"]
        L0["L0 piece.py - Piece, Tetromino, ExTetromino x5, Handedness"]
        L5 --> L3 --> L2 --> L1 --> L0
    end
    SPEC -->|"engine_spec()"| L3
    SIM --> L3
    CUST --> L5
    PACK -->|"copies modules"| SYSTEM
```

**Dependency rule.** Arrows point only downwards. Two things enforce it:
- `test_engine_has_zero_tkinter` scans every core module's imports and imports `engine` with `tkinter` blocked.
- `test_package_is_self_contained` runs a shipped package with nothing but its own copy of the modules.

| Layer | Module | Responsibility | Lines |
|---|---|---|---|
| L0 | `piece.py` | 34 immutable pieces generated from geometry, with invariants | 759 |
| L1 | `family.py` | Immutable named piece sets, filters, set algebra, presets | 225 |
| L1 | `distribution.py` | Seeded functional-OO probability models | 246 |
| L1 | `board.py` | Immutable board, solid/wrap walls, naive/cascade clearing | 133 |
| L2 | `state.py` | Rules, Scoring, LevelPolicy, immutable GameState, events | 222 |
| L3 | `engine.py` | Headless state machine, layered config, triggers, save/resume | 442 |
| L5 | `tk_adapter.py` | Canvas renderer and single-clock controller | 229 |
| P | `spec.py` | TOML variant schema and plain-English validator | 488 |
| P | `cli.py`, `simulator.py`, `customizer.py`, `packager.py` | Platform commands | 621 |

---

## 2. Class hierarchy and composition (UML)

```mermaid
classDiagram
    class Piece {
        <<abstract, immutable>>
        +cells Cells
        +bbox BBox
        +hole_signature HoleSig
        +handedness Handedness
        +code str
        +turned(k) Piece
        +rotated_cw() Piece
        +mirror_image() Piece
        +to_matrix() ndarray
        +all_pieces() tuple$
        +identify_matrix(m) Piece$
        +from_code(code) Piece$
    }
    class Tetromino {
        +letter str
        +from_invariants(bbox, holes, hand) Tetromino$
    }
    class ExTetromino {
        <<abstract>>
        +BBOX BBox$
        +create(bbox, holes, hand) ExTetromino$
    }
    class ExTetromino2x3
    class ExTetromino2x4
    class ExTetromino3x3
    class ExTetromino3x4
    class ExTetromino4x4
    class Handedness {
        <<enumeration>>
        MINUS
        NONE
        PLUS
    }
    Piece <|-- Tetromino
    Piece <|-- ExTetromino
    ExTetromino <|-- ExTetromino2x3
    ExTetromino <|-- ExTetromino2x4
    ExTetromino <|-- ExTetromino3x3
    ExTetromino <|-- ExTetromino3x4
    ExTetromino <|-- ExTetromino4x4
    Piece --> Handedness

    class PieceFamily {
        <<frozen>>
        +name str
        +codes tuple
        +filter(category, connectivity, bbox, max_holes, handedness, ids) PieceFamily
        +include(items) PieceFamily
        +exclude(items) PieceFamily
        +union(other) PieceFamily
        +intersection(other) PieceFamily
        +preset(name) PieceFamily$
        +from_spec(spec) PieceFamily$
    }
    PieceFamily "1" o-- "1..34" Piece : codes of

    class Distribution {
        <<abstract>>
        +family PieceFamily
        +weights(history, count) dict
        +probabilities(history, count) dict
        +draw(rng, history, count) Piece
    }
    class UniformDistribution
    class WeightedDistribution {
        +table dict
        +default float
    }
    class ByPropertyDistribution {
        +rule RuleFn
        +strength float
    }
    class BagDistribution {
        +copies int
    }
    class AdaptiveDistribution {
        +base Distribution
        +drought_boost float
        +repeat_penalty float
    }
    class MixtureDistribution {
        +parts tuple
    }
    Distribution <|-- UniformDistribution
    Distribution <|-- WeightedDistribution
    Distribution <|-- ByPropertyDistribution
    Distribution <|-- BagDistribution
    Distribution <|-- AdaptiveDistribution
    Distribution <|-- MixtureDistribution
    Distribution --> PieceFamily : samples
    AdaptiveDistribution o-- Distribution : wraps
    MixtureDistribution o-- Distribution : combines

    class Board {
        <<frozen>>
        +width int
        +height int
        +filled frozenset
        +fits(piece, pos, wrap) bool
        +place(piece, pos, wrap) Board
        +clear_rows(gravity) tuple
        +drop_distance(piece, pos, wrap) int
    }
    class Rules {
        <<frozen>>
        +walls str
        +rotation str
        +gravity str
        +game_over str
        +spawn_position(piece) Position
        +kick_offsets() tuple
    }
    class Scoring {
        <<frozen>>
        +for_clear(lines, chains, level) int
    }
    class LevelPolicy {
        <<frozen>>
        +level_for(total_lines) int
        +gravity_ms(level) int
    }
    class GameState {
        <<frozen>>
        +board Board
        +active Piece
        +pos Position
        +queue tuple
        +mode Mode
        +score int
        +lines int
        +level int
        +history tuple
        +fired_triggers frozenset
        +to_json() dict
        +from_json(d) GameState$
    }
    class Engine {
        +state GameState
        +variant_hash str
        +tick(elapsed_ms) list
        +apply_action(action) list
        +request_update(path, value) None
        +reset(seed) list
        +save() str
        +resume(text, spec) Engine$
    }
    Engine o-- Rules
    Engine o-- Scoring
    Engine o-- LevelPolicy
    Engine o-- PieceFamily
    Engine o-- Distribution
    Engine --> GameState : replaces each step
    GameState *-- Board
    GameState --> Piece : active and queue
    Board ..> Piece : reads cells

    class TkinterRenderer {
        +draw(engine) None
    }
    class TkinterController {
        +start() None
        +run() None
        +act(action) None
        +save_to(path) None
        +load_from(path) None
    }
    TkinterController --> Engine : actions and ticks
    TkinterController *-- TkinterRenderer

    class VariantSpec {
        <<frozen>>
        +from_toml(path) VariantSpec$
        +engine_spec() dict
        +build_engine(seed) Engine
        +with_changes(changes) VariantSpec
        +to_toml() str
    }
    class SpecValidator {
        +errors list
        +warnings list
        +validate() bool
    }
    class VariantCustomizer {
        +open() None
    }
    VariantSpec ..> SpecValidator : validated by
    VariantSpec ..> Engine : builds
    VariantCustomizer --> TkinterController : pauses, then request_update
    VariantCustomizer --> VariantSpec : save as variant
    note for Engine "Headless: no tkinter, no timers, no file I/O"
```

**Why the piece hierarchy looks like this.** Spec §3.2 asks for classification "by shapes, bounding boxes, holes produced while landing in different orientations".
- **Two branches:** `Tetromino` holds the 7 edge-connected pieces, and `ExTetromino` the 27 that need a corner contact.
- **Bounding-box subclasses:** `ExTetromino` splits into 5 subclasses by bounding box, holding 2, 9, 9, 6 and 1 pieces.
- **Constructor parameters:** each subclass takes a *landing-hole signature* and a *handedness*. Together with the bounding box, these identify all 34 pieces. `piece.py` checks this when it builds its catalogue, and `verify_piece.py` test 3 checks it again.
- **Why not diagonal count:** the earlier key `(bbox, diagonal count)` in `v0.5_failed_attempt/` was ambiguous. It maps 27 pieces onto 11 keys, and it can never separate the 10 mirror pairs, because reflection preserves both properties.

---

## 3. Dynamic behaviour: tick, trigger, save and resume

```mermaid
sequenceDiagram
    autonumber
    participant UI as TkinterController
    participant E as Engine
    participant D as Distribution
    participant B as Board
    participant F as Save file (JSON)
    UI->>E: request_update("rules.walls", "wrap")
    Note over E: validated now, queued until the next tick boundary
    UI->>E: tick(16 ms)
    E->>E: apply queued updates, rebuild Rules
    E->>E: add 16 ms to gravity_acc, step down while it is at least gravity_ms(level)
    E->>B: fits(piece, pos + 1 row)?
    B-->>E: no, so lock
    E->>B: place() then clear_rows(gravity)
    B-->>E: new Board, lines, chains
    E->>E: score, total lines, level_for(total lines)
    E->>D: draw(rng, history, count)
    D-->>E: next Piece (pure weights + seeded rng)
    E->>E: triggers: lines_at_least 20 is now true, fire once
    E-->>UI: events: Locked, LinesCleared, LevelChanged, TriggerFired, ConfigChanged
    UI->>UI: TkinterRenderer.draw(engine)
    UI->>E: save()
    E->>F: state + rng + layers + variant_hash + payload_sha256
    UI->>E: Engine.resume(text, spec)
    E->>E: check payload_sha256 (edited file is refused)
    E->>E: check variant_hash(spec) (different variant is refused)
    E-->>UI: Engine with identical state and rng
```

```mermaid
stateDiagram-v2
    [*] --> RUNNING : Engine() / reset(seed)
    RUNNING --> PAUSED : Action.PAUSE
    PAUSED --> RUNNING : Action.PAUSE
    RUNNING --> GAME_OVER : block_out or top_rows rule
    PAUSED --> RUNNING : Action.RESET
    GAME_OVER --> RUNNING : Action.RESET
```

**What this design prevents:**
- `tick()` and the movement actions are ignored outside `RUNNING`, so pausing cannot create extra gravity loops (v0 BUG-03).
- There is exactly one clock: `TkinterController` keeps a single `after()` id, and `start()` cancels any existing one first.
- `GAME_OVER` is a mode, not `quit()`, so the board stays visible and New Game works (BUG-05).

---

## 4. Alignment with the paradigm (Bottom-Up, Modular, Imperative-OO)

| Paradigm element | Where it shows | Evidence |
|---|---|---|
| **Bottom-up** | Built and verified in layer order. Each layer had a passing check before the next started: L0 `piece.py` (Phase 2) → L1–L3 + L5 (Phase 3) → platform (Phase 4). | `verify_piece.py` 9/9 before `family.py`. `test_v1.py` 23/23 before `spec.py`. |
| **Cyclic top-down/bottom-up** | The blueprint (top-down) was revised by what implementation found (bottom-up). Rev 1.1 moved `Rules`/`Scoring`/`LevelPolicy` into `state.py` and replaced the planned `VariantSpec` in L4 with the engine's layered config plus the platform's `spec.py`. | `architecture_v1_blueprint.md` revision log |
| **Modular** | One responsibility per module, a downward-only import graph, and a single tkinter module. The platform copies the core modules unchanged into a package. | `test_engine_has_zero_tkinter`, `test_package_is_self_contained` |
| **Imperative core** | The engine is a state machine. `tick()`/`apply_action()` run imperative step loops (gravity accumulator, lock, clear, spawn) and *replace* `self.state`. | `engine.py` `_step_down`, `_lock`, `_spawn` |
| **Object-oriented** | Abstract classes with subclass polymorphism (`Piece`→`Tetromino`/`ExTetromino*`, `Distribution`→6 kinds). Composition (`Engine` *has* Rules, Scoring, LevelPolicy, PieceFamily, Distribution). Encapsulated invariants (`ShapeInfo`, read-only properties). | §2 diagram |
| **Functional elements** (where the spec asks for "functional-OO") | Immutable values (`Piece`, `Board`, `GameState`, `PieceFamily`, every distribution). Pure `weights(history)` functions. Distributions built from functions (`ByPropertyDistribution(rule=fn)`) and combinators (`mix`, `AdaptiveDistribution(base)`). | `test_distributions_are_deterministic_per_seed`, `test_determinism_same_seed_same_game` |
| **No code in data** | No `eval`/`exec` anywhere. TOML triggers use whitelisted conditions and targets. | `verify_piece.py` test 4, `test_triggers_fire_once_and_are_restricted`, `test_validator_plain_english` |

---

## 5. Configuration layers

```mermaid
flowchart LR
    DEF["DEFAULTS"] --> SPEC["spec (variant .toml), hashed with SHA-256"]
    SPEC --> PLAYER["player: ui, rules.preview, level.start_level"]
    PLAYER --> RT["runtime: RUNTIME_KEYS only, applied at the next tick"]
    RT --> EFF["effective config -> Rules / Scoring / LevelPolicy / PieceFamily / Distribution"]
    TRIG["[[triggers]] fire once when a whitelisted condition holds"] --> RT
    CUST["Variant Customizer"] --> RT
```

**What each layer may change:**
- `rules.width` and `rules.height` can only be set in the spec. Player and runtime layers are rejected with `ConfigError`.
- The variant hash covers DEFAULTS + spec, so a save game is tied to the exact variant it was played with.

---

## 6. Known limitations

- The landing-hole definition used for classification has **not yet been confirmed** against the 6 Nov tutorial. If it differs, only `piece._landing_holes()` and the piece codes change, and uniqueness must be re-verified.
- Rotation is about the bounding-box top-left with simple column kicks, not SRS.
- The PyInstaller spec is generated but was not built in the sandbox. `build.bat` has not been run on Windows by the AI.
