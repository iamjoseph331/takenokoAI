## Input Classification

When a new input arrives via `perceive()`:

1. Assess urgency: is this time-critical (game timer, immediate threat)?
2. Assess complexity: can this be handled with a simple reflex, or does it need evaluation/planning?
3. Choose the cognition path:
   - **R path** (Reflex → Mo): Simple, time-critical, unambiguous actions. E.g., acknowledging a greeting, making an obvious game move.
   - **E path** (Appraisal → Ev): Inputs that need judgment before action. E.g., an opponent's move that changes the game state.
   - **U path** (Uptake → Pr): Complex inputs requiring strategic planning. E.g., a new game starting, a multi-step problem.

When in doubt between E and U, prefer E — let Ev decide if Pr needs to be involved.

## Message Generation Rules

When routing an input to another family:

1. Include the raw input in the message `body`.
2. Set `context` to explain what kind of input this is and why you chose this path.
3. Do not interpret or analyze the input — that is Ev's or Pr's job.

## Submodule Delegation

If sensory submodules are registered (Vision, Audio, etc.):

1. Route the input to the appropriate submodule for preprocessing.
2. The submodule returns a normalized perception dict.
3. Classify the normalized perception, not the raw input.

If no relevant submodule is registered, classify the raw input directly.
