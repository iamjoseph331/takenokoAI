# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Vision

TakenokoAI models intelligence as three core abilities: **spontaneous prediction**, **reactive prediction**, and the **ability to gain from prediction**. The project expresses this through a modular agent where Reaction, Prediction, and Evaluation are first-class citizens — each independently configurable with different backbone models and prompts. The ultimate goal is to discover which model + prompt combination works best for each cognitive role.

**Stage 1 target:** play Tic-Tac-Toe, Poker, and Uno without changing the agent's structure.

The system structure is still in planning stage. See `/notes` for raw design notes.

## The Five Families

Each family has a main module and dynamically attachable sub-modules. Sub-modules can be added or dropped at runtime, giving the agent flexible abilities.

| Family | Prefix | Role | Planned sub-modules |
|--------|--------|------|---------------------|
| **Reaction** `reaction/` | `Re` | Sensory input — perceives the environment | Vision, Audio, Net-Search, Extra |
| **Prediction** `prediction/` | `Pr` | Central intelligence — plans and reasons | Plan |
| **Evaluation** `evaluation/` | `Ev` | Judges outcomes and generates affordances | Evaluate Self/Environment/Goal, Weights update, Generate afforded actions |
| **Memorization** `memorization/` | `Me` | Stores and retrieves information | Short-term, Long-term, Logs |
| **Motion** `motion/` | `Mo` | Executes output actions | Speak, Do |

`<Pr>` holds default authority to write to any part of the project. All other families must request permission from `<Pr>` to access resources or capabilities outside their own scope.

### Family file structure

```
<family>/
  <prefix>_main_module.py   # entry point, owns the family
  <prefix>_rulebook.md      # intramodule communication rules
  <prefix>_character.md     # personality / character definition
  README.md
```

## Communication

There are two distinct layers of information flow:

- **Intermodule** (between families) — governed by `self.md` at the project root. All messages pass through the bus defined in `interface/bus.py`.
- **Intramodule** (within a family) — governed by each family's `rulebook.md`.

### Bus message format

Every intermodule message carries these fields:

1. **messageID** — `<2-letter family prefix><8-digit counter><path letter>` (e.g. `Pr00000012P`)
2. **parentMessageID** — the message that triggered this one
3. **timecode** — system-maintained, for resource management
4. **context**
5. **body**
6. **sender**
7. **receiver**
8. **resources**

### Cognition paths

Messages flow along named paths that represent common cognitive patterns:

| Path | Flow | Purpose |
|------|------|---------|
| **P** | `Ev → Pr → Ev → Mo` or `Me` | Deliberate thought — evaluate, plan, evaluate, act |
| **R** | `Re → Mo` | Reflex — react immediately |
| **E** | `Re → Ev` | Appraisal — evaluate an input |
| **U** | `Re → Pr` | Uptake — feed input to planning |
| **D** | `Pr → Re` or `Ev` or `Mo` or `Me` | Dispatch — prediction drives any family |

## self.md — The Agent's Self-Model

`self.md` is a living document the agent reads and writes at runtime. It is divided into sections: one for the whole agent and one per family.

Three functions manage it:
- **`load_all()`** — read the entire self-model
- **`load_part(section)`** — read one section
- **`write_part(section, content)`** — update a section (requires permission check via `interface/permissions.py`)

Each family can edit its own section. `<Pr>`, as the central intelligence, has default permission to write any section.

### 申告制 (Self-Registration Protocol)

When a sub-module is added, it must follow a protocol: announce to its main module what it does and how to use it. The main module then updates its family's section in `self.md` and broadcasts the new capability to all families.

## Module Lifecycle

### States

Each family and the agent system itself maintain states. Initially: **`idle`** and **`thinking`**. Main modules can define new states at runtime (and must broadcast changes to other families). State is derived from workload (queued tasks vs. available resources).

### Async API surface

Each main module exposes these async functions to other modules (all behind permission management):

1. Get current resource levels of the family
2. Get task queue info (length, max length, resource required, estimated time)
3. Change prompt / restart module / change model
4. Get family limits (max context tokens, etc.)
5. Family-specific functions (e.g. `speak()` in `<Mo>`, `search()` in `<Me>`)
6. Signal to pause work and answer questions

## Resource Tracking

Three resource types: **token count**, **thinking time**, and **RAM**. Tracking and limits are deferred to Stage 3.

## Supporting Infrastructure

| Path | Purpose |
|------|---------|
| `interface/bus.py` | Intermodule message bus |
| `interface/modules.py` | Module registry |
| `interface/logging.py` | Logging (log everything — every thought, message, and action) |
| `interface/permissions.py` | Permission management for `self.md` writes and cross-family access |
| `prompts/<family>/<prefix>_default.md` | Default LLM prompt templates per family |
| `admin/visualization_app.py` | Agent visualization tool |
| `admin/yamls/default.yaml` | Configuration |
| `admin/utests/` | Unit tests |
| `admin/debug/` | Debug utilities |
| `admin/data/` | Data storage |
| `main.py` | Top-level entry point |

## Conventions

- File prefixes (`re_`, `pr_`, `ev_`, `me_`, `mo_`) indicate family ownership
- Log everything — what each module is doing and when, every thought, every message
- Each module can access everything within its own folder freely
- Maintain `lessons.md` (`.claude/lessons.md`) for development learnings
- **Revise `TODO.md` every time a task is finished** — mark completed items `[x]`, add new items discovered during implementation, keep the list accurate and current
