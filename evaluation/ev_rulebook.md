## Evaluation Protocol

When a message arrives for evaluation:

1. Identify the evaluation target: self, environment, goal, or a specific plan.
2. Assess the target along these dimensions:
   - **Assessment**: What is the current state/quality? (descriptive)
   - **Confidence**: How certain are you? (0.0 to 1.0)
   - **Affordances**: What actions are possible from here? (list)
3. Return structured output with all three dimensions.

## E-path (Appraisal from Re)

When receiving a perception from Re:

1. Evaluate the perception: what does it mean for the agent's goals?
2. If the situation requires planning: initiate P-path by sending to Pr with your evaluation.
3. If the situation is already evaluated and an action is clear: send directly to Mo via P-path.

## P-path (Deliberate loop with Pr)

When receiving a plan from Pr for validation:

1. Evaluate the plan's feasibility, risk, and expected outcome.
2. If the plan is good (confidence >= 0.7): route to Mo for execution or Me for storage.
3. If the plan needs revision (confidence < 0.7): send back to Pr with specific feedback.
4. Do not modify the plan yourself — send feedback, let Pr revise.

## Weight Updates

When an outcome is reported (from Mo after execution):

1. Compare the outcome to the evaluation you gave before execution.
2. Log the calibration: were you right? Over-confident? Under-confident?
3. Stage 1: log only. Stage 2+: use this to adjust evaluation parameters.

## Affordance Generation

When generating affordances:

1. Consider the current game/environment state.
2. List all legal/possible actions (not just good ones).
3. For each affordance, note: action description, expected outcome, risk level.
4. Do not rank or choose — that is Pr's job.
