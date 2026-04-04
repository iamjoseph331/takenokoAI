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
- [x] Message counter per family for ID generation
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

- [x] 51 tests passing (family behavior, MessageCodec, broadcasts, S-path, idle detection, fallback routes, family states)
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

### Done — Browser Interaction

- [x] `BrowserSession` — Playwright wrapper (start/stop/click/type/screenshot/DOM snapshot)
- [x] `Re.browser` submodule — general browser perception (DOM + screenshot capture)
- [x] `Mo.browser` submodule — general browser action (click/type/navigate/wait/js)
- [x] Browser wiring in `run_agent.py` (config-driven, optional)
- [x] `default.yaml` browser config section
- [x] Submodule dispatch in Re.main and Mo.main for browser messages
- [x] 30 browser tests (BrowserSession, Re.browser, Mo.browser, dispatch)

### To Do — Game Rule Learning (Me.rules)

- [x] `Me.rules` submodule placeholder — basic add/get/query/clear rule storage
- [ ] Structured rule entries: rule text, source (user/inferred), confidence, game name
- [ ] LLM-powered rule query: given a game state, find relevant rules via semantic matching
- [ ] Rule refinement: update confidence or text when play experience contradicts a rule
- [ ] Rule conflict detection: flag when new rules contradict existing ones, ask user
- [ ] Multi-game support: store rules per game, switch context when game changes
- [ ] Rule persistence: save/load rules to disk across sessions
- [ ] Rule injection into Pr/Ev context: automatically include relevant rules when reasoning about moves
- [ ] Learning flow: user explains rules → Pr summarizes → Me.rules stores → Ev validates during play

### To Do — Game Integration

- [ ] End-to-end test: agent learns rules via conversation, then plays a browser game
- [ ] Turn detection: agent recognizes when it's their turn from browser state
- [ ] Move generation: Pr proposes moves based on rules in Me, Ev evaluates legality
- [ ] Game session management: start/end game, reset rules, track score

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

## Deferred / Future

- [ ] Configurable cognition paths via YAML (not hardcoded in bus.py)
- [ ] Event sourcing on bus (append-only message log for replay/analysis)
- [ ] Circuit-breaker pattern for LLM failures
- [x] Re sub-module: Browser (general Playwright perception)
- [ ] Re sub-modules: Vision, Audio, Net-Search (for web/VR per Q6 answer)
- [ ] Pr sub-module: Plan
- [x] Me sub-module: Rules (placeholder — game rule memory)
- [ ] Me sub-modules: Short-term, Long-term, Logs
- [x] Admin visualization app (WebSocket live view)
- [ ] Multi-agent scenarios (multiple TakenokoAI instances)
- [ ] Persistent message counter across restarts
