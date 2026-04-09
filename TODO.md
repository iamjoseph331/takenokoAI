# TakenokoAI — TODO

Status key: `[x]` done, `[ ]` to do, `[~]` partially done, `[!]` needs redesign

---

## Stage 0: Foundation (Infrastructure)

- [x] Project structure: five family dirs, interface/, admin/, prompts/
- [x] `MessageBus` with bounded queues, backpressure (`QueueFullSignal`), pause/resume
- [x] `BusMessage` Pydantic model with message ID format validation
- [x] Cognition path definitions (P, R, E, U, D, S) and route validation
- [x] `MainModule` / `SubModule` base classes with state machine, submodule registry
- [x] `LLMClient` wrapping litellm (supports OpenAI, Anthropic, Ollama)
- [x] `LLMConfig` dataclass with hot-swap via `update_config()`
- [x] `PromptAssembler` — 4-part system prompt (identity, self-model, rulebook, character)
- [x] `SelfModel` — async load/write of `self.md` by section with permission checks
- [x] `CharacterModel` — async load/write of `character.md` with Core + family merge
- [x] `PermissionManager` — grant/revoke/check with Pr-as-universal-authority
- [x] Structured logging (`ModuleLogger`) with rotating file + console
- [x] `DebugServer` (FastAPI) — /state, /families, /pause, /resume, /step, /inject, /talk, /ask
- [x] `run_agent.py` CLI with argparse (config, viz-port, debug-port flags)
- [x] `default.yaml` config with per-family model/temperature/max_tokens
- [x] Identity prompts for all five families
- [x] Character definitions (`character.md`) for all five families
- [x] Pr rulebook (`prediction/pr_rulebook.md`)
- [x] Trace ID propagation on bus messages
- [x] Message counter per family for ID generation (moved to shared bus counter)
- [x] `QueueFullPolicy` enum (WAIT/RETRY/DROP) for submodule backpressure
- [x] `Capability` dataclass and capability system for submodules
- [x] Decoupled `SubModule` from `MainModule` (depends only on interfaces)
- [x] Bus-based submodule registration (申告制 via message bus)
- [x] Submodules moved to `submodules/<Family>/` directory
- [x] Browser submodules: `Re.browser` (perception), `Mo.browser` (action)
- [x] Audio submodules: `Re.audio` (STT), `Mo.audio` (TTS)
- [x] Rules submodule: `Me.rules` (game rule memory)
- [x] Config-driven submodule boot in `main.py`
- [x] Markdown section parser (`markdown_utils.py`)
- [x] API key environment variable mapping for litellm
- [x] `conftest.py` with `mock_bus`, `mock_logger`, `mock_llm_config`, `mock_permissions` fixtures
- [x] `fastapi` and `uvicorn` in `pyproject.toml` as optional `[debug]` dependencies
- [x] Initial `self.md` with agent-level and per-family sections
- [x] Rulebooks: `re_rulebook.md`, `ev_rulebook.md`, `me_rulebook.md`, `mo_rulebook.md`
- [x] `README.md` with project overview and quickstart
- [x] LLM call timeout wrapper (asyncio.wait_for)
- [x] Injectable `completion_fn` on `LLMClient` for testing without API keys
- [x] Fix `MotionModule.get_output()` method
- [x] `.gitignore` for logs/ and *.egg-info/
- [x] PromptAssembler: load only Agent + own-family section of self.md
- [x] PromptAssembler: 5th section `<output-format>` auto-appended from FORMAT_INSTRUCTIONS
- [ ] Create `admin/visualization_app.py` or remove viz references from `run_agent.py`
- [ ] Create `.claude/lessons.md` for development learnings
- [ ] Make message counter persistent across restarts (save/load from file or self.md)
- [ ] Add `PermissionAction.WRITE_CHARACTER_MD` distinct from `WRITE_SELF_MD`
- [!] DRY: extract `MarkdownDocumentModel` base from `SelfModel`/`CharacterModel`

---

## Stage 1: Core Cognitive Loop

### Done — Message System

- [x] `MessageCodec` — parse LLM JSON output into `(body, path, receiver, summary)`
- [x] `FORMAT_INSTRUCTIONS` prompt template for LLM structured output
- [x] Broadcast circular buffer in MessageBus
- [x] `BusMessage.summary` and `is_broadcast` fields
- [x] `MessageBus.add_broadcast()`, `get_recent_broadcasts()`
- [x] `_build_broadcast_context()` helper on MainModule for LLM context injection (now includes family states)

### Done — S-Path & Idle Detection

- [x] `CognitionPath.S` in enum and VALID_PATH_ROUTES (sender == receiver for all families)
- [x] `_on_idle()` hook in message loop template (override for family-specific idle behavior)
- [x] Idle detection with budget system: nudge threshold, streak tracking, forced sleep, budget window
- [x] Adaptive timeout in message loop: 1s active, 5s idle (CPU savings)
- [x] Fallback route inference (`infer_fallback_route`) when LLM doesn't specify routing
- [x] Family state query callback (`_family_state_fn`) wired from orchestrator

### Done — Message Loop Template

- [x] Standard `_message_loop()` in MainModule: receive → ack → handle → idle
- [x] Per-family `_pause_event` for individual module pause/resume
- [x] Working `pause_and_answer()` on MainModule (pauses, queries LLM, resumes)
- [x] Abstract `_handle_message()` — each family implements its own processing

### Done — Module Implementation

- [x] `ReactionModule.perceive()` — classify input via LLM, route to R/E/U path
- [x] `ReactionModule.classify_input()` — LLM + MessageCodec decides path
- [x] `ReactionModule._handle_message()` — handles D-path directives from Pr
- [x] `PredictionModule.reason()` — LLM-based reasoning over context + evaluation
- [x] `PredictionModule.dispatch()` — send D-path directive to target family
- [x] `PredictionModule._handle_message()` — handle U-path from Re, P-path from Ev
- [x] `EvaluationModule.evaluate()` — LLM assessment with confidence extraction
- [x] `EvaluationModule.generate_affordances()` — higher temperature for creativity
- [x] `EvaluationModule._handle_message()` — validate Pr plans, evaluate Re input
- [x] `MemorizationModule.store/search/recall()` — in-memory store with substring search
- [x] `MemorizationModule._handle_message()` — dispatch store/search/recall actions
- [x] `MotionModule.speak()` — queues text output for chat loop
- [x] `MotionModule.do()` — logs and queues game action descriptions
- [x] `MotionModule.get_output()` — async queue for run_agent.py
- [x] `MotionModule._handle_message()` — extracts actions/plans/text from messages

### Done — Testing

- [x] 74 tests passing (family behavior, MessageCodec, broadcasts, S-path, idle detection, fallback routes, family states, submodule base, capabilities, policies, registration)
- [x] Injectable completion_fn enables all tests without LLM API

### To Do — Context & Conversation

- [ ] Context window manager — maintain conversation history within each module
- [~] Auto-populate message context (family states done via callback; parent body summary still manual)
- [ ] Attach "last N broadcasts" as context when processing messages (currently built but not automatically injected into every LLM call)

### To Do — Testing & Evaluation Harness

- [ ] Build per-module test harness: inject game state → get module-specific output
- [ ] Separate evaluation metrics for Re (classification accuracy), Pr (plan quality), Ev (assessment calibration)
- [ ] Prompt A/B testing framework: swap prompts, run same scenarios, compare outputs
- [ ] Model comparison framework: swap models per family, run same scenarios, compare outputs

### To Do — Game Integration

- [ ] Design `GameAdapter` interface (translates game engine ↔ Re/Mo text-based I/O)
- [ ] Implement Tic-Tac-Toe adapter
- [ ] Implement Poker adapter
- [ ] Implement Uno adapter
- [ ] End-to-end test: agent plays a full game of Tic-Tac-Toe

---

## Stage 2: Learning & Self-Improvement

- [ ] Design feedback structure for `update_weights()` — outcome schema, feedback flow from Mo → Ev
- [ ] Implement Ev weight storage and adjustment mechanism
- [ ] Cross-session learning: Pr writes lessons to self.md (already has section in rulebook)
- [ ] Me long-term memory: persist memories across restarts
- [ ] Me short-term memory: scoped to session/game with auto-expiry
- [ ] Self-evaluation: agent examines its own performance after each game
- [ ] 申告制 (Self-Registration): implement full announce → update self.md → broadcast flow
- [x] S-path idle detection: timer-based wake-up per module (resource-aware, suppressible) — moved to Stage 1
- [ ] S-path per-family idle prompts: tune what each family does when idle (e.g., Mo fidgets, Pr strategizes)
- [ ] S-path budget tuning: make thresholds configurable via YAML
- [ ] Broadcast storage revision (currently Option A, may need to change)

---

## Stage 3: Resource Management & Polish

- [ ] Track token count per family per session
- [ ] Track thinking time per family
- [ ] Track RAM usage
- [ ] Enforce resource limits from config
- [ ] State derived from workload/resource ratio
- [ ] Resource-aware scheduling: low-resource families get priority on bus
- [ ] Revise character.md vs identity prompts (keep separate for now per Q9 answer)

---

## Known Issues

- `QueueFullPolicy.WAIT` has no upper-bound timeout — a submodule could block indefinitely if its parent's queue never drains
- Submodule bus-registration is one-way — no deregistration message yet (only direct `unregister_submodule()` works)
- Message counter moved from MainModule to MessageBus — counter is no longer persistent across restarts (was already non-persistent, but the migration path changed)
- `register_submodule()` on MainModule kept for backward compatibility — remove in Stage 2
- Capability routing in Re/Mo `_handle_message()` forwards the original message to the bus rather than directly to the submodule queue — this means the submodule must be listening on its own bus queue to receive it
- Browser and audio submodule tests are not yet reimplemented for the new decoupled API (only `test_submodule_base.py` covers the new patterns)

---

## Diary

### 2026-04-07 — Submodule separation (feature/submodule-separation)

**What changed:**
- Decoupled `SubModule` from `MainModule`: constructor no longer takes `parent: MainModule`, instead takes explicit interface deps (bus, logger, permissions, llm_config)
- Added `QueueFullPolicy` enum (WAIT/RETRY/DROP) to `interface/bus.py` — submodules use this when sending messages to a full queue
- Moved message counter from `MainModule._message_counter` to `MessageBus._family_counters` — shared counter prevents ID collisions between MainModule and SubModule
- Added `interface/capabilities.py` with `Capability` dataclass — standardized pattern for submodule capability declaration
- SubModule now has `capabilities()` (abstract), `invoke()`, `_apply_policy()`, and `send_message()` — fully autonomous message sending
- Bus-based registration: `SubModule.start()` sends `_sub_register` message to parent queue; `MainModule._message_loop()` intercepts and stores in `_submodule_registry`
- MainModule gained `find_capability()` and `list_capabilities()` for capability discovery
- Moved all submodule files to `submodules/<Family>/` (e.g., `submodules/Re/re_browser.py`)
- Reimplemented browser, audio, and rules submodules with new decoupled API + capability system
- Added `interface/audio.py` (STT/TTS backends) and `interface/browser_session.py` (Playwright wrapper)
- Updated `main.py` with config-driven submodule boot phase
- Added `submodules` section to `default.yaml`
- 74 tests passing (51 existing + 23 new)

**Why:**
Four feature branches (cursor, model-selection, browser, audio) had conflicting submodule patterns. Browser submodules used action-based `handle_message()`, audio submodules used capability-based `invoke()`. Both depended on `parent: MainModule`. Merging them would have caused conflicts in `interface/modules.py`. This restructuring resolves the conflict by making all submodules independent of MainModule and standardizing on the capability pattern.

---

## Deferred / Future

- [ ] Configurable cognition paths via YAML (not hardcoded in bus.py)
- [ ] Event sourcing on bus (append-only message log for replay/analysis)
- [ ] Circuit-breaker pattern for LLM failures
- [ ] Re sub-modules: Vision, Net-Search (for web/VR per Q6 answer)
- [ ] Pr sub-module: Plan
- [ ] Me sub-modules: Short-term, Long-term, Logs
- [ ] Admin visualization app (WebSocket live view)
- [ ] Multi-agent scenarios (multiple TakenokoAI instances)
- [ ] Persistent message counter across restarts
