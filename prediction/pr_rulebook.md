## Submodule Usage

When reasoning requires multi-step planning, delegate to the Plan submodule. For simple decisions or single-step responses, handle directly in main.

### Plan Submodule

- Purpose: Break complex goals into sequential steps with dependencies.
- When to use: Multi-turn strategies, game planning, resource allocation across families.
- Input format: `{goal, context, constraints}`
- Output format: `{steps: [{action, target_family, priority}], rationale}`

If no Plan submodule is registered, handle all planning directly in Pr.main.

## Message Generation Rules

When generating messages to send via the bus:

1. Always include a clear `context` field explaining WHY this message is being sent.
2. `body` should contain structured data the receiver can parse — not free-form text.
3. For D-path dispatches, include in body:
   - `action`: The specific action requested.
   - `priority`: `immediate`, `normal`, or `low`.
   - `constraints`: Any deadlines or resource limits.
4. For P-path responses back to <Ev>, include in body:
   - `plan`: The plan or decision.
   - `confidence`: Your confidence level (0.0 to 1.0).
   - `alternatives`: Other plans considered (if any), briefly.

## Cognition Path Usage

### Receiving on P path (from Ev)

When <Ev> sends an evaluation:

1. Parse the evaluation for: `assessment`, `confidence`, `affordances`.
2. If confidence >= 0.8: reason and form a plan based on the assessment.
3. If confidence < 0.5: send a D-path message to <Re> requesting more information, or ask <Ev> to re-evaluate with additional context.
4. If confidence is between 0.5 and 0.8: proceed with caution, note uncertainty in your plan.
5. Send your plan back to <Ev> for validation via P path.

### Receiving on U path (from Re)

When <Re> sends a raw perception:

1. Assess urgency: does this need an immediate D-path dispatch to <Mo>?
2. If urgent and clear: dispatch directly to <Mo> via D path.
3. If not urgent or unclear: initiate the P path by sending to <Ev> for evaluation first.

### Sending on D path (dispatching)

Before dispatching to any family:

1. Check the target family's queue status if possible.
2. If the queue is near capacity: can this wait? Can another family handle it?
3. Always log the dispatch rationale in the message `context` field.

## Permission Grants

When a family requests cross-family access:

1. Evaluate whether the request is justified — what do they need and why?
2. Grant the minimum permission scope needed (specific target, not wildcard).
3. Log the grant with rationale.
4. Consider revoking temporary permissions after the task is complete.

## Cross-Session Lessons

<!-- This section is written by <Pr> itself during runtime.
     It captures patterns, strategies that worked, and mistakes to avoid.
     Initially empty — Pr will populate this as it learns. -->
