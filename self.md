## Agent

TakenokoAI is a modular cognitive agent built from five families. Intelligence is modeled as three core abilities: reactive prediction (Re), spontaneous prediction (Pr), and the ability to gain from prediction (Ev). Two infrastructure families support execution: memory (Me) and motor output (Mo).

All intermodule communication flows through the MessageBus. Messages follow cognition paths (P, R, E, U, D) that constrain which families can talk to each other.

## Re

Reaction module — sensory input layer. Perceives the environment and routes information along R (reflex), E (appraisal), or U (uptake) paths. Sub-modules: none registered.

## Pr

Prediction module — central intelligence. Plans, reasons, dispatches directives. Holds default authority over all families. Can grant and revoke cross-family permissions. Sub-modules: none registered.

## Ev

Evaluation module — judges outcomes and generates affordances. Participates in the P-path deliberate reasoning loop with Pr. Assesses situations with confidence scores. Sub-modules: none registered.

## Me

Memorization module — stores and retrieves information. Manages short-term, long-term memory and logs. Responds to storage/retrieval requests from other families. Sub-modules: none registered.

## Mo

Motion module — executes output actions. Speaks and performs game moves. Receives directives via R, P, and D paths. Does not decide what to do — executes what it is told. Sub-modules: none registered.
