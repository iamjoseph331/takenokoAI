# TakenokoAI — TODO

Status key: `[x]` done, `[-]` in progress, `[ ]` not started, `[~]` deferred/blocked

---

## Stage 0 — Foundation (Infrastructure & Design)

### Done
- [x] Project structure: five family directories with main modules
- [x] Message bus with bounded queues, backpressure, and route validation
- [x] Permission system with Pr-authority model
- [x] LLM abstraction via litellm (OpenAI/Anthropic/Ollama)
- [x] Prompt assembler (4-part: identity, self-model, rulebook, character)
- [x] SelfModel — load/write/flush with permission-gated writes
- [x] CharacterModel — same pattern as SelfModel
- [x] Structured logging with rotating file + console
- [x] YAML configuration for families, models, and resources
- [x] Debug API (FastAPI) — pause/resume/step/inject/talk/ask
- [x] Chat loop runner (`admin/run_agent.py`)
- [x] Stub implementations for all five family modules
- [x] Trace ID propagation on bus messages
- [x] Ack message pattern
- [x] Markdown section parser
- [x] Family module unit test structure (stubs)
- [x] Prediction rulebook (`pr_rulebook.md`)
- [x] Identity prompts for all five families
- [x] Character definitions for all five families

### Bugs to fix
- [ ] Add `get_output()` to MotionModule (or redesign chat loop in `run_agent.py`)
- [ ] Create `conftest.py` with mock fixtures for tests
- [ ] Add `fastapi`, `uvicorn` to `pyproject.toml` optional deps
- [ ] Fix `CLAUDE.md` — update file paths to match actual tree
- [ ] Create missing rulebook files for Re, Ev, Me, Mo
- [ ] Convert `notes` file to `notes/` directory (or rename)
- [ ] Add a `WRITE_CHARACTER` permission action (currently reuses `WRITE_SELF_MD`)

### Design decisions needed (see DESIGN_REVIEW.md)
- [ ] Answer Q1: Define what "testing a module separately" means as concrete test cases
- [ ] Answer Q2: Define what "self-examine" produces — prompt updates? lesson logs? both?
- [ ] Answer Q3: Design the cross-session learning mechanism
- [ ] Answer Q4: Define broadcast context window parameters
- [ ] Answer Q5: Decide if S-path is Stage 1 or Stage 3
- [ ] Answer Q6: Decide on hot vs cold submodule registration
- [ ] Answer Q7: Define Mo's role in game move validation
- [ ] Answer Q8: Design structured LLM output format (JSON mode / function calling / parsing)

---

## Stage 1 — Make It Work (End-to-end cognition for games)

### Core message flow
- [ ] Implement ReactionModule.perceive() — classify input and route to R/E/U path
- [ ] Implement ReactionModule.classify_input() — LLM-based path classification
- [ ] Implement ReactionModule._message_loop()
- [ ] Implement PredictionModule.reason() — LLM-based reasoning over context + evaluation
- [ ] Implement PredictionModule.dispatch() — send directives via D-path
- [ ] Implement PredictionModule._message_loop() — handle U-path (from Re) and P-path (from Ev)
- [ ] Implement EvaluationModule.evaluate() — LLM-based assessment with confidence scores
- [ ] Implement EvaluationModule.generate_affordances() — brainstorm possible actions
- [ ] Implement EvaluationModule._message_loop() — handle E-path (from Re) and P-path (from Pr)
- [ ] Implement MotionModule.speak() — produce text output
- [ ] Implement MotionModule.do() — execute game actions
- [ ] Implement MotionModule._message_loop() — handle R/P/D-path directives

### Message system
- [ ] Implement broadcast message mechanism (summary messages visible to all families)
- [ ] Implement auto-context assembly (metadata + broadcast history + parent summary)
- [ ] Add `summary` field to BusMessage for broadcast digests
- [ ] Implement broadcast buffer (last N summaries per family)
- [ ] Structured output parsing for LLM responses (path/receiver/body/summary extraction)

### Memory (minimum viable)
- [ ] Implement MemorizationModule.store() — in-memory storage with tags
- [ ] Implement MemorizationModule.search() — tag-based lookup
- [ ] Implement MemorizationModule.recall() — by ID
- [ ] Implement MemorizationModule._message_loop() — handle store/search/recall requests

### Game environments
- [ ] Define `Environment` protocol: get_state, valid_actions, apply_action, is_terminal
- [ ] Implement Tic-Tac-Toe environment
- [ ] Implement game-agent adapter in run_agent.py (or a new runner)
- [ ] Implement Poker environment
- [ ] Implement Uno environment

### Testing & evaluation
- [ ] Implement `pause_and_answer()` for Re, Pr, Ev (direct module questioning)
- [ ] Create benchmark inputs for Re (input classification test suite)
- [ ] Create benchmark inputs for Pr (planning test suite)
- [ ] Create benchmark inputs for Ev (evaluation calibration test suite)
- [ ] Model/prompt comparison harness — run same inputs with different configs, collect metrics

### Supporting
- [ ] Add `get_resources()` / `get_limits()` stub implementations (return placeholder data)
- [ ] Conversation history management — per-module or centralized in Me
- [ ] Context window management — summarization when approaching token limits

---

## Stage 2 — Make It Think (Spontaneous behavior & learning)

### S-path (self-path)
- [ ] Add CognitionPath.S to bus
- [ ] Add S-path route validation (sender == receiver)
- [ ] Implement idle detection and self-activation in each module's message loop
- [ ] Design resource-aware self-activation (simplified token budget for now)
- [ ] "Find something to do" behavior for Pr when idle

### Learning
- [ ] Design outcome schema for Ev.update_weights()
- [ ] Implement feedback flow: Mo outcome → Ev → weight update
- [ ] Implement cross-session lesson extraction by Pr
- [ ] Persist lessons in self.md / rulebook
- [ ] Implement 申告制 (self-registration) at runtime — submodule announces → self.md update → broadcast

### Self-model as living document
- [ ] Runtime self.md updates when submodules are added/removed
- [ ] Periodic self-assessment entries written by Ev
- [ ] Strategy notes written by Pr after game completions

---

## Stage 3 — Make It Efficient (Resource management)

- [ ] Token counting per family (track input + output tokens)
- [ ] Thinking time tracking per LLM call
- [ ] RAM monitoring
- [ ] Resource-aware state transitions (IDLE → THINKING with budget checks)
- [ ] Resource-based backpressure strategy (what to do when budget is exhausted)
- [ ] Context compression / summarization to manage token budgets
- [ ] Resource dashboard in visualization app

---

## Infrastructure backlog

- [ ] Visualization app (`admin/visualization_app.py`) — real-time family state + message flow
- [ ] Queryable structured log store (SQLite or in-memory ring buffer)
- [ ] Circuit breaker for LLM failures (timeout → fallback → retry with backoff)
- [ ] Test seam for LLM client (inject mock completion_fn)
- [ ] Make VALID_PATH_ROUTES configurable via YAML
- [ ] CI pipeline (lint + test on push)
- [ ] Add `__init__.py` files to family directories if needed for packaging
