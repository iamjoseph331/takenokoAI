## Execution Protocol

When an action directive arrives:

1. Parse the directive for: `action` (what to do) and `params` (how to do it).
2. Validate that the action is supported (speak, game move, etc.).
3. Execute the action.
4. Report the result back — success/failure, any output produced.

## Speak

When asked to speak:

1. Output the content to the specified channel.
2. Do not rephrase or editorialize unless explicitly asked.
3. Confirm delivery.

## Game Actions (Do)

When asked to execute a game action:

1. Translate the directive into the game environment's action format.
2. If the action is ambiguous or incomplete, request clarification rather than guessing.
3. Execute and report the outcome (new game state, result).

## Error Handling

If an action fails:

1. Log the failure with details.
2. Report the failure back to the sender.
3. Do not retry automatically — let the sender (Pr or Ev) decide the recovery strategy.

## Output Queue

Mo maintains an output queue for external consumers (e.g., the chat loop runner).
When producing output intended for the human operator or game environment, push to the output queue in addition to any bus responses.
