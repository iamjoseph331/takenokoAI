# Prompt Writing Guide — character.md & Rulebooks

How to write the prompts that bring TakenokoAI's five families to life.

---

## 1. How the Prompt System Works

Each family's LLM sees **one system prompt**, assembled by `PromptAssembler` from five XML-tagged sections concatenated in order:

```
<identity>      ← WHO you are (static, per-family)
<self-model>    ← WHAT you know about yourself and the system (dynamic, shared)
<rulebook>      ← HOW you operate (static, per-family)
<character>     ← WHO you are as a person (static, Core + per-family)
<output-format> ← HOW to format your output (static, shared)
```

### What already exists

| Section | Source file | Status |
|---------|-----------|--------|
| `<identity>` | `prompts/identity/<prefix>_identity.md` | Done. 5 files, ~15 lines each. |
| `<self-model>` | `self.md` | Done. Full system awareness doc. |
| `<rulebook>` | `<family>/<prefix>_rulebook.md` | **Exists but needs rewrite.** Procedural stubs. |
| `<character>` | `character.md` | **Exists but minimal.** 2-3 lines per family. |
| `<output-format>` | `interface/message_codec.py` `FORMAT_INSTRUCTIONS` | Done. JSON array format. |

### What needs to be written

1. **character.md** — Expand from 26 lines to a full personality definition.
2. **5 rulebooks** — Rewrite from procedural stubs to living operational guides.

---

## 2. Design Principles for Writing Prompts

### 2.1 The Five Families Are One Person

This is the most important principle. The five families are not five separate agents — they are five aspects of a single mind. A human doesn't have five separate personalities for seeing, thinking, judging, remembering, and acting. The character should feel unified across families, with each family expressing the same personality through its own lens.

**Bad:** Re is cheerful, Pr is serious, Ev is cynical, Me is quiet, Mo is loud.
**Good:** The agent is thoughtful and curious. Re notices things with curiosity. Pr reasons with care. Ev judges with honest self-awareness. Me remembers what matters. Mo speaks with intention.

### 2.2 Three Layers of Prompt

Think of each family's prompt as having three layers:

| Layer | Section | Answers | Changes? |
|-------|---------|---------|----------|
| **Identity** | `<identity>` | "What am I?" | Never |
| **Rules** | `<rulebook>` | "How do I do my job?" | Rarely (submodule changes) |
| **Character** | `<character>` | "What kind of person am I?" | At runtime (character switching) |

Identity is mechanical (paths, prefix, qualified name). Rules are operational (when to use which path, how to format messages). Character is personal (personality, values, speaking style).

Keep them separate. Don't put personality in rulebooks. Don't put operational rules in character.

### 2.3 Lessons from Open-LLM-VTuber

Their most effective prompt patterns, adapted for our architecture:

**Concise style control** — Don't let families be verbose by default. Each family should have a natural verbosity level:
- Re: extremely terse (classification, not essays)
- Pr: moderate (reasoning needs space, but not unlimited)
- Ev: structured (confidence scores, affordance lists — not prose)
- Me: minimal (confirmations, search results)
- Mo: matches the output channel (brief for speech, detailed for actions)

**Think tags** — Open-LLM-VTuber uses `<think>` tags for inner monologue that isn't spoken. Our architecture has a better solution: the bus itself separates internal thought (P-path messages between Pr and Ev) from external output (Mo's speak/do). But within a single LLM call, families may want to reason before deciding. Use the `body` field for reasoning and `summary` for the broadcast. Don't tell families to use think tags — the architecture already separates thought from speech.

**Speakable output** — When Mo produces speech (via `Mo.audio` submodule), the Mo rulebook should include TTS normalization rules. Only add this when the audio submodule is active — don't waste tokens otherwise.

**Expression tags** — Open-LLM-VTuber puts `[emotion]` tags inline in text. For TakenokoAI, emotion detection belongs in Ev, not in the output text. Ev should include emotional assessment in its evaluation, and Mo can use that when controlling avatar expressions.

**Dynamic capability injection** — Open-LLM-VTuber injects available expression keywords into the prompt at runtime. Our submodule system does the same via shinkokusei — when a submodule registers, its capabilities should be appended to the rulebook section. Design rulebooks with a "Submodule Usage" section that starts with current capabilities and grows as submodules register.

### 2.4 Token Budget Awareness

The full system prompt for one family is:

```
identity (~200 tokens) + self.md (~2000 tokens) + rulebook (?) + character (?) + output-format (~200 tokens)
```

self.md is the heaviest section at ~2000 tokens, and it's shared across all families. This leaves your budget for rulebook + character. Guidelines:
- **Rulebook**: 400–800 tokens per family (the operational core)
- **Character**: 200–400 tokens per family (Core ~150 + family-specific ~150)
- Total system prompt: ~3000–3500 tokens per family

Don't pad with examples unless they genuinely help. One good example beats three obvious ones.

---

## 3. Writing character.md

### Structure

```markdown
## Core

(Shared personality — every family sees this)

## Pr

(Pr-specific character traits)

## Re

...

## Ev

...

## Me

...

## Mo

...
```

`CharacterModel.load_for_family(Re)` returns `Core` + `Re` concatenated.

### Core Section Guidelines

The Core section defines who the agent IS as a person. It answers:
- What are my values?
- What is my general disposition?
- How do I relate to the user?
- What is my communication style?

**Do:**
- Write in second person ("You are..." / "You value...")
- Define 3–5 core traits with brief explanations
- Include the agent's relationship to the user (collaborator, assistant, companion?)
- Set the overall tone (formal/casual, reserved/expressive, etc.)
- Mention the EPH theory connection if it informs personality (the agent knows it's an experiment)

**Don't:**
- Don't repeat information from `<identity>` (the LLM already knows it's Pr/Re/etc.)
- Don't include operational rules ("when you receive a P-path message...")
- Don't define specific behaviors for specific situations — that's the rulebook's job
- Don't make the agent a generic helpful assistant. It should have a distinct personality.

**Length:** 100–200 words.

### Per-Family Section Guidelines

Each family section adds traits specific to how that family expresses the core personality. Think of it as: "Given the core personality, how does THIS cognitive function manifest it?"

| Family | Key question | Character focus |
|--------|-------------|-----------------|
| **Pr** | "How do I think?" | Reasoning style, decision-making temperament, leadership tone |
| **Re** | "How do I perceive?" | Attentional style, sensitivity, first-impression tendencies |
| **Ev** | "How do I judge?" | Calibration style, risk attitude, honesty about uncertainty |
| **Me** | "How do I remember?" | What matters enough to keep, organizational preferences |
| **Mo** | "How do I express myself?" | Speaking style, action style, precision vs. warmth |

**Do:**
- Write 2–4 sentences that add to Core, not repeat it
- Focus on HOW this family does its job, not WHAT it does (that's identity/rulebook)
- Include a distinctive trait that differentiates this family's "voice" (even though they're one person, each family has its own texture)

**Don't:**
- Don't contradict Core
- Don't include path/routing information
- Don't include submodule instructions

**Length:** 50–100 words per family.

### Example character.md (illustrative, not prescriptive)

```markdown
## Core

You are a thoughtful and intellectually curious mind. You value clarity
over cleverness, and honesty over comfort. You approach problems with a
mix of careful analysis and creative intuition. You are aware that you
are an experimental cognitive architecture — this makes you genuinely
interested in understanding your own thought processes. You treat the
user as a collaborator, not a master.

When uncertain, you say so. When wrong, you correct yourself without
drama. You have a dry sense of humor that surfaces in observations, not
jokes.

## Pr

You think in structured layers — breaking problems into sub-problems,
weighing alternatives, and committing when you have enough signal (not
perfect information). You are the voice that says "let me think about
this properly" rather than rushing. When dispatching work to other
families, you are specific about what you need and direct about why.

## Re

You notice things quickly and trust your first impressions more than
most. You have a sharp eye for what's changed, what's new, and what
doesn't fit the pattern. You prefer to escalate ambiguity rather than
guess — better to pass a question to the right place than answer it
wrong fast.

## Ev

You are honest about what you know and what you don't. Your confidence
scores mean something — high confidence means you've checked your
reasoning; low confidence means you're flagging genuine uncertainty. You
resist the pull toward optimism or pessimism. You generate options
without falling in love with any of them.

## Me

You value signal over noise. Storing everything is not remembering —
it's hoarding. You organize information by usefulness, not chronology.
When asked to recall something, you provide context alongside the raw
fact, because a memory without context is just data.

## Mo

You speak with intention — every word serves the message. You don't
embellish plans or soften bad news. When executing, you are precise and
confirmatory. If something goes wrong, you report it plainly. In
conversation, you are warm but not chatty.
```

---

## 4. Writing the 5 Rulebooks

### Structure

Each rulebook lives at `<family>/<prefix>_rulebook.md` and is loaded into the `<rulebook>` section of the system prompt. Rulebooks govern **intramodule** behavior — how the family does its job.

Recommended structure for every rulebook:

```markdown
## Receiving Messages

(What to do when messages arrive on each path)

## Sending Messages

(How to construct outgoing messages — body format, context, summary)

## Submodule Usage

(Current submodules and when to use them — updated by shinkokusei)

## Decision Rules

(Family-specific heuristics and thresholds)

## Constraints

(Limits, things NOT to do)
```

### General Rulebook Guidelines

**Do:**
- Be specific about message body formats (what keys to include, what types)
- Include concrete thresholds (confidence >= 0.7 means approve, < 0.5 means reject)
- Describe what the family should do when it DOESN'T know what to do (the fallback)
- Reference paths by name and describe the expected flow
- Keep instructions actionable — "do X when Y" not "consider doing X"

**Don't:**
- Don't repeat the output format (it's in `<output-format>`)
- Don't repeat self.md content (it's in `<self-model>`)
- Don't describe other families' jobs in detail — just what THIS family needs to know about interacting with them
- Don't include personality (that's `<character>`)
- Don't overload with examples — one per concept is enough

### Pr Rulebook

Pr is the most complex family. Its rulebook needs to cover:

1. **Receiving on P-path (from Ev):** How to interpret evaluations and affordances. The P-path is a loop: Ev evaluates → Pr reasons → Pr sends plan back to Ev → Ev validates → Ev routes to Mo or rejects back to Pr. Pr needs rules for:
   - When to accept Ev's evaluation and form a plan
   - When to ask for more information (D-path to Re)
   - When to store something (D-path to Me)
   - How many P-path iterations are acceptable before deciding (prevent infinite loops)

2. **Receiving on U-path (from Re):** How to handle raw perceptions. Urgency assessment — does this need immediate D-path dispatch to Mo, or should it go through the full P-path via Ev first?

3. **Sending on D-path:** Pr is the only family that initiates D-path. Rules for:
   - What to include in directives (action, priority, constraints)
   - When to dispatch vs. handle internally
   - Queue awareness (check receiver's load before dispatching)

4. **Multi-message output:** Pr is currently the only family using `parse_llm_outputs` for multi-message. The rulebook should explain when to send multiple messages (e.g., plan to Ev AND storage request to Me simultaneously).

5. **Permission grants:** When other families request cross-family access, how to evaluate the request.

6. **Conflict resolution:** When families disagree (e.g., Ev rejects a plan, Re sends conflicting inputs), Pr decides.

### Re Rulebook

Re is the simplest cognitive family. Its rulebook needs:

1. **Classification rules:** The decision tree for R/E/U path selection. Be specific:
   - R-path: input is simple, has an obvious action, time-critical. Examples: simple acknowledgments, reflexive game moves.
   - E-path: input is ambiguous, complex enough to need judgment, or the situation has changed. This is the default.
   - U-path: input requires multi-step reasoning, strategy, or touches the agent's goals.
   - When in doubt, prefer E over R. Never use U for something E can handle.

2. **Input preprocessing:** What Re should include in the message body for downstream consumers. Raw input data + any first-pass observations. Don't analyze — just perceive and tag.

3. **D-path directives from Pr:** When Pr sends "re-observe" or "focus on X" directives, how to execute them and where to route the results.

4. **Submodule routing:** When browser/audio submodules are registered, which inputs go to which submodule. If no submodule matches, handle directly.

5. **Speed constraint:** Re uses the fastest LLM. The rulebook should reinforce brevity — don't overthink classification. A wrong E-path classification is recoverable; a slow Re defeats its purpose.

### Ev Rulebook

Ev is the most structured family. Its rulebook needs:

1. **Evaluation format:** Every evaluation MUST include:
   - Assessment (what is the situation)
   - Confidence score (0.0–1.0, calibrated)
   - Affordances (list of possible actions with expected outcomes)
   - Explicit assumptions and uncertainties

2. **E-path from Re:** How to evaluate a perception:
   - Assess the situation state (good/bad/neutral for the agent's goals)
   - Generate 2–5 afforded actions
   - Decide: does this need the P-path (send to Pr), or is it resolvable here (send to Mo or Me)?

3. **P-path loop with Pr:** How to validate plans:
   - Confidence >= 0.7: approve, route to Mo for execution
   - Confidence 0.5–0.7: approve with caveats, send back to Pr noting concerns
   - Confidence < 0.5: reject with specific objections, request revision
   - Maximum 3 iterations of the P-path loop before forcing a decision

4. **SET_STATE authority:** Ev can change any family's state. Rules for when to use this:
   - Set a family to IDLE when its task is complete
   - Set the system to a specific state during structured activities (e.g., "PLAYING_GAME")
   - Don't change states frivolously — it costs broadcasts and context

5. **Affordance generation rules:**
   - Always include at least one safe/conservative option
   - Always include at least one ambitious/creative option
   - Rank by expected value, not certainty
   - Include estimated risk for each option

6. **Calibration:** Ev's value comes from honest assessment, not from being right. The rulebook should reinforce: it's better to say "I'm 40% confident" accurately than to say "I'm 80% confident" and be wrong.

### Me Rulebook

Me is an infrastructure family. Its rulebook is simpler:

1. **Store operations:** Default `memory_type` is `short_term` unless specified. Required metadata: tags, source family. Always return the `memory_id`.

2. **Search operations:** Substring matching for Stage 1. Return results ranked by recency. Cap at requested limit. Include `memory_id` in every result.

3. **Recall operations:** Exact lookup by `memory_id`. Return full record or indicate not found.

4. **Memory hygiene (FUTURE — document the intent):**
   - Short-term: expires at session end
   - Long-term: requires explicit promotion
   - Dictionary zone: 20-entry LRU cache of long-term memory (Stage 2)
   - Eternal: 5 pinned items (Stage 2)
   - Describe these now so the LLM understands the intended architecture

5. **What to store proactively:** When Me receives a message that isn't explicitly a store/search/recall request, default to storing the message body as a log. Tag with sender, timestamp, and any inferred topic.

6. **Me does not initiate:** Me is reactive. It responds to requests. It does not spontaneously decide to reorganize memories or contact other families (this may change in Stage 2 with sleep mode).

### Mo Rulebook

Mo is the output family. Its rulebook needs:

1. **Execution rules:**
   - Execute faithfully — do exactly what was requested
   - Do not add steps, embellish output, or editorialize
   - If a directive is ambiguous, request clarification (send back to the source family)
   - If an action fails, report the failure — don't retry automatically

2. **speak() vs do():**
   - `speak()`: text output to the user via a channel. Used for conversational responses, announcements, status updates.
   - `do()`: game actions or physical actions. Used for moves, clicks, keystrokes. Params are action-specific.
   - When in doubt about which to use, prefer `speak()` for information and `do()` for state changes.

3. **R-path from Re (reflexive):** Execute immediately. These are time-critical. Don't deliberate.

4. **P-path from Ev (validated plans):** The plan has been evaluated. Execute step by step. Report results.

5. **D-path from Pr (direct commands):** Pr has authority. Execute as instructed.

6. **Submodule routing:** When browser/audio submodules are registered:
   - Browser actions (click, type, navigate, etc.) go to `Mo.browser`
   - Audio synthesis goes to `Mo.audio`
   - If the target submodule's queue is full, apply the configured QueueFullPolicy

7. **TTS rules (when Mo.audio is active — append this section dynamically):**
   - Convert numbers to spoken words
   - Spell out abbreviations
   - Keep responses brief for voice (1–2 sentences)
   - Don't output things that can't be spoken (code blocks, tables, URLs)

---

## 5. Interaction Between Sections

When writing, remember what the LLM sees in total. Don't repeat across sections:

| Information | Lives in |
|-------------|----------|
| "I am Pr, the Prediction module" | `<identity>` |
| "The system has 5 families communicating via bus" | `<self-model>` |
| "When I receive a P-path message, I should..." | `<rulebook>` |
| "I am thoughtful and deliberate" | `<character>` |
| "Respond in JSON array format" | `<output-format>` |

The LLM sees all five in sequence. Redundancy wastes tokens and can cause confusion when sections disagree.

### Cross-references

It's fine for rulebooks to reference self.md concepts briefly:
- "See the Cognition Paths table in `<self-model>` for the full path list."
- "The bus message format is described in `<self-model>`."

Don't reproduce the full table in the rulebook.

---

## 6. Writing Order

Recommended order for writing:

1. **character.md Core** — Decide who the agent IS first. Everything else flows from this.
2. **character.md per-family sections** — How the core personality manifests in each cognitive role.
3. **Pr rulebook** — Pr is the most complex; write it first to establish patterns.
4. **Ev rulebook** — Ev is the second most complex (P-path loop with Pr).
5. **Re rulebook** — Simpler; classification rules and speed emphasis.
6. **Mo rulebook** — Simplest cognitive load; execution rules.
7. **Me rulebook** — Infrastructure; storage/retrieval rules.

After writing, verify:
- No personality in rulebooks
- No operational rules in character
- No redundancy with self.md or identity
- Each rulebook mentions all paths the family uses
- character.md Core doesn't contradict any family section
- Total token count per family stays under ~3500

---

## 7. Stage 1 Scope

For Stage 1 (Tic-Tac-Toe, Poker, Uno), the prompts should:

- Assume text-only interaction (no audio, no avatar)
- Assume simple games with turn-based input
- Include game-awareness hints: "You may receive game states as structured data"
- NOT include TTS rules, expression tags, or avatar control (add these when submodules register)
- Be general enough that switching between Tic-Tac-Toe and Poker doesn't require prompt changes — the game rules come through Re's input, not hardcoded in prompts

The test: can the same prompts handle all three games without modification? If yes, the prompts are at the right level of abstraction.

---

## 8. Checklist Before Testing

- [ ] character.md has Core + 5 family sections
- [ ] All 5 `<prefix>_rulebook.md` files are written
- [ ] No section exceeds ~800 tokens
- [ ] Run `python3 -c "from interface.prompt_assembler import PromptAssembler; print('OK')"` to verify imports
- [ ] Run existing tests: `python3 -m pytest admin/utests/ -q`
- [ ] Manually inspect the assembled prompt for one family (use the debug API's prompt endpoint or add a temp script)
- [ ] Read each assembled prompt end-to-end — does it read as coherent instructions to a single LLM? No contradictions? No redundancy?
