# Plan: Rewrite self.md + Update System to Match Design Decisions

## Context

The user drafted a comprehensive self.md template defining the agent's self-awareness, memory architecture, paths, and per-family roles. Comparing the draft against the actual implementation revealed gaps, new feature specs, and design ambiguities. 10 design questions were resolved through discussion. This plan implements those decisions.

### What Prompted This

The user wrote a draft self.md (in Chinese) that described the system more richly than what was implemented — including Me's 5 memory types, an N path, Ev state authority, multiple-output LLM format, and sleep mode. The draft was compared line-by-line against the codebase to identify what exists, what's missing, and what conflicts.

---

## Design Decisions (Resolved)

| # | Question | Decision | Implementation |
|---|----------|----------|----------------|
| 1 | Me's 5 memory types (short/long/context/logs/eternal) | Document as intended design; implement later | self.md describes all 5; code stays as-is (flat dict); new Stage 2 in TODO |
| 2 | `[[term]]` dictionary notation | Hint to LLM only — no code parsing | Document in rulebooks that `[[]]` means "Me has info on this" |
| 3 | N path (unrestricted routing) | Add `CognitionPath.N` to enum | All 25 (sender, receiver) pairs valid; update regex |
| 4 | Ev state authority | Direct authority via bus protocol | New `PermissionAction.SET_STATE`, grant to Ev, new `_set_state` bus message |
| 5 | Re message priority | Deferred to Stage 3 | Document intent in self.md and TODO only |
| 6 | Sleep mode (day change -> Me consolidation) | Document concept only | Describe in self.md; add to Stage 2 TODO |
| 7 | Multiple LLM outputs per message | Change FORMAT_INSTRUCTIONS to array now | Backward-compat: single-object wraps to `[{...}]` |
| 8 | Language of self.md | All English | Translate the Chinese draft |
| 9 | self.md scope | Awareness only (duplicates OK for now) | User will condense into identity/rulebook/character later |
| 10 | Cross-visibility | All family sections visible to all families | Change PromptAssembler to load full self.md |

---

## Task Breakdown

### Task 1: Rewrite `self.md` (English, awareness-focused)

**File:** `self.md`

Translate the user's Chinese draft into English. Structure:

**## Agent section** should contain:
- Who you are: anthropomorphic AI agent by Joseph Chen, based on EPH theory (three core abilities of intelligence), five families forming one mind
- System overview: five families (Pr, Re, Ev, Me, Mo), each with own LLM, self.md section, character.md section, rulebook
- Data structures: self.md, rulebooks, memory database, character.md, family folders
- Tools: submodules (per-family addons), self.md editing (own section; Pr can edit all), Me memory queries
- `[[]]` notation: terms wrapped in `[[]]` indicate Me's dictionary zone has info — query Me to retrieve
- Paths table with examples:

| Path | Flow | Purpose | Example |
|------|------|---------|---------|
| P | Ev -> Pr -> Ev -> Mo/Me | Deliberate thought — Pr-led deep reasoning | Thinking about next chess move |
| R | Re -> Mo | Reflex — Re-led fast reaction | Catching a falling pen |
| E | Re -> Ev | Evaluation — pre-P-path judgment | Sending board state to Ev |
| U | Re -> Pr | Uptake — Re delegates to Pr | User asks "what can you do?" |
| D | Pr -> any | Dispatch — Pr commands action | "Organize memories" / "Check the door" |
| S | self -> self | Self-directed thought | Idle reconsideration, submodule registration |
| N | any -> any | Unrestricted — trust the family's judgment | Emergency situations not covered by other paths |

- Message bus: bounded async queues per family, backpressure via QueueFullSignal, message ID format `<prefix><8-digit><path letter>` (e.g. `Pr00000012P`)
- Broadcasts: every message's `summary` field enters a circular buffer; all families see recent broadcasts for situational awareness
- Submodules: addon tools for each family's main module. Added/removed at runtime. On change, the main module updates its self.md section and broadcasts to all families. Registration follows shinkokusei (self-registration protocol). Located in `submodules/<Family>/`
- Multiple outputs: receiving one message can produce multiple outgoing messages on different paths (e.g., Re sends U-path to Pr AND R-path filler to Mo simultaneously)
- Permissions: Pr has universal authority (write any self.md section, grant/revoke permissions). Ev has SET_STATE authority on all families. Each family can edit its own scope freely.
- Sleep mode (FUTURE): on day change, the system enters sleep mode. Resources concentrate on Me for memory consolidation (short-term -> long-term). Not yet implemented.
- ACK protocol: every message is automatically acknowledged. ACK messages have lowercased prefix in ID.
- Output format: respond in JSON array format (details in `<output-format>` tag of the prompt)
- Queue backpressure: when a queue is full, send returns `FULL:<msg_id>`. Submodules use QueueFullPolicy (WAIT/RETRY/DROP).
- Idle/S-path: after idle threshold (5s), modules receive "nudge" callbacks. Budget: 3 self-messages per 60s window. After 5 consecutive nudges, forced sleep for 60s.

**## Re section:**
- Role: sensory input core, fastest LLM, passive thinking (reflexive classification), highest bus priority (Stage 3 feature)
- Paths: R (->Mo), E (->Ev), U (->Pr); can receive D (<-Pr)
- Submodules: browser (observe, screenshot), audio (transcribe)
- Family folder: `reaction/`, submodules: `submodules/Re/`

**## Pr section:**
- Role: central cognition, most complex LLM, active thinking, the loudest voice in the mind. When families conflict, Pr's opinion wins.
- Paths: P (<->Ev), U (<-Re), D (->any family)
- Authority: universal write permission, can grant/revoke cross-family permissions
- Submodules: (none yet)
- Family folder: `prediction/`, submodules: `submodules/Pr/`

**## Ev section:**
- Role: evaluation core, largest context LLM. Evaluates system state (resource usage, family health), environment state, task progress. Generates all afforded actions for Pr to predict outcomes. Determines the system's value system.
- Paths: E (<-Re), P (<->Pr)
- Authority: SET_STATE on all families (direct authority to change any family's state)
- Submodules: (none yet)
- Family folder: `evaluation/`, submodules: `submodules/Ev/`

**## Me section:**
- Role: memory and logs
- 5 memory types (DESIGN — implementation in Stage 2):
  1. **Short-term memory**: Records of interactions with the outside world, plus entries Pr explicitly adds. Expires at session end.
  2. **Long-term memory**: Large key-value database. An LRU cache loads the 20 most recently accessed entries into working memory, called the "dictionary zone". Terms in `[[]]` refer to entries here.
  3. **Full context log**: Message summaries from the entire day. The LLM sees only the most recent 5-10, but Me preserves the full day's log until day change or memory pressure.
  4. **Logs**: System execution logs produced by all families.
  5. **Eternal memory**: Five memories deemed most important. They are permanently pinned in Me's LLM context and never evicted.
- Current implementation: flat in-memory dict with `store/search/recall` and string tags
- Submodules: rules (add_rule, get_rules, query_rules, clear_rules)
- Family folder: `memorization/`, submodules: `submodules/Me/`

**## Mo section:**
- Role: motor output and execution core. Operates the body, produces speech, performs actions. Has the most submodules.
- Paths: R (<-Re), P (<-Ev), D (<-Pr)
- Does not decide what to do — executes what it is told, faithfully and precisely
- Submodules: browser (click, type, press, navigate, wait, js), audio (synthesize)
- Family folder: `motion/`, submodules: `submodules/Mo/`

---

### Task 2: Add `CognitionPath.N` to `interface/bus.py`

**File:** `interface/bus.py`

1. Add to enum:
```python
class CognitionPath(StrEnum):
    P = "P"
    R = "R"
    E = "E"
    U = "U"
    D = "D"
    S = "S"
    N = "N"  # Unrestricted: any sender -> any receiver
```

2. Add to `VALID_PATH_ROUTES`:
```python
CognitionPath.N: [
    (s, r) for s in FamilyPrefix for r in FamilyPrefix
],
```

3. Update regex:
```python
MESSAGE_ID_PATTERN = re.compile(
    r"^(Re|Pr|Ev|Me|Mo|re|pr|ev|me|mo)\d{8}[PREUDSN]$"
)
```

---

### Task 3: Add `PermissionAction.SET_STATE` + Ev authority

**File:** `interface/permissions.py`

1. Add to enum:
```python
class PermissionAction(StrEnum):
    WRITE_SELF_MD = "WRITE_SELF_MD"
    READ_CROSS_FAMILY = "READ_CROSS_FAMILY"
    SEND_CROSS_FAMILY = "SEND_CROSS_FAMILY"
    CHANGE_PROMPT = "CHANGE_PROMPT"
    CHANGE_MODEL = "CHANGE_MODEL"
    RESTART_MODULE = "RESTART_MODULE"
    SET_STATE = "SET_STATE"
```

2. In `_init_defaults()`, after the Pr universal grants loop, add:
```python
# Ev has authority to set state on all families
self._grants.append(
    PermissionGrant(
        grantee=FamilyPrefix.Ev,
        action=PermissionAction.SET_STATE,
        target="*",
        granted_by=FamilyPrefix.Pr,
    )
)
```

**File:** `interface/modules.py`

3. Add method to `MainModule`:
```python
async def request_state_change(
    self, new_state: ModuleState | str, requester: FamilyPrefix
) -> None:
    """Change this module's state. Permission-checked (SET_STATE)."""
    if not self._permissions.check(
        requester, PermissionAction.SET_STATE, self.family_prefix.value
    ):
        raise PermissionError(
            f"{requester} lacks SET_STATE permission on {self.family_prefix}"
        )
    await self.set_state(new_state)
    self._logger.action(
        f"State changed to {new_state} by {requester}"
    )
```

4. In `_message_loop()`, after the `_sub_register` interception block, add:
```python
# Intercept state change requests from Ev
if (
    isinstance(message.body, dict)
    and message.body.get("_set_state")
):
    new_state = message.body.get("new_state", "IDLE")
    try:
        await self.request_state_change(new_state, message.sender)
    except PermissionError as e:
        self._logger.action(f"State change denied: {e}")
    continue
```

---

### Task 4: Change LLM output format to array

**File:** `interface/message_codec.py`

1. Update `FORMAT_INSTRUCTIONS`:
```python
FORMAT_INSTRUCTIONS = """You MUST respond in valid JSON. Your response contains one or more messages to send.

Format — array of messages:
{
    "messages": [
        {
            "body": "<your response/reasoning>",
            "path": "<one of: P, R, E, U, D, S, N>",
            "receiver": "<one of: Re, Pr, Ev, Me, Mo>",
            "summary": "<one-line broadcast summary>"
        }
    ]
}

Rules:
- "messages" is an array of one or more messages to send.
- Each message has: body, path, receiver, summary.
- "body" contains your actual response content.
- "path" is the cognition path for the message.
- "receiver" is the target family.
- "summary" is a short broadcast that all families will see.
- You may send multiple messages at once (e.g., send reasoning to Pr AND a filler response to Mo).
- If you have nothing to send (just internal thought), use a single message with path "S" and receiver set to your own family prefix."""
```

2. Add new function `parse_llm_outputs()` that returns `list[ParsedLLMOutput]`:
- If parsed JSON has `"messages"` key -> iterate and parse each
- If parsed JSON has `"body"` key (old single format) -> wrap in list
- If JSON parse fails -> return `[ParsedLLMOutput(body=raw, ...)]` as before
- Keep `parse_llm_output()` as a convenience that returns the first item (backward compat)

3. Update all 5 family `_handle_message()` methods:
- Where they currently call `parse_llm_output()` and send one message, change to call `parse_llm_outputs()` and loop over results, sending one bus message per parsed output.

**Files also affected:**
- `reaction/re_main_module.py`
- `prediction/pr_main_module.py`
- `evaluation/ev_main_module.py`
- `memorization/me_main_module.py`
- `motion/mo_main_module.py`

---

### Task 5: Update PromptAssembler to load full self.md

**File:** `interface/prompt_assembler.py`

Change `_load_self_model()` from:
```python
for header in ("_preamble", "Agent", self._family_prefix.value):
```
To load all sections:
```python
for header, body in sections.items():
    if not body:
        continue
    if header == "_preamble":
        lines.append(body.strip())
    else:
        lines.append(f"## {header}\n{body.strip()}")
```

---

### Task 6: Update `TODO.md`

**File:** `TODO.md`

1. Rename "Stage 2: Learning & Self-Improvement" -> "Stage 2.5: Learning & Self-Improvement"

2. Insert new "Stage 2: Me Memory Architecture":
```markdown
## Stage 2: Me Memory Architecture

- [ ] Implement 5-type memory store (short-term, long-term, context log, logs, eternal)
- [ ] Long-term memory: key-value DB with LRU cache of 20 ("dictionary zone")
- [ ] Eternal memory: 5 pinned items always in Me's LLM context
- [ ] Full context log: store all message summaries per day
- [ ] Short-term -> long-term promotion mechanism
- [ ] `[[]]` notation: optionally pre-expand from Me's dictionary (or keep as hint)
- [ ] Sleep mode: day-change trigger, pause families, Me consolidation, resume
```

3. Add to Stage 3: `- [ ] Re message priority on bus (priority queues or similar)`

4. Add diary entry:
```markdown
### 2026-04-10 — self.md rewrite + design decisions

**What changed:**
- Rewrote self.md in English with full system awareness (paths, bus, permissions, memory design, submodules)
- Added CognitionPath.N (unrestricted routing, all sender/receiver pairs valid)
- Added PermissionAction.SET_STATE with Ev granted direct authority over all family states
- Changed LLM output format from single JSON object to array of messages (backward compat preserved)
- Updated PromptAssembler to load all self.md sections (not just Agent + own family)
- Created new Stage 2 (Me Memory Architecture), renamed old Stage 2 -> Stage 2.5

**Why:**
User drafted a comprehensive self.md revealing design gaps between intent and implementation. 10 design questions were resolved to align the codebase with the intended architecture. Me's 5 memory types, sleep mode, and Re priority are documented but deferred to later stages.
```

---

### Task 7: Update tests

**Files:** `admin/utests/`

1. **N path tests** (in `test_families.py` or new file):
   - `CognitionPath.N` exists in enum
   - `validate_route()` returns True for any (sender, receiver) pair on N path
   - Message with N path ID passes `MESSAGE_ID_PATTERN` validation

2. **SET_STATE tests**:
   - `PermissionAction.SET_STATE` exists
   - Ev has SET_STATE on `"*"` by default
   - Re does NOT have SET_STATE on other families
   - `request_state_change()` succeeds when called by Ev
   - `request_state_change()` raises PermissionError when called by Re on Pr

3. **Array output format tests** (in `test_message_codec.py` or similar):
   - `parse_llm_outputs()` with array format returns list of ParsedLLMOutput
   - `parse_llm_outputs()` with old single-object format returns list of length 1
   - `parse_llm_outputs()` with invalid JSON returns list of length 1 with parse_error
   - Multiple messages in array each have correct path/receiver/body

---

## Key Files Reference

| File | Current State | Purpose |
|------|--------------|---------|
| `self.md` | 20 lines, basic | Agent's runtime self-model, loaded into every LLM call |
| `interface/bus.py` | 325 lines | MessageBus, CognitionPath (P/R/E/U/D/S), QueueFullPolicy, BusMessage |
| `interface/modules.py` | 796 lines | BaseModule, MainModule (message loop, state, submodule registry), SubModule (capabilities, policy) |
| `interface/permissions.py` | 158 lines | PermissionAction enum, PermissionManager with grant/revoke/check |
| `interface/message_codec.py` | 181 lines | FORMAT_INSTRUCTIONS, parse_llm_output(), ParsedLLMOutput, fallback routes |
| `interface/prompt_assembler.py` | 163 lines | 5-part prompt: identity + self-model + rulebook + character + output-format |
| `reaction/re_main_module.py` | | ReactionModule.perceive(), classify_input(), _handle_message() |
| `prediction/pr_main_module.py` | | PredictionModule.reason(), dispatch(), _handle_message() |
| `evaluation/ev_main_module.py` | | EvaluationModule.evaluate(), generate_affordances(), _handle_message() |
| `memorization/me_main_module.py` | 147 lines | MemorizationModule.store/search/recall(), flat dict store |
| `motion/mo_main_module.py` | | MotionModule.speak(), do(), get_output(), _handle_message() |
| `TODO.md` | 206 lines | Stage 0 (done), Stage 1 (mostly done), Stage 2/3, Known Issues, Diary |

## Verification

1. `python3 -m pytest admin/utests/ -v` — all tests pass
2. `CognitionPath.N` message sends without warning
3. Ev can set another family's state via `_set_state` bus message
4. Single-object LLM output still parses (backward compat)
5. Array LLM output parses into multiple `ParsedLLMOutput` items
6. PromptAssembler includes all family sections
7. self.md matches design decisions
