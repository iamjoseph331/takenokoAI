# TakenokoAI — TODO

Status key: `[x]` done, `[ ]` to do, `[~]` partially done, `[!]` needs redesign

---

## Stage 0: Foundation (Infrastructure)

### Done

- [x] Project structure: five family dirs, interface/, admin/, prompts/
- [x] `MessageBus` with bounded queues, backpressure (`QueueFullSignal`), pause/resume
- [x] `BusMessage` Pydantic model with message ID format validation
- [x] Cognition path definitions (P, R, E, U, D) and route validation
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
- [x] Test stubs for all five family modules (`test_families.py`)

### To Do

- [ ] Create `conftest.py` with `mock_bus`, `mock_logger`, `mock_llm_config`, `mock_permissions` fixtures
- [ ] Add `fastapi` and `uvicorn` to `pyproject.toml` as optional dependencies
- [ ] Create initial `self.md` with agent-level and per-family sections
- [ ] Create missing rulebooks: `re_rulebook.md`, `ev_rulebook.md`, `me_rulebook.md`, `mo_rulebook.md`
- [ ] Create `README.md` with project overview and quickstart
- [ ] Create `admin/visualization_app.py` or remove viz references from `run_agent.py`
- [ ] Add LLM call timeout wrapper (asyncio.wait_for around litellm calls)
- [ ] Add `completion_fn` injection to `LLMClient` for testing without API keys
- [ ] Fix `run_agent.py` — `MotionModule` has no `get_output()` method
- [ ] Create `.claude/lessons.md` for development learnings
- [!] Decide: should route validation be enforced or advisory? (see DESIGN_REVIEW.md Q10)
- [!] DRY: extract `MarkdownDocumentModel` base from `SelfModel`/`CharacterModel`
- [ ] Make message counter persistent across restarts (save/load from file or self.md)
- [ ] Add `PermissionAction.WRITE_CHARACTER_MD` distinct from `WRITE_SELF_MD`
- [ ] PromptAssembler: load only agent + own-family sections of self.md, not the entire document

---

## Stage 1: Core Cognitive Loop

### To Do — Message System

- [ ] Design LLM output format: `{body, path, receiver, summary}` — see notes line 159–163
- [ ] Build `MessageCodec` in base class to parse LLM output → `BusMessage` + broadcast
- [ ] Implement broadcast message queue (circular buffer in bus or per-family)
- [ ] Add `BusMessage.is_broadcast` field and broadcast delivery mechanism
- [ ] Attach "last N broadcasts" as context when processing messages
- [ ] Auto-populate message context (parent body summary, family states) without LLM involvement

### To Do — S-Path (Self-Path)

- [ ] Add `CognitionPath.S` to enum and route table (sender == receiver)
- [ ] Design idle detection: timer-based wake-up per module
- [ ] Implement S-path trigger in message loop template (idle threshold → "find something to do")
- [ ] Resource-aware S-path: suppress when budget is low
- [ ] S-path interrupt: new real message cancels pending S-path processing

### To Do — Module Implementation

- [ ] Implement `ReactionModule.perceive()` — classify input via LLM, route to R/E/U path
- [ ] Implement `ReactionModule.classify_input()` — LLM decides path
- [ ] Implement `ReactionModule._message_loop()` — receive D-path directives from Pr
- [ ] Implement `PredictionModule.reason()` — LLM-based reasoning over context + evaluation
- [ ] Implement `PredictionModule.dispatch()` — send D-path directive to target family
- [ ] Implement `PredictionModule._message_loop()` — handle U-path from Re, P-path from Ev
- [ ] Implement `EvaluationModule.evaluate()` — LLM-based assessment with confidence scores
- [ ] Implement `EvaluationModule.generate_affordances()` — brainstorm possible actions
- [ ] Implement `EvaluationModule._message_loop()` — handle E-path from Re, P-path from Pr
- [ ] Implement `MemorizationModule.store/search/recall()` — in-memory store for Stage 1
- [ ] Implement `MemorizationModule._message_loop()` — handle D-path store/retrieve requests
- [ ] Implement `MotionModule.speak()` — output text to channel
- [ ] Implement `MotionModule.do()` — execute game action
- [ ] Implement `MotionModule.get_output()` — collect output for chat loop
- [ ] Implement `MotionModule._message_loop()` — handle R/P/D-path action directives
- [ ] Implement `pause_and_answer()` on all five modules

### To Do — Message Loop Template

- [ ] Create standard `_message_loop` skeleton in `MainModule` (receive → ack → process → idle hook)
- [ ] Per-family pause mechanism (not just global bus pause)
- [ ] Context window manager — maintain conversation history within each module

### To Do — Testing & Evaluation Harness

- [ ] Build per-module test harness: inject game state → get module-specific output
- [ ] Separate evaluation metrics for Re (classification accuracy), Pr (plan quality), Ev (assessment calibration)
- [ ] Prompt A/B testing framework: swap prompts, run same scenarios, compare outputs
- [ ] Model comparison framework: swap models per family, run same scenarios, compare outputs

### To Do — Game Integration

- [ ] Design `GameAdapter` interface (translates game engine ↔ Re/Mo)
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
- [ ] Self-evaluation: agent examines its own performance after each game
- [ ] 申告制 (Self-Registration): implement full announce → update self.md → broadcast flow

---

## Stage 3: Resource Management

- [ ] Track token count per family per session
- [ ] Track thinking time per family
- [ ] Track RAM usage
- [ ] Enforce resource limits from config
- [ ] State derived from workload/resource ratio
- [ ] Resource-aware scheduling: low-resource families get priority on bus

---

## Deferred / Future

- [ ] Configurable cognition paths via YAML (not hardcoded in bus.py)
- [ ] Event sourcing on bus (append-only message log for replay/analysis)
- [ ] Circuit-breaker pattern for LLM failures
- [ ] Re sub-modules: Vision, Audio, Net-Search
- [ ] Pr sub-module: Plan
- [ ] Me sub-modules: Short-term, Long-term, Logs
- [ ] Admin visualization app (WebSocket live view)
- [ ] Multi-agent scenarios (multiple TakenokoAI instances)
