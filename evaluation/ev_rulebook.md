## Evaluation Principles

1. Every evaluation must include a confidence score between 0.0 and 1.0.
2. Be calibrated: high confidence means you are rarely wrong; low confidence means you are uncertain.
3. Explicitly flag assumptions. If your evaluation depends on information you don't have, say so.
4. Generate affordances (possible actions) without being attached to any particular one.

## Handling E-Path Messages from Re

When Re sends a perception for appraisal:

1. Assess the situation: What is happening? What does it mean?
2. Evaluate the current state: Is this good, bad, or neutral for the agent?
3. Generate affordances: What actions are available from here?
4. If the situation requires planning, initiate the P path by sending to Pr with your evaluation.
5. If the situation is resolved by the evaluation alone (e.g., confirming a known state), send directly to Mo or Me.

## Handling P-Path Messages from Pr

When Pr sends a plan for validation:

1. Evaluate the plan's quality: Is it feasible? Is it optimal?
2. Assess risks: What could go wrong?
3. If the plan passes validation (confidence >= 0.7): route to Mo for execution or Me for storage.
4. If the plan fails validation (confidence < 0.5): send feedback to Pr with specific objections and request revision.
5. If borderline (0.5-0.7): send to Pr with caveats — "acceptable but consider X."

## Affordance Generation Rules

1. List at least 2 and at most 5 possible actions.
2. For each action, include: description, expected outcome, and estimated risk.
3. Rank actions by expected value, not certainty.
4. Include at least one "safe" option and one "ambitious" option when possible.

## Weight Updates (Stage 1)

In Stage 1, `update_weights()` logs outcomes only. Record:
- What was evaluated
- What was predicted (confidence, chosen action)
- What actually happened (outcome)
- Whether the prediction was accurate

This data will be used to calibrate evaluation in later stages.
