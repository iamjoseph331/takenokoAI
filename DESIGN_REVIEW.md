# TakenokoAI Design Review

This document contains a thorough code review, design critique, and open questions for the TakenokoAI project. It is organized into four sections:

1. **Concrete Flaws** — Bugs and code issues that would cause failures
2. **Design Misalignments** — Places where code doesn't reflect the stated design concept
3. **Redesign Suggestions** — Structural concerns that warrant reconsideration
4. **Open Questions** — Ambiguities that must be resolved before proceeding

---

## 1. Concrete Flaws

### 1.1 `run_agent.py` calls `mo_module.get_output()` which doesn't exist

`admin/run_agent.py:76` calls `await mo_module.get_output(timeout=30.0)`, but `MotionModule` has no `get_output` method. The chat loop would crash at runtime the moment a user sends input.

**Fix:** Either add `get_output()` to MotionModule, or redesign the chat loop to collect output from the bus (e.g. subscribe to Mo's outgoing messages).

### 1.2 Test fixtures are undefined — tests cannot run

`admin/utests/test_families.py` uses `mock_bus`, `mock_logger`, `mock_llm_config`, `mock_permissions` fixtures, but there is no `conftest.py` anywhere in the project. Running `pytest` will fail immediately with fixture-not-found errors.

### 1.3 Missing dependencies in `pyproject.toml`

`admin/debug_api.py` imports `fastapi` and `uvicorn`, but neither is declared in `pyproject.toml`. This will fail on a clean install.

### 1.4 Missing files referenced by config

`default.yaml` points to four rulebook files that don't exist:
- `reaction/re_rulebook.md`
- `evaluation/ev_rulebook.md`
- `memorization/me_rulebook.md`
- `motion/mo_rulebook.md`

Only `prediction/pr_rulebook.md` exists. The `PromptAssembler` handles this gracefully (logs and continues with empty string), but it means four out of five families operate with no behavioral rules in their system prompt.

### 1.5 `self.md` does not exist

The config sets `self_model_path: self.md`, but the file doesn't exist. `SelfModel.load_all()` handles this gracefully, but it means the agent boots with zero self-knowledge — the `<self-model>` section of every prompt is empty.

### 1.6 `visualization_app.py` does not exist

`run_agent.py` tries to import `admin.visualization_app.VizBroadcaster`. This module doesn't exist. Running without `--no-viz` will crash. The import is guarded by try/except, but both paths (admin.visualization_app and visualization_app) will fail.

### 1.7 Bus route validation is advisory, not enforced

`MainModule.send_message()` calls `MessageBus.validate_route()`, but on failure it only logs a warning and sends the message anyway. This means the cognition path constraints — a core design principle — are never actually enforced. Any module can send to any other module on any path.

### 1.8 Ack messages bypass route validation entirely

`send_ack()` calls `self._bus.send(ack)` directly, skipping the route validation in `send_message()`. This is necessary (acks go in reverse direction), but it means there are two separate send paths with different validation rules, which is fragile.

### 1.9 No timeout on LLM calls

`LLMClient.complete()` has no timeout. A hung LLM provider will block the module's message loop forever. The `SUGGESTION` comment in `modules.py` describes this problem but it's unimplemented.

### 1.10 `CharacterModel.write_section()` reuses `WRITE_SELF_MD` permission

Writing to `character.md` checks `PermissionAction.WRITE_SELF_MD`. This conflates two different resources. A module with permission to write its own self.md section also implicitly has permission to write its character.md section, which may not be intended.

### 1.11 Message counter not persistent across restarts

`MainModule._message_counter` resets to 0 on every boot. Message IDs from different sessions can collide (e.g. `Pr00000001P` in session 1 vs. session 2). This will corrupt log analysis and trace correlation.

---

## 2. Design Misalignments

### 2.1 The three core abilities are not testable separately

The stated vision is: *"intelligence = spontaneous prediction + reactive prediction + ability to gain from prediction"*, and the goal is to *"test them separately by pausing the agent and sending questions to these modules directly."*

The current code doesn't support this:
- `pause_and_answer()` raises `NotImplementedError` on every module.
- The debug API's `/talk/{prefix}` and `/ask` endpoints bypass `pause_and_answer()` entirely and call `think()` directly — making the designed method dead code.
- The bus pause (`pause_event`) is global — you can't pause one family while testing another.
- There's no "evaluation harness" that can feed a game state to Re/Pr/Ev individually and compare their outputs.

**What's needed:** A per-family pause mechanism, implemented `pause_and_answer()`, and a testing harness that can inject game states into individual modules.

### 2.2 No orchestration for multi-hop cognition paths

The P path is described as `Ev → Pr → Ev → Mo`. But there's no code that orchestrates this chain. Each module's `_message_loop()` is either a stub (`NotImplementedError`) or an idle receiver. When Ev sends to Pr on the P path, nothing tells Pr to process it and respond back to Ev. The chain would have to emerge from each module independently knowing its role — but there's no mechanism for this.

**What's needed:** Either a path-aware orchestrator that drives the chain, or clear per-module loop logic that continues the chain (e.g. Pr's loop knows that after receiving a P-path message from Ev, it must process and respond to Ev).

### 2.3 No mechanism for LLM output → structured bus message

The design notes describe LLMs generating: `(message body, path + receiver, short summary for broadcast)`. But the current code has no parsing layer. `think()` returns a raw string. There's no structured output format, no parsing, no validation of LLM-chosen paths.

**What's needed:** A `MessageCodec` or similar that defines the expected LLM output format (likely JSON or a structured template), parses it, validates the path/receiver, and constructs a `BusMessage`. This should live in the base class so all families share it.

### 2.4 Prompt assembly includes the entire self.md for every family

`PromptAssembler._load_self_model()` calls `self._self_model.load_all()` and reconstructs the full document. This means every family gets every other family's self-description in its system prompt. This wastes context tokens and gives families information they shouldn't need.

The design says each family owns its own section. The prompt should include: global agent section + the family's own section, not all five sections.

### 2.5 Broadcast messages are planned but not implemented or stubbed

The notes describe broadcast as a "type of message that has no designated receiver and doesn't require immediate action." Broadcasts should carry recent context for all families. But there's no `BusMessage.is_broadcast`, no broadcast queue, no mechanism to attach recent broadcasts to message context. This is a core part of the message system design that has no code footprint.

### 2.6 S-path (self-path) is designed but not represented in code

The notes describe S-path as critical to avoiding idle agents. The `CognitionPath` enum has only P, R, E, U, D — no S. There's no idle detection, no periodic wake-up, no mechanism for a module to send a message to itself. This is a significant feature gap since it directly addresses the "anything a human can do" goal (humans don't just wait for input — they think spontaneously).

### 2.7 SelfModel and CharacterModel are near-identical code

Both manage markdown sections with async lock, load, write, flush, and parse. The only meaningful difference is `CharacterModel.load_for_family()` which merges Core + family sections. These should share a base class (`MarkdownDocumentModel` or similar) to eliminate duplication.

### 2.8 No conversation history / context window management

When `think()` is called, it receives a `messages` list, but there's no mechanism to maintain conversation history within a module. Each `think()` call is stateless — the module has no memory of previous exchanges. The LLM sees: system prompt + whatever messages are passed in the current call. For multi-turn reasoning (which the P path requires), there needs to be a context window manager.

---

## 3. Redesign Suggestions

### 3.1 Separate "cognitive" families from "infrastructure" families

The design thesis centers on three abilities, but the architecture has five families. Memorization and Motion are support infrastructure — they don't represent cognitive abilities. Consider:

```
Core Cognitive Families (testable abilities):
  Re — reactive prediction (perceiving/classifying)
  Pr — spontaneous prediction (planning/reasoning)
  Ev — gain from prediction (evaluating/learning)

Infrastructure Families:
  Me — memory (storage/retrieval service)
  Mo — motor (output execution service)
```

This distinction should be explicit in the architecture. Infrastructure families should have simpler interfaces (they're services, not thinkers). They probably don't need full LLM clients — Me needs an embedding model for search, Mo needs an output adapter, not a general-purpose reasoning LLM.

### 3.2 The permission system needs scope categories, not a flat list

Currently permissions are `(grantee, action, target)` where target is a family prefix or `*`. But the notes describe needing temporal permissions ("revoke after task") and resource-scoped permissions ("write only this section of self.md"). The current flat list doesn't support this.

Consider adding: `PermissionScope(resource_type, resource_id, expires_at)`.

### 3.3 Consider a "context builder" for messages instead of prompt-level context

The notes describe wanting message context to include "last 5 broadcasts, parent message body, current state of all families." Currently, context is a string field on BusMessage with no structure. 

Instead of cramming everything into the LLM prompt (which wastes tokens), consider a `ContextBuilder` that assembles the relevant context just-in-time when a module processes a message. This keeps messages lean on the bus and context rich at processing time.

### 3.4 Make `LLMClient` injectable for testing

The SUGGESTION comment in `llm.py` describes this correctly. Accept a `completion_fn` parameter that defaults to `litellm.acompletion`. This is critical — without it, every test requires a live LLM API, which is expensive and non-deterministic.

### 3.5 Consider event sourcing for the bus

Currently, messages are fire-and-forget through queues. There's no history, no replay, no audit trail (beyond logs). If you want to analyze how the agent thought about a game move, you'd have to parse log files.

Consider recording all bus messages to an append-only log (in-memory for Stage 1, persistent later). This gives you: replay capability, debugging (show me the full P-path chain for this turn), and training data for improving prompts.

### 3.6 The `_message_loop` pattern needs a standard skeleton

Every family needs to implement `_message_loop()`, but the loops share common patterns: receive message → ack → check state → process → potentially send response. Currently, Ev and Me have idle loops, Re/Pr/Mo raise NotImplementedError. 

Consider a template method in `MainModule`:

```python
async def _message_loop(self):
    while self._running:
        message = await self._receive_with_timeout()
        if message is None:
            await self._on_idle()  # S-path hook
            continue
        await self.send_ack(message)
        await self._handle_message(message)  # abstract
```

This ensures consistent behavior (acking, idle detection) across all families.

---

## 4. Open Questions (Requiring Your Decision)

These questions represent ambiguities in the current design that should be resolved before implementation proceeds. Please answer them here or in a separate design decisions document.

### Q1: How do the three abilities map to the five families?

The notes say: *"spontaneous predicting ability, reactive predicting ability, and the ability to gain from prediction."*

- **Reactive prediction → Re?** But "reaction" implies responding to stimuli, not predicting. Is the idea that perceiving = predicting what the environment will present? If Re is about prediction, why is it named "Reaction"?
- **Spontaneous prediction → Pr?** This mapping is clearest. Pr plans and reasons without being prompted by external stimuli.  
- **Gain from prediction → Ev?** Evaluation is about judging outcomes, but "gaining from prediction" could also mean learning and updating behavior, which touches Me (remembering lessons) and updating prompts.

**Your answer:** Reactive prediction is a kind of prediction ability that does not require bayes update and happens in a shorter period of time. Things like knowing a pen is falling when it rolled towards the edge of a table, or knowing the meaning of words on a wall are all reactive prediction. Contrary, spontaneous prediction is a more long termed, bayes updated prediction ability. Beliefs such as: doing this will lead to this result are typical spontaneous prediction. Gainability, moreformally written as "the ability to gain benefit from the prediction", actually has its two most important components in <Ev>. They are the ability to generate afforded actions (possible actions) and the ability to correctly evaluate the state. What action will lead to what state is the responsibility of spontaneous prediction. <Mo> runs the action. You are right that <Me> provides the materials for learning, but learnt preference lies in <Ev>.

### Q2: What does "testing the three abilities separately" look like concretely?

Scenario: The agent is playing Tic-Tac-Toe. It's the agent's turn.

- Testing Re alone: Given the board state, does Re correctly perceive and classify the situation?
- Testing Pr alone: Given a perception + evaluation, does Pr generate a good plan?
- Testing Ev alone: Given a board state and a proposed move, does Ev correctly assess it?

Is this the right mental model? Or is "testing separately" more about testing different LLM/prompt combinations for each family and comparing their performance?

**Your answer:** This is basically the idea. However, testing separately actually means that I have a test bed in mind with multiple specifically designed tests to test on the AI agent, and playing games is just to make sure that the basic structure works as planned. To make the answer more concrete, Testing Pr alone, it should generate the possible outcome of each possible action, at least to some layers of depth. Testing Ev alone, it should be able to give me all possible moves, alongside with if it is in an advantage or disadvantage state. (Ideally, <Re> should know that Tic-Tac-Toe is easy enough to handle itself and skip the P path)

### Q3: How should the S-path idle trigger work?

The notes describe: *"the system will periodically tell the modules that you have been idle for how long and how much resources to use, then the module will decide to fire an S-path message."*

- Who is "the system"? The main loop? The bus? A timer in each module?
- Should all five families have S-path, or only the cognitive three (Re, Pr, Ev)?
- How does S-path interact with resource limits? If the agent has used 80% of its thinking budget, should S-path be suppressed?
- Can S-path messages be interrupted mid-processing by a real message?

**Your answer:** Let all modules have the S-path and leave the idle poking to stage 2, where I introduce the whole resource managing system. If the agent has used 80% of its thinking budget, S-path should be suppressed. I want to let S-path messages postpone if in the queue there are other messages.

### Q4: Where do broadcast messages live?

The notes describe broadcasts as context that gets included when any message arrives. Options:

- **Option A:** Circular buffer in the MessageBus itself (simple, ephemeral)
- **Option B:** Stored in Me family (persistent, searchable, but adds latency)  
- **Option C:** Each module maintains its own recent-broadcasts buffer (distributed, no single point of failure)

Each has different trade-offs for latency, persistence, and consistency.

**Your answer:** A but add into TODO to revise later

### Q5: What if the LLM generates an invalid path or receiver?

The design says LLMs generate `(body, path+receiver, summary)`. LLMs can hallucinate.

- Should invalid paths be rejected (hard fail)?
- Should they be corrected to the nearest valid path (soft fail)?
- Should there be a "retry with feedback" loop where the module re-prompts the LLM?
- Is there a default fallback path (e.g. always fall back to D-path from Pr)?

**Your answer:** Infer and send system message. I'm doing it in another branch now. Leave it for now.

### Q6: How does a game environment connect to the agent?

For Stage 1 (Tic-Tac-Toe, Poker, Uno), the agent needs to:
1. Receive game state → through Re?
2. Output a move → through Mo?
3. Know the game rules → through Pr's prompt? Through Me's stored knowledge?
4. Track game progress → through Me?

Is there a "game adapter" that sits outside the agent and translates between the game engine and Re/Mo? Or is the game engine a sub-module of Re (input) and Mo (output)?

**Your answer:** There will be sub-modules iof Re and Mo doing things like perceiving and controlling web pages, or similar things in VR space. For now, text base is fine.

### Q7: What differentiates short-term from long-term memory?

The notes list Me sub-modules: Short-term, Long-term, Logs. But:

- **Short-term:** Is this the current conversation / current game? How long does it persist?
- **Long-term:** Is this cross-session knowledge? Where is it stored (files, database)?
- **Logs:** Are these different from the file logs already managed by `interface/logging.py`?

**Your answer:** Only do logs now. Keep the TODO for stage 2.

### Q8: Should Ev's evaluation and affordance generation be the same LLM call?

Currently `evaluate()` and `generate_affordances()` are separate methods. But:
- Evaluation is retrospective: "How did that go? How good is this state?"
- Affordance generation is prospective: "What could we do from here?"

These might benefit from different LLM temperatures or even different models. Evaluation needs precision (low temperature); affordance generation needs creativity (higher temperature).

**Your answer:** Use the same model with different temperatures for now.

### Q9: Is `character.md` distinct enough from identity prompts to justify the token cost?

Every module's system prompt includes: `<identity>` (what it is) + `<character>` (how it behaves). These overlap significantly. For example, the Pr identity says "central intelligence responsible for planning" and the Pr character says "deliberate and strategic."

Including both in every LLM call costs tokens. Is the distinction valuable enough? Or could character traits be folded into the identity prompts?

**Your answer:** keep separate but add in TODO for revision in stage 3 

### Q10: Should the bus enforce paths or just log violations?

Currently, route validation logs a warning but sends anyway. Two options:

- **Enforce:** Invalid routes are rejected. This is safer but means bugs in path selection silently drop messages.
- **Advisory:** Invalid routes are warned but delivered. This is forgiving but means the path constraints are just conventions, not invariants.

A middle ground: enforce in production, advisory in debug mode (configurable).

**Your answer:** make it advisory for now but log errors.

---

## Summary of Priority Issues

Ordered by impact on the project's ability to function:

1. **No working cognitive loop** — All core module methods are stubs. Nothing actually runs.
2. **No LLM output parsing** — Even when stubs are filled, there's no way to turn LLM output into bus messages.
3. **No separate testing mechanism** — The core goal (test abilities separately) has no infrastructure.
4. **Missing S-path and broadcasts** — Key features from the design notes with zero code footprint.
5. **run_agent.py is broken** — `get_output()` doesn't exist.
6. **Tests can't run** — Missing conftest.py.
7. **Missing rulebooks** — 4 of 5 families have no behavioral rules.
8. **No conversation context** — Modules are stateless across calls.
9. **No LLM timeout** — A single API failure hangs the entire agent.
10. **Duplicate code** — SelfModel / CharacterModel should share a base.
