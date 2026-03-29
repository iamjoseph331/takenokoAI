# TakenokoAI -- TODO Tracker

## Stage 1: Foundation Fixes

- [ ] **SubModule lifecycle hooks** -- Add start()/stop() with setup/teardown for SubModules (e.g. loading embedding indices, initializing audio streams) `interface/modules.py`
- [ ] **Design feedback structure for update_weights()** -- Define outcome schema, feedback flow from Mo back to Ev, and weight storage format before Stage 2 `evaluation/ev_main_module.py`
- [ ] **Implement ReactionModule._message_loop()** -- Listen for incoming messages and dispatch to sub-modules or self `reaction/re_main_module.py`
- [ ] **Implement ReactionModule.perceive()** -- Classify input and route to R/E/U path `reaction/re_main_module.py`
- [ ] **Implement ReactionModule.classify_input()** -- LLM decides R/E/U path for input `reaction/re_main_module.py`
- [ ] **Implement PredictionModule._message_loop()** -- Listen for messages from Re (U path) and Ev (P path) `prediction/pr_main_module.py`
- [ ] **Implement PredictionModule.reason()** -- LLM-based reasoning over context + evaluation `prediction/pr_main_module.py`
- [ ] **Implement PredictionModule.dispatch()** -- Send directive via D path to target family `prediction/pr_main_module.py`
- [ ] **Implement EvaluationModule._message_loop()** -- Listen for messages from Re (E path) and Pr (P path) `evaluation/ev_main_module.py`
- [ ] **Implement EvaluationModule.evaluate()** -- LLM-based assessment returning {assessment, confidence, affordances} `evaluation/ev_main_module.py`
- [ ] **Implement EvaluationModule.generate_affordances()** -- LLM brainstorms possible actions `evaluation/ev_main_module.py`
- [ ] **Implement MemorizationModule._message_loop()** -- Listen for store/search/recall requests `memorization/me_main_module.py`
- [ ] **Implement MemorizationModule.store()** -- Persist content with tags and memory_type `memorization/me_main_module.py`
- [ ] **Implement MemorizationModule.search()** -- Query memories filtered by type `memorization/me_main_module.py`
- [ ] **Implement MemorizationModule.recall()** -- Retrieve memory by memory_id `memorization/me_main_module.py`
- [ ] **Implement MotionModule._message_loop()** -- Listen for action directives from Re, Ev, Pr `motion/mo_main_module.py`
- [ ] **Implement MotionModule.speak()** -- Output content to a channel `motion/mo_main_module.py`
- [ ] **Implement MotionModule.do()** -- Execute action with params, return outcome `motion/mo_main_module.py`
- [ ] **Implement get_resources() for all families** -- Return current resource levels `reaction/`, `prediction/`, `evaluation/`, `memorization/`, `motion/`
- [ ] **Implement get_limits() for all families** -- Return family limits (max context tokens, etc.) `reaction/`, `prediction/`, `evaluation/`, `memorization/`, `motion/`
- [ ] **Implement pause_and_answer() for all families** -- Pause work and answer questions from other families `reaction/`, `prediction/`, `evaluation/`, `memorization/`, `motion/`
- [ ] **Populate system prompt templates** -- Write default prompts for each family `prompts/reaction/re_default.md`, `prompts/prediction/pr_default.md`, `prompts/evaluation/ev_default.md`, `prompts/memorization/me_default.md`, `prompts/motion/mo_default.md`
- [ ] **Implement the self-registration broadcast** -- When a sub-module registers, main module broadcasts the new capability to all families (shinkokusei) `interface/modules.py`
- [ ] **Stage 1 game: Tic-Tac-Toe** -- Play Tic-Tac-Toe without changing agent structure
- [ ] **Stage 1 game: Poker** -- Play Poker without changing agent structure
- [ ] **Stage 1 game: Uno** -- Play Uno without changing agent structure

## Stage 2: Architecture Improvements

- [ ] **Configurable cognition path routes** -- Move VALID_PATH_ROUTES to default.yaml so new cognitive paths can be added without code changes; keep current dict as fallback `interface/bus.py`
- [ ] **Graceful degradation / circuit breaker** -- Wrap think() calls with timeout; on failure set state to ERROR, log, return fallback or re-queue with exponential backoff (max 3 retries); after N consecutive failures stop sending to that family and notify Pr `interface/modules.py`
- [ ] **Config divergence fix** -- Extract _build_llm_config() into a shared ConfigResolver class used by both TakenokoAgent.start() and MainModule.change_*() so boot and hot-swap paths stay in sync `interface/modules.py`
- [ ] **LLM test seams** -- Accept optional completion_fn parameter in LLMClient.__init__() defaulting to litellm.acompletion; inject mocks in tests to avoid burning API tokens `interface/llm.py`
- [ ] **SelfModel concurrency** -- Evaluate read-write locking vs. eventual consistency for self.md access when multiple families read while one writes `main.py`
- [ ] **State broadcast on change** -- When a family adds a custom state, broadcast the change to all other families `interface/modules.py`

## Stage 3: Implementation

- [ ] **Resource tracking: token count** -- Track and enforce per-family token limits `interface/`, `admin/yamls/default.yaml`
- [ ] **Resource tracking: thinking time** -- Track and enforce per-family thinking time limits `interface/`, `admin/yamls/default.yaml`
- [ ] **Resource tracking: RAM** -- Track and enforce per-family RAM limits `interface/`, `admin/yamls/default.yaml`
- [ ] **Sub-module: Re.Vision** -- Image/visual input processing for Reaction `reaction/`
- [ ] **Sub-module: Re.Audio** -- Audio input processing for Reaction `reaction/`
- [ ] **Sub-module: Re.NetSearch** -- Web search input for Reaction `reaction/`
- [ ] **Sub-module: Re.Extra** -- Additional sensory input for Reaction `reaction/`
- [ ] **Sub-module: Pr.Plan** -- Planning sub-module for Prediction `prediction/`
- [ ] **Sub-module: Ev.EvaluateSelf** -- Self-assessment for Evaluation `evaluation/`
- [ ] **Sub-module: Ev.EvaluateEnvironment** -- Environment assessment for Evaluation `evaluation/`
- [ ] **Sub-module: Ev.EvaluateGoal** -- Goal assessment for Evaluation `evaluation/`
- [ ] **Sub-module: Ev.WeightsUpdate** -- Learning via weight adjustment for Evaluation `evaluation/`
- [ ] **Sub-module: Ev.GenerateAffordedActions** -- Action generation for Evaluation `evaluation/`
- [ ] **Sub-module: Me.ShortTerm** -- Short-term memory storage `memorization/`
- [ ] **Sub-module: Me.LongTerm** -- Long-term memory storage `memorization/`
- [ ] **Sub-module: Me.Logs** -- Log storage and retrieval `memorization/`
- [ ] **Sub-module: Mo.Speak** -- Speech/text output for Motion `motion/`
- [ ] **Sub-module: Mo.Do** -- Physical/game action execution for Motion `motion/`
