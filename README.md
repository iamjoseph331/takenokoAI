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

Submodules attach to families at runtime — e.g. `Re.browser` for DOM perception, `Mo.audio` for speech — and communicate with their parent family exclusively through the bus.

## Quick Start

```bash
pip install -e ".[dev,debug]"

# Full run: chat loop + visualization (http://localhost:7899) + debug API (http://localhost:7901)
python admin/run_agent.py

# Chat loop only (no servers)
python admin/run_agent.py --no-viz --no-debug

# Custom config or ports
python admin/run_agent.py --config admin/yamls/default.yaml --viz-port 7899 --debug-port 7901

# Run tests
pytest admin/utests/
```

Type a message and press Enter to chat. Type `exit` or press Ctrl-D to quit.

## Project Structure

```
main.py                    # TakenokoAgent orchestrator + SelfModel
interface/
  bus.py                   # MessageBus, FamilyPrefix, QueueFullPolicy, cognition paths
  modules.py               # BaseModule, MainModule, SubModule
  capabilities.py          # Capability dataclass (submodule self-registration)
  llm.py                   # LLM abstraction (litellm)
  permissions.py           # Permission management
  prompt_assembler.py      # 4-part system prompt builder
  character_model.py       # Personality definitions
  logging.py               # Structured logging
  markdown_utils.py        # Markdown section parser
  audio.py                 # STT/TTS backend abstractions
  browser_session.py       # Playwright browser session wrapper
reaction/                  # Re family
prediction/                # Pr family
evaluation/                # Ev family
memorization/              # Me family
motion/                    # Mo family
submodules/
  Re/
    re_browser.py          # DOM observation (observe, screenshot)
    re_audio.py            # Speech-to-text (transcribe)
  Mo/
    mo_browser.py          # Browser actions (click, type, navigate, js, ...)
    mo_audio.py            # Text-to-speech (synthesize)
  Me/
    me_rules.py            # Rule memory (add_rule, get_rules, query_rules)
admin/
  run_agent.py             # CLI runner with chat loop, viz, and debug API
  debug_api.py             # REST debug API (FastAPI) — http://localhost:7901
  visualization_app.py     # WebSocket visualization — http://localhost:7899
  yamls/default.yaml       # Configuration
  utests/                  # Unit tests
prompts/identity/          # Per-family identity prompts
self.md                    # Agent's runtime self-model
character.md               # Personality definitions
```

## Configuration

Edit `admin/yamls/default.yaml` to configure per-family models, temperatures, and token limits:

```yaml
families:
  Pr:
    model: ollama/gemma4   # or gpt-4o, claude-opus-4-6, etc.
    temperature: 0.5
    max_tokens: 8192
```

Enable submodules under the `submodules:` section (all disabled by default):

```yaml
submodules:
  Re:
    browser:
      enabled: true
      policy: WAIT          # WAIT | RETRY | DROP — queue-full behaviour
  Mo:
    audio:
      enabled: true
      policy: DROP
      tts: {}
```

Set API keys via environment variables:

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
