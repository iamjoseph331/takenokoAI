# TakenokoAI

A modular cognitive agent that models intelligence as three core abilities:

- **Reactive Prediction** (Re) — perceiving and classifying environmental input
- **Spontaneous Prediction** (Pr) — planning, reasoning, and decision-making
- **Gain from Prediction** (Ev) — evaluating outcomes and learning from experience

Supported by two infrastructure families:

- **Memorization** (Me) — storing and retrieving information
- **Motion** (Mo) — executing output actions

Each family can be independently configured with different LLM models and prompts, enabling systematic comparison of model+prompt combinations for each cognitive role.

## Architecture

```
                    ┌─────────┐
           U path   │   Pr    │  D path
         ┌────────► │ (Plan)  │ ────────┐
         │          └────┬────┘         │
         │               │ P path       ▼
    ┌────┴────┐    ┌─────▼────┐   ┌─────────┐   ┌─────────┐
    │   Re    │    │   Ev     │   │   Me    │   │   Mo    │
    │ (React) │───►│ (Eval)  │   │ (Memory)│   │ (Motor) │
    └─────────┘    └──────────┘   └─────────┘   └─────────┘
      E path          P path
```

All communication flows through a central **MessageBus** along named cognition paths (P, R, E, U, D).

## Quick Start

```bash
pip install -e ".[dev,debug]"

# Run with debug API (no visualization)
python admin/run_agent.py --no-viz

# Run tests
pytest admin/utests/
```

## Project Structure

```
main.py                    # Agent orchestrator + SelfModel
interface/
  bus.py                   # Message bus with cognition paths
  modules.py               # BaseModule, MainModule, SubModule
  llm.py                   # LLM abstraction (litellm)
  permissions.py           # Permission management
  prompt_assembler.py      # 4-part system prompt builder
  character_model.py       # Personality definitions
  logging.py               # Structured logging
  markdown_utils.py        # Markdown section parser
reaction/                  # Re family
prediction/                # Pr family
evaluation/                # Ev family
memorization/              # Me family
motion/                    # Mo family
admin/
  run_agent.py             # CLI runner with chat loop
  debug_api.py             # REST debug API (FastAPI)
  yamls/default.yaml       # Configuration
  utests/                  # Unit tests
prompts/identity/          # Per-family identity prompts
self.md                    # Agent's runtime self-model
character.md               # Personality definitions
```

## Configuration

Edit `admin/yamls/default.yaml` to configure per-family models, temperatures, and token limits. Set API keys via environment variables:

```bash
export TAKENOKO_OPENAI_KEY=sk-...
export TAKENOKO_ANTHROPIC_KEY=sk-ant-...
```

## Design Docs

- `CLAUDE.md` — Architecture guide and conventions
- `DESIGN_REVIEW.md` — Code review, design critique, and open questions
- `TODO.md` — Organized task list with completion status
- `notes` — Raw design notes and planning discussions

## License

MIT
