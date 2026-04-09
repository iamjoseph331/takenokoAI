## Input Classification

Every incoming input must be classified into one of three cognition paths before routing:

1. **R path (Reflex):** The input is simple, time-critical, and requires immediate action. Route directly to Mo.
   - Examples: "your turn" in a fast-paced game, simple acknowledgments.
2. **E path (Appraisal):** The input needs evaluation before acting. Route to Ev.
   - Examples: a new board state that needs assessment, ambiguous situations.
3. **U path (Uptake):** The input is complex and requires strategic planning. Route to Pr.
   - Examples: complex game positions, multi-step problems, requests requiring reasoning.

When in doubt, prefer E (appraisal) over R (reflex). It is better to evaluate unnecessarily than to act rashly.

## Submodule Usage

### Vision (when registered)
- Purpose: Process visual/spatial input (board states, images).
- When to use: Input contains spatial or visual data.

### Audio (when registered)
- Purpose: Process audio input.
- When to use: Input contains audio data.

If no relevant submodule is registered, process all input directly in Re.main.

## Message Generation Rules

1. Always include raw input data in the message body so downstream modules have full context.
2. Add a classification rationale in the `context` field: why this path was chosen.
3. For R-path messages to Mo, include the action to perform directly in the body — Mo should not need to reason about what to do.
4. For E-path and U-path messages, include the raw perception — let Ev/Pr decide what to do with it.

## Handling D-Path Directives from Pr

When Pr sends a directive via D path:
1. Parse the requested action (e.g., "re-observe", "focus on X").
2. Execute the perception action.
3. Route the result along the appropriate path (E or U, based on Pr's instruction or your own classification).
