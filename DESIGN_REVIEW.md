# TakenokoAI Design Review

This document is a thorough audit of the codebase as of v0.1.0. It covers architectural flaws, design-concept mismatches, areas needing reconsideration, and open questions for the designer.

---

## 1. Flaws — Bugs and Broken Code

### 1.1 `MotionModule.get_output()` does not exist

`admin/run_agent.py:76` calls `mo_module.get_output(timeout=30.0)`, but `MotionModule` defines only `speak()` and `do()` — there is no `get_output` method anywhere in the class hierarchy. The chat loop is non-functional as written.

**Fix:** Either add `get_output()` to `MotionModule` (a future that resolves when Mo produces output) or redesign the chat loop to subscribe to Mo's bus queue directly.

### 1.2 Missing `conftest.py` for tests

`admin/utests/test_families.py` uses fixtures `mock_bus`, `mock_logger`, `mock_llm_config`, `mock_permissions` that are never defined. Tests will fail with `fixture not found`.

**Fix:** Create `admin/utests/conftest.py` with proper mock fixtures.

### 1.3 Missing rulebook files (4 of 5)

`default.yaml` references `reaction/re_rulebook.md`, `evaluation/ev_rulebook.md`, `memorization/me_rulebook.md`, `motion/mo_rulebook.md`. Only `prediction/pr_rulebook.md` exists. The prompt assembler silently returns empty strings for these, meaning 4 of 5 families boot with incomplete system prompts.

### 1.4 Missing dependencies in `pyproject.toml`

`admin/debug_api.py` imports `fastapi` and `uvicorn`, but neither is declared in `pyproject.toml`. Running the debug API will fail with `ModuleNotFoundError`.

**Fix:** Add `fastapi` and `uvicorn` to an `[project.optional-dependencies] admin` group, or to the main dependencies if they are always needed.

### 1.5 `asyncio.TimeoutError` vs `TimeoutError`

In `ev_main_module.py:79` and `me_main_module.py:93`, the idle loops catch `TimeoutError`. In Python 3.11+, `asyncio.wait_for` raises `asyncio.TimeoutError` which is a subclass of `TimeoutError`, so this works. However, the `except` is broad — document that this relies on PEP 654's aliasing (Python 3.11+), or explicitly catch `asyncio.TimeoutError` for clarity.

### 1.6 `send_ack` sends on an invalid route

`send_ack()` creates a `BusMessage` with no path field — the ack message ID uses a lowercased prefix but still carries a cognition path letter. Meanwhile `send()` on the bus doesn't validate routes for acks. This is probably fine, but the ack path validation is inconsistent: `validate_route()` exists but is never called for ack messages.

### 1.7 `SelfModel.load_part()` potential deadlock

`load_part()` calls `load_all()` (which acquires the lock) and then *also* tries to acquire the lock itself. If `load_all()` is called first, the lock is already held — this works because `load_all` releases before `load_part` tries to acquire. But if `_sections` is empty and `load_part` is called, it calls `load_all()` which acquires the lock, then `load_part` also acquires it — this works in asyncio (non-reentrant lock, but since load_all finishes first). Worth noting for correctness.

### 1.8 `notes` is a file, not a directory

`CLAUDE.md` says "See `/notes` for raw design notes." The actual `notes` is a plain file at the project root, not a directory. Minor but confusing.

---

## 2. Design-Concept Mismatches

### 2.1 The three core abilities are not independently testable yet

The central thesis is that intelligence = spontaneous prediction + reactive prediction + ability to gain from prediction. The codebase maps these to Re, Pr, and Ev. However:

- **There is no way to test them separately.** The `pause_and_answer()` method on each module raises `NotImplementedError`. The debug API's `/talk/{prefix}` endpoint bypasses the bus and calls the LLM directly, which tests the *LLM*, not the *module's cognitive function*.
- **There is no benchmark harness.** To compare model+prompt combinations, you need repeatable inputs with measurable outputs. Neither the game environments nor evaluation metrics exist.

**Question for designer:** What does "testing Reaction separately" look like concretely? Is it: "Given this game state, which cognition path did Re choose?" If so, the test would need a set of labeled inputs with expected path classifications.

### 2.2 Broadcast messages are designed but not implemented

The `notes` file describes a broadcast mechanism where summaries are shared across families as context. The bus has no broadcast capability — it only sends point-to-point messages. The message format in the notes specifies three parts (metadata, context with "last 5 broadcasted messages", body) but `BusMessage` has no `broadcast_history` or `summary` field.

This is a significant gap because the design relies on families having a "big picture" of what's happening.

### 2.3 S-path (self-path) is designed but not implemented

The `notes` describe an S-path where modules wake themselves up when idle, decide to find something to do, or decide to rest. This is core to the "human-like thinking" goal. Neither `CognitionPath` nor `VALID_PATH_ROUTES` include an S-path. The idle loops in Ev and Me just spin, doing nothing — they don't exhibit any spontaneous behavior.

### 2.4 Message context auto-assembly is designed but not implemented

The `notes` specify that message metadata and context (broadcast history, parent summary, family states) should be auto-appended by the system, with LLMs only generating body + path + summary. Currently, `send_message()` requires the caller to provide all fields manually. There is no auto-context injection.

### 2.5 `<Ev>` should initiate the P-path, but can't

The P-path is `Ev → Pr → Ev → Mo`. But Evaluation has no way to *start* a P-path flow. It can receive from Re on the E-path, but there's no logic to then initiate a P-path message to Pr. The `_message_loop` just acks and discards.

### 2.6 Memorization is passive — no integration with the cognition cycle

The design says Me stores logs and memories, but no family actually sends storage requests. Me's `_message_loop` is idle. In a human cognition model, memory is consulted during planning (Pr should query Me) and updated after evaluation (Ev should store outcomes). This wiring doesn't exist.

### 2.7 Character model uses `WRITE_SELF_MD` permission for character writes

`character_model.py:98` checks `PermissionAction.WRITE_SELF_MD` when writing to `character.md`. This is semantically wrong — character writes should have their own permission action (e.g., `WRITE_CHARACTER`), since controlling who can modify the agent's personality is a distinct concern from who can update the self-model.

---

## 3. Areas Requiring Reconsideration & Redesign

### 3.1 The "Five Families" framing obscures the three-ability core

The README, CLAUDE.md, and notes all frame the system as "five families." But the intellectual core is three abilities: reaction, prediction, evaluation. Memorization and Motion are *infrastructure* — they support the three abilities but don't represent independent cognitive functions. Treating all five equally obscures what you're actually trying to study.

**Suggestion:** Reframe the architecture as three cognitive modules (Re, Pr, Ev) plus two support modules (Me, Mo). The support modules should have simpler interfaces and don't need the full cognitive path machinery.

**Question for designer:** Do you agree that Me and Mo are support infrastructure rather than independent cognitive abilities? If so, should they still have their own LLM instances, or could they operate as deterministic services?

### 3.2 Every family gets an LLM — is this right?

Currently every family (including Mo and Me) gets its own LLM client. But does Memory need an LLM to store and retrieve data? Does Motion need an LLM to execute `play_card`? In many cases these are deterministic operations.

Giving every module an LLM makes the system expensive and slow. Consider whether Me and Mo should be LLM-free by default, with LLM access available as an optional upgrade (e.g., a submodule that uses LLM for semantic search in Me, or natural language generation in Mo).

**Question for designer:** Should Me's `search()` use embedding/LLM-based semantic search, or structured tag-based lookup? Should Mo format its own speech, or just relay what it receives?

### 3.3 The cognition paths are too rigid for real cognitive flexibility

The five paths (P, R, E, U, D) hardcode specific flows. But human cognition is more flexible:
- What if Ev wants to ask Re for more sensory input? (No path for this)
- What if Mo encounters an error and needs to report back? (No return path)
- What if Me discovers a relevant memory unprompted and wants to inform Pr? (Me has no outgoing path)

The current design forces all cross-family communication through Pr's D-path, making Pr a bottleneck.

**Question for designer:** Should there be a generic "request" path that any family can use to ask any other family for something (subject to permissions)?

### 3.4 The bus validates routes but doesn't enforce them

`MessageBus.send()` calls `_resolve_receiver()` but never calls `validate_route()`. Route validation exists as a static method but is only used in `MainModule.send_message()` which *logs a warning but sends anyway*. The route constraints are advisory, not enforced.

**Question for designer:** Should invalid-route messages be rejected (preventing architectural violations) or allowed with a warning (enabling flexibility)?

### 3.5 No conversation history or context window management

Each LLM call is stateless — it sends the system prompt plus the immediate messages. There is no conversation history, no context windowing, no summarization of past interactions. For game-playing (Stage 1 target), the agent needs to maintain game state across turns.

This is a fundamental gap for any multi-turn interaction. Where should conversation history live? Options:
1. In each family's LLM client (simple but duplicated)
2. In Me (canonical, but adds latency for every LLM call)
3. As part of the message context auto-assembly (the notes' design)

**Question for designer:** Should each module maintain its own running context window, or should context be centralized in Me and fetched on demand?

### 3.6 No game environment / adapter layer

Stage 1 targets are Tic-Tac-Toe, Poker, and Uno. There is no game environment, no state representation, no move validation, and no adapter that translates between game state and the agent's internal message format. This is a significant amount of work that the architecture doesn't account for.

**Suggestion:** Add a `games/` directory with an `Environment` protocol: `get_state()`, `valid_actions()`, `apply_action()`, `is_terminal()`. The runner (`admin/run_agent.py`) would mediate between the game environment and the agent's Re module.

### 3.7 `self.md` is read at boot but never meaningfully updated at runtime

The design describes `self.md` as a "living document" that the agent reads and writes at runtime. In practice, `SelfModel` loads at boot and the prompt assembler caches the result. No module ever calls `write_part()` during runtime. The 申告制 (self-registration) protocol is documented but never triggered.

### 3.8 Lack of structured output from LLM calls

The modules call `think()` which returns raw text. But the design needs structured data: path classification from Re, evaluation scores from Ev, action plans from Pr. There is no structured output parsing (e.g., JSON mode, function calling, or even regex extraction). This will be a constant source of bugs as you implement the modules.

**Question for designer:** Should TakenokoAI use structured output (JSON mode / function calling) from the LLMs, or free-form text with parsing?

### 3.9 Logging captures everything, but there's no way to query it

The design says "log everything," and the structured logger does capture family/module/category. But logs go to a rotating file. There is no way to query logs at runtime (e.g., "what did Pr think about in the last 5 turns?"). For debugging and for Me's "Logs" submodule, you need queryable structured storage, not just a log file.

**Suggestion:** Log to a structured store (SQLite, or at minimum an in-memory ring buffer per family) that Me's Logs submodule can query.

---

## 4. Open Questions for the Designer

These questions need clear answers before implementation can proceed. They are written here so they persist in the design docs.

### Q1: What is the unit of "testing a module separately"?

You said you want to "test Reaction, Prediction, and Evaluation separately by pausing the agent and sending questions to these modules directly." What does a test case look like?

- For Re: "Given input X, it should classify it as path Y" — is this an LLM judgment call or a deterministic rule?
- For Pr: "Given evaluation E from Ev, it should produce plan P" — how do you judge if P is good?
- For Ev: "Given situation S, it should assess it as A with confidence C" — what's the ground truth?

The `/talk/{prefix}` endpoint lets you send text to a module's LLM, but that tests the LLM+prompt combo, not the module's cognitive function within the system. What additional testing surface do you need?

### Q2: What does "self-examine" mean concretely?

You want the agent to "self-examine and learn." The S-path is part of this — a module reflecting on its idle state. But what should self-examination produce?

- Should Pr periodically review recent decisions and update its own prompt/weights?
- Should Ev assess the agent's recent performance and store findings in Me?
- Should the agent's `self.md` accumulate lessons learned across sessions?
- All of the above?

### Q3: How should the agent learn across sessions?

The `pr_rulebook.md` has a "Cross-Session Lessons" section that Pr is supposed to populate at runtime. But there's no mechanism for:
- Deciding when a lesson has been learned
- Persisting lessons beyond the current process
- Incorporating lessons into future behavior (beyond putting them in the prompt)

Is the learning model: "Ev evaluates outcomes → Pr extracts lessons → lessons get appended to self.md/rulebook → next session reads them as context"?

### Q4: How should the broadcast context window work?

The notes describe "last 5 broadcasted messages" as part of every message's context. Questions:
- Is 5 a fixed number or should it vary by family?
- Should the broadcast buffer be global (shared) or per-family (each family sees different broadcasts)?
- What happens when the context gets too long for the LLM's context window?

### Q5: How does the S-path interact with resource limits?

The S-path design says modules should consider their resource budget before deciding to self-activate. But resources aren't tracked until Stage 3. Should the S-path be a Stage 1 feature (using a simplified resource model like "count of LLM calls") or deferred to Stage 3?

### Q6: Should submodule registration actually modify the system prompt?

The 申告制 protocol says: when a submodule registers, the main module updates `self.md` and broadcasts the capability. This means the system prompt changes mid-session. Questions:
- Is prompt mutation during a session desirable? It invalidates cached context.
- Should there be a distinction between "hot-pluggable" submodules (added during runtime) and "cold" submodules (configured at boot)?

### Q7: What is Motion's role in game-playing?

For games, Mo needs to translate plans into game moves. But who validates the move is legal?
- Does Mo blindly execute and report the result?
- Does Ev validate the move before Mo executes?
- Does the game environment reject illegal moves, and if so, who handles the error?

### Q8: How should backpressure flow backward?

The bus returns `QueueFullSignal` when a queue is full. `send_message()` returns `"FULL:{msg_id}"`. But the calling module has no strategy for this — it doesn't retry, defer, or escalate. What should a module do when its target is overloaded?

---

## 5. File / Documentation Inconsistencies

| Issue | Location | Fix |
|-------|----------|-----|
| `CLAUDE.md` references `prompts/<family>/<prefix>_default.md` | Root | Actual path is `prompts/identity/<prefix>_identity.md` |
| `CLAUDE.md` references `admin/visualization_app.py` | Root | File does not exist |
| `CLAUDE.md` references `admin/debug/`, `admin/data/` | Root | Directories do not exist |
| `notes` is a file, not a directory | Root | Either rename or convert to `notes/` directory |
| No `README.md` | Root | The repo has no README (only a bare `README.md` with 1 line was viewed locally) |
| No `self.md` checked in | Root | Should a template `self.md` be in the repo? |
| No `TODO.md` in repo | Root | Was `TODO.md` local-only? Needs to be tracked |
| `default.yaml` references 4 missing rulebook files | `admin/yamls/` | Create stub rulebooks or remove references |
| `test_families.py` references undefined fixtures | `admin/utests/` | Create `conftest.py` |
| `run_agent.py` calls `mo_module.get_output()` | `admin/` | Method doesn't exist on `MotionModule` |

---

## 6. Summary of Priorities

### Must fix before any module implementation
1. Create missing `conftest.py` so tests can run
2. Add `get_output()` to MotionModule or redesign chat loop
3. Create stub rulebook files for Re, Ev, Me, Mo
4. Add `fastapi`/`uvicorn` to `pyproject.toml`
5. Fix `CLAUDE.md` file references

### Must design before Stage 1
1. Structured output format from LLM calls (Q8 in notes)
2. Conversation history / context window management (Section 3.5)
3. Game environment adapter layer (Section 3.6)
4. Broadcast message mechanism (Section 2.2)
5. Message context auto-assembly (Section 2.4)

### Should design before Stage 2
1. S-path and spontaneous behavior (Section 2.3)
2. Learning mechanism (Q3)
3. Queryable log storage (Section 3.9)
4. Submodule lifecycle and 申告制 runtime implementation (Q6)
