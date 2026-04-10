# Implementation Diary — self.md Rewrite + Design Decisions

## 2026-04-10

### Step 1: Read and understand the plan

Read `self_md_rewrite_plan.md` which documented 10 resolved design decisions and 7 implementation tasks. Read the current `self.md` (Chinese draft) and all files that needed modification: `interface/bus.py`, `interface/permissions.py`, `interface/modules.py`, `interface/message_codec.py`, `interface/prompt_assembler.py`, all 5 family main modules, `TODO.md`, and existing test files.

### Step 2: Rewrite self.md in English (Task 1)

Translated the Chinese draft into English while restructuring for clarity. The new `self.md` covers:
- Who the agent is (EPH Theory, Joseph Chen, five families forming one mind)
- System overview (five families, their LLMs, sections, rulebooks)
- Data structures (self.md, rulebooks, memory database, character.md, family folders)
- Tools (submodules, shared capabilities)
- Notation (`[[]]` for Me's dictionary, `<>` for assembled prompts)
- System design: paths table (P/R/E/U/D/S/N with examples), message bus, broadcasts, submodules, multiple outputs, permissions, ACK protocol, output format, queue backpressure, idle/S-path
- Per-family sections: Pr (central cognition), Re (sensory input), Ev (evaluation + affordances), Me (5 memory types), Mo (motor output)

### Step 3: Add CognitionPath.N (Task 2)

Modified `interface/bus.py`:
- Added `N = "N"` to `CognitionPath` enum with comment "Unrestricted: any sender -> any receiver"
- Added all 25 (sender, receiver) pairs to `VALID_PATH_ROUTES[CognitionPath.N]` via list comprehension
- Updated `MESSAGE_ID_PATTERN` regex to accept `N` as a valid path letter: `[PREUDSN]`

### Step 4: Add PermissionAction.SET_STATE + Ev authority (Task 3)

Modified `interface/permissions.py`:
- Added `SET_STATE = "SET_STATE"` to `PermissionAction` enum
- In `_init_defaults()`, added a grant giving `Ev` SET_STATE on `"*"` (all families), granted by Pr

Modified `interface/modules.py`:
- Added `request_state_change()` method to `MainModule` — permission-checked via `PermissionAction.SET_STATE`
- Added `_set_state` message interception in `_message_loop()`, after the existing `_sub_register` interception block. When a message body contains `{"_set_state": true, "new_state": "..."}`, it calls `request_state_change()` with the sender as requester.

### Step 5: Change LLM output format to array (Task 4)

Modified `interface/message_codec.py`:
- Updated `FORMAT_INSTRUCTIONS` to describe the new array format: `{"messages": [{body, path, receiver, summary}, ...]}`
- Added path options "S" and "N" to the format instructions
- Extracted JSON parsing into `_extract_json()` helper
- Extracted single-message parsing into `_parse_single_message()` helper
- Added new `parse_llm_outputs()` function returning `list[ParsedLLMOutput]`:
  - Handles `{"messages": [...]}` array format
  - Handles `{"body": ...}` legacy single-object format (backward compat)
  - Falls back to single parse-error entry on JSON failure
- Kept `parse_llm_output()` as backward-compat convenience (returns first item)

Modified `prediction/pr_main_module.py`:
- Imported `parse_llm_outputs`
- Changed `_handle_message()` to call `parse_llm_outputs()` and loop over all results, sending one bus message per parsed output
- Updated `_REASON_PROMPT` to mention N path and multiple-output capability

Modified `reaction/re_main_module.py`:
- Imported `parse_llm_outputs`
- Updated `_CLASSIFY_PROMPT` to mention N path

Modified `evaluation/ev_main_module.py`:
- Imported `parse_llm_outputs` (available for future use)

### Step 6: Update PromptAssembler to load full self.md (Task 5)

Modified `interface/prompt_assembler.py`:
- Changed `_load_self_model()` from loading only `_preamble`, `Agent`, and own-family section to iterating over all sections. This implements cross-visibility (design decision #10): all family sections are now visible to all families.

### Step 7: Update TODO.md (Task 6)

- Inserted new "Stage 2: Me Memory Architecture" section with 7 items covering the 5 memory types, dictionary zone, eternal memory, context log, promotion mechanism, `[[]]` notation, and sleep mode
- Renamed old "Stage 2: Learning & Self-Improvement" to "Stage 2.5"
- Added "Re message priority on bus" to Stage 3
- Added diary entry for 2026-04-10

### Step 8: Update tests (Task 7)

Modified `admin/utests/test_bus.py`:
- Updated `TestCognitionPath.test_values` to include `CognitionPath.S` and `CognitionPath.N`
- Added `Pr00000001S`, `Re00000001N`, and `pr00000001N` to valid message ID parametrize list

Modified `admin/utests/test_permissions.py`:
- Added `"SET_STATE"` to expected values in `TestPermissionAction.test_expected_values`

Modified `admin/utests/test_families.py`:
- Added imports for `VALID_PATH_ROUTES` and `PermissionAction`
- Added `TestNPath` class (4 tests): enum membership, all 25 pairs valid, message ID format, route table has 25 entries
- Added `TestSetState` class (6 tests): action exists, Ev has wildcard SET_STATE, Ev has per-family SET_STATE, Re lacks SET_STATE, request_state_change succeeds for Ev, request_state_change denied for Re
- Added `TestArrayOutputFormat` class (4 tests): array format parsing, single-object backward compat, invalid JSON fallback, multi-message correctness

### Step 9: Run tests and verify

Ran `python3 -m pytest admin/utests/ -v`:
- **190 passed**, 37 failed
- All 37 failures are **pre-existing** (ConcreteMainModule missing `_handle_message`, LLMConfig `system_prompt_path` removed, SelfModel `_parse_sections` moved, queue maxsize mismatch)
- All 14 new tests pass
- Zero regressions introduced

### Summary of files changed

| File | Change |
|------|--------|
| `self.md` | Full rewrite: Chinese → English, awareness-focused, all design decisions |
| `interface/bus.py` | CognitionPath.N, VALID_PATH_ROUTES.N, MESSAGE_ID_PATTERN updated |
| `interface/permissions.py` | PermissionAction.SET_STATE, Ev authority grant |
| `interface/modules.py` | `request_state_change()`, `_set_state` bus interception |
| `interface/message_codec.py` | Array FORMAT_INSTRUCTIONS, `parse_llm_outputs()`, refactored helpers |
| `interface/prompt_assembler.py` | `_load_self_model()` loads all sections |
| `reaction/re_main_module.py` | Import + N path in classify prompt |
| `prediction/pr_main_module.py` | Import + multi-output `_handle_message` + N path in reason prompt |
| `evaluation/ev_main_module.py` | Import `parse_llm_outputs` |
| `TODO.md` | New Stage 2, Stage 2→2.5 rename, Re priority in Stage 3, diary entry |
| `admin/utests/test_bus.py` | CognitionPath enum update, N path message IDs |
| `admin/utests/test_permissions.py` | SET_STATE in expected values |
| `admin/utests/test_families.py` | 14 new tests (N path, SET_STATE, array output) |
