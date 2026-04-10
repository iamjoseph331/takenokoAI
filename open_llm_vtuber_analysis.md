# Analysis: What TakenokoAI Can Learn from Open-LLM-VTuber

**Date:** 2026-04-10
**Source:** `/Users/macbook/Code/Sideprojects/Open-LLM-VTuber` (v1.2.1)

---

## 1. Project Overview

Open-LLM-VTuber is a voice-first AI companion with Live2D avatar, real-time voice, optional vision (camera/screen), and desktop pet mode. It runs locally with pluggable LLM/ASR/TTS backends. Architecture: FastAPI + WebSocket backend, React frontend (separate repo via git submodule).

Key relevance to TakenokoAI: it solves **embodiment** — giving an LLM a face, voice, expressions, and visual perception. TakenokoAI's five-family architecture could gain a body through similar techniques.

---

## 2. Prompt Engineering Techniques

### 2.1 System Prompt Assembly (similar to our PromptAssembler)

Open-LLM-VTuber builds the system prompt by **concatenating** a persona + utility prompt snippets:

```python
# service_context.py — construct_system_prompt()
for prompt_name, prompt_file in self.system_config.tool_prompts.items():
    prompt_content = prompt_loader.load_util(prompt_file)
    persona_prompt += prompt_content
```

The `tool_prompts` dict in YAML maps logical names to `.txt` files under `prompts/utils/`. This is analogous to our PromptAssembler's multi-section approach but **flat concatenation** instead of XML tags.

**Takeaway for TakenokoAI:** Our XML-tagged approach (`<identity>`, `<self-model>`, `<rulebook>`, `<character>`, `<output-format>`) is more structured. But their modular `.txt` files approach is good for **hot-swappable capabilities** — we could adopt this for submodule-specific prompt fragments that get appended when a submodule is active.

### 2.2 Persona Prompt (Character Definition)

Personas live in YAML `character_config.persona_prompt`. Characters are **switchable at runtime** via WebSocket — the system re-initializes the agent with the new persona. Multiple character YAMLs in `characters/` override parts of the base config via deep merge.

**Takeaway for TakenokoAI:** Our `character.md` + per-family `<character>` sections serve a similar purpose, but we lack runtime character switching. The YAML override + deep merge pattern is elegant for swapping personalities without restarting.

### 2.3 Speakable Output Prompt

```
You speak all output aloud to the user, so tailor responses as spoken words
for voice conversations. Never output things that are not spoken.

Convert all text to easily speakable words:
- Numbers: Spell out fully (three hundred forty-two...)
- Phone numbers: Use words (five five zero...)
- Dates: Spell month, use ordinals...
- Math: Describe operations clearly...
- Currencies: Spell out as full words...
```

**Takeaway for TakenokoAI:** When Mo produces speech output, the prompt should include TTS normalization rules. Directly applicable to our `Mo.audio` submodule — add to Mo's rulebook or as a utility prompt when TTS is active.

### 2.4 Concise Style Prompt

```
[Response Guidelines]
- Keep responses brief and focused (1-2 sentences)
- Favor questions over statements
- Include contextual follow-ups
- Avoid lengthy monologues
- Use simple sentence structures
```

**Takeaway for TakenokoAI:** Useful for controlling verbosity. Could be applied per-family — Pr might be verbose internally, but Mo's speech output runs through this filter.

### 2.5 Think Tag Prompt (Inner Thoughts)

```
Try to express your inner thoughts, mental activities and actions between
<think> </think> tags in most of your responses.

Examples:
<think>*lowers head, cheeks turning slightly red*</think>That's... quite
embarrassing to talk about...
```

The pipeline handles `<think>` tags specially:
- **Display**: think content shown in parentheses `(...)` as "inner thoughts"
- **TTS**: think content is **skipped** (not spoken aloud)
- **Expressions**: think content does **not** trigger expression extraction

**Takeaway for TakenokoAI:** This is a powerful pattern. Our families could use similar tags:
- `<think>` for Pr's internal reasoning (visible in debug but not spoken by Mo)
- The `summary` field in our bus messages already serves a similar broadcast purpose
- Different handling per path: P-path messages are internal deliberation; only the final Mo output is spoken

### 2.6 Live2D Expression Prompt

```
## Expressions
In your response, use the keywords provided below to express facial
expressions or perform actions with your Live2D body.

Keywords you can use:
- [neutral], [anger], [disgust], [fear], [joy], [smirk], [sadness], [surprise]

Examples:
"Hi! [joy] Nice to meet you!"
"[surprise] That's a great question! [neutral] Let me explain..."
```

The placeholder `[<insert_emomap_keys>]` is dynamically replaced with the actual model's available expressions from `model_dict.json`.

**Takeaway for TakenokoAI:** This is how the LLM drives avatar expressions — through **inline bracketed keywords** in text output. Our Ev module could tag emotional state, and Mo could extract tags before speaking. The pattern of dynamically injecting available capabilities into the prompt is reusable for any submodule.

### 2.7 Tool Guidance Prompt

```
If a tool is needed, proactively use it without asking the user directly.
You can use at most one sentence to explain your reason / plan for using
one tool.
```

**Takeaway for TakenokoAI:** Similar guidance should go in Pr's rulebook — when dispatching to submodules, don't over-explain; act decisively.

### 2.8 Proactive Speaking

```
Please say something that would be engaging and appropriate for the
current context.
```

Triggered when the system proactively initiates speech (no user input).

**Takeaway for TakenokoAI:** Our S-path idle detection + `_on_idle()` hook serves the exact same purpose. Use a similar simple prompt for Mo's idle filler responses.

---

## 3. Monitor/Screen Viewing Feature

### 3.1 Architecture

Screen viewing is **client-side capture, server-side LLM processing**:

1. **Client** (frontend/desktop app) captures screen/camera/clipboard images
2. Client sends images as **base64 data URLs** over WebSocket in the `images` field
3. Backend wraps them into `BatchInput` with `ImageData(source=ImageSource.SCREEN, ...)`
4. Agent formats them as **OpenAI multimodal messages** (`image_url` type) or **Claude image blocks**

### 3.2 Input Types (Data Model)

```python
class ImageSource(Enum):
    CAMERA = "camera"
    SCREEN = "screen"
    CLIPBOARD = "clipboard"
    UPLOAD = "upload"

@dataclass
class ImageData:
    source: ImageSource
    data: str  # Base64 encoded or data URL
    mime_type: str

@dataclass
class BatchInput:
    texts: List[TextData]
    images: Optional[List[ImageData]] = None
    files: Optional[List[FileData]] = None
    metadata: Optional[Dict[str, Any]] = None
```

### 3.3 How Images Reach the LLM

In `BasicMemoryAgent._to_messages()`:

```python
if img_data.data.startswith("data:image"):
    user_content.append({
        "type": "image_url",
        "image_url": {"url": img_data.data, "detail": "auto"},
    })
```

For Claude, the data URL is split into media_type + base64 and reformatted into Anthropic's image block format.

### 3.4 Key Insight: No Server-Side Capture

The Python backend does **not** capture screenshots itself. All image capture happens in the **frontend** (React app / desktop client). The backend is purely a **passthrough** that formats images for the LLM API.

**Takeaway for TakenokoAI:**
- Our `Re.browser` submodule (observe, screenshot) already handles web perception
- We should add `Re.screen` and `Re.camera` submodules following the same `ImageData` pattern
- The multimodal message formatting in `BasicMemoryAgent` is directly reusable for Re's input
- The `BatchInput` pattern (text + images + files + metadata) is a good model for Re's composite input handling
- For a desktop agent, we'd use Python-side capture (e.g. `mss`, `pyautogui`) since we're not browser-bound

---

## 4. VTuber Avatar Control (Making It Realistic)

### 4.1 Expression System

**Pipeline:** LLM output → extract `[emotion]` tags → map to expression indices → send to frontend

```json
// model_dict.json
"emotionMap": {
    "neutral": 0, "anger": 2, "disgust": 2, "fear": 1,
    "joy": 3, "smirk": 3, "sadness": 1, "surprise": 3
}
```

`Live2dModel.extract_emotion()` scans text for `[keyword]` patterns and returns expression indices. The `actions_extractor` transformer applies this to each sentence.

**Output payload per sentence:**

```python
@dataclass
class Actions:
    expressions: Optional[List[int]] = None   # Live2D expression indices
    pictures: Optional[List[str]] = None
    sounds: Optional[List[str]] = None

@dataclass
class SentenceOutput:
    display_text: DisplayText  # What the user sees
    tts_text: str              # What gets spoken (filtered)
    actions: Actions           # Expressions + other actions
```

### 4.2 Lip Sync (RMS Volume Envelope)

There is **no phoneme/viseme engine**. Lip sync uses **amplitude envelopes**:

```python
# stream_audio.py
def _get_volume_by_chunks(audio, chunk_length_ms=20):
    chunks = make_chunks(audio, chunk_length_ms)
    volumes = [chunk.rms for chunk in chunks]
    max_volume = max(volumes)
    return [volume / max_volume for volume in volumes]  # normalized 0.0–1.0
```

Each audio message sent to the frontend includes:
- `audio`: base64-encoded WAV
- `volumes`: list of normalized RMS values (one per 20ms chunk)
- `slice_length`: duration of each chunk (0.02s)

The **frontend** maps these volume values to the Live2D model's mouth parameter (e.g., `ParamA` or `PARAM_MOUTH_OPEN_Y`) in real-time during playback.

**Takeaway for TakenokoAI:** This is elegant and simple. Our `Mo.audio` submodule could compute the same volume envelope when synthesizing speech, and our visualization app could use it for avatar animation. **You don't need complex phoneme analysis for convincing lip sync — RMS amplitude is good enough.**

### 4.3 The Audio Payload (WebSocket Protocol)

Each spoken sentence becomes a WebSocket message:

```json
{
  "type": "audio",
  "audio": "<base64 WAV>",
  "volumes": [0.0, 0.12, 0.45, 0.89, 0.67, ...],
  "slice_length": 0.02,
  "display_text": {"text": "Hello!", "name": "AI", "avatar": null},
  "actions": {"expressions": [3]}
}
```

The frontend plays the audio while:
1. Stepping through `volumes[]` to drive mouth opening
2. Applying `actions.expressions` (switching Live2D expression)
3. Displaying `display_text` as subtitles

### 4.4 Idle Animations and Touch Interactions

`model_dict.json` also specifies:
- `idleMotionGroupName`: which motion group plays when idle
- `tapMotions`: animations triggered by clicking/touching areas of the model
- `kScale`, `xOffset`, `yOffset`: positioning/scaling

These are purely **frontend-driven** — the backend just delivers the configuration.

### 4.5 Ordered TTS Delivery

`TTSTaskManager` ensures sentences are spoken **in order** even when TTS is parallelized:
- Each sentence gets a sequence number
- A payload queue sorts results by sequence
- `finalize_conversation_turn` waits for `frontend-playback-complete` before accepting new input

**Takeaway for TakenokoAI:** Our Mo module needs the same ordered delivery. The sequence-number + priority-queue pattern is directly applicable.

### 4.6 Sentence Streaming Pipeline (Decorator Chain)

The agent output goes through a **decorator chain** of async generator transformers:

```
LLM token stream
  → sentence_divider    (tokens → sentences, handles <think> tags)
  → actions_extractor   (extract [emotion] tags → Actions)
  → display_processor   (create DisplayText, handle think parentheses)
  → tts_filter          (clean text for TTS, skip think content)
  → SentenceOutput      (display_text + tts_text + actions)
```

**Takeaway for TakenokoAI:** This is a clean pattern for our output pipeline. Instead of one monolithic `_handle_message()`, we could use decorator chains:

```
LLM output → parse_llm_outputs → expression_extractor → tts_filter → bus.send()
```

---

## 5. Concrete Recommendations for TakenokoAI

### 5.1 Near-Term (Stage 1–2)

| Area | What to Adopt | Where in TakenokoAI |
|------|--------------|---------------------|
| **Expression tags** | `[emotion]` keyword system in LLM output | Add to Ev's affordance generation; Mo extracts before speaking |
| **Speakable prompt** | TTS normalization rules | Mo's rulebook when `Mo.audio` is active |
| **Think tags** | `<think>` for inner monologue | Pr's output format; Mo skips think content for TTS |
| **Volume envelope** | RMS-based lip sync data | `Mo.audio` computes `volumes[]` alongside synthesized audio |
| **Proactive speak** | Simple nudge prompt for idle | S-path `_on_idle()` in Mo |
| **Concise style** | Brevity guidelines | Mo's prompt when in voice mode |
| **Multimodal input** | `ImageData`/`BatchInput` model | New `Re.screen` and `Re.camera` submodules |

### 5.2 Medium-Term (Stage 2–3)

| Area | What to Adopt | Where in TakenokoAI |
|------|--------------|---------------------|
| **Character switching** | YAML deep-merge for runtime persona swap | `SelfModel.write_part()` + character.md reload |
| **Sentence streaming** | Async decorator transformer chain | Pr → Ev → Mo pipeline |
| **Ordered TTS** | Sequence-numbered payload queue | Mo's output queue |
| **Live2D integration** | `model_dict.json` + expression map | New `Mo.avatar` submodule |
| **Playback sync** | `frontend-playback-complete` handshake | Visualization app WebSocket protocol |

### 5.3 Design Differences to Preserve

| Open-LLM-VTuber | TakenokoAI | Keep TakenokoAI's |
|-----------------|-----------|-------------------|
| Single LLM decides everything | Five families with separate LLMs | Yes — multi-agent is more powerful |
| Flat prompt concatenation | XML-tagged multi-section prompts | Yes — structured sections suit per-family specialization |
| Expression extraction post-hoc | Ev explicitly evaluates emotion | Yes — dedicated Ev module is more principled |
| No memory architecture | Me with 5 memory types | Yes — unique strength |
| No permission system | Pr/Ev authority model | Yes — important for multi-agent coordination |

---

## 6. Key Files Reference

| Purpose | Path in Open-LLM-VTuber |
|---------|------------------------|
| System prompt construction | `src/open_llm_vtuber/service_context.py` (lines 436–470) |
| Persona config schema | `src/open_llm_vtuber/config_manager/character.py` |
| All utility prompts | `prompts/utils/*.txt` (8 files) |
| Character definitions | `characters/*.yaml` |
| Expression extraction | `src/open_llm_vtuber/live2d_model.py` (`extract_emotion()`) |
| Action extraction transformer | `src/open_llm_vtuber/agent/transformers.py` |
| Output types (Actions, DisplayText) | `src/open_llm_vtuber/agent/output_types.py` |
| Lip sync volume computation | `src/open_llm_vtuber/utils/stream_audio.py` |
| Multimodal input types | `src/open_llm_vtuber/agent/input_types.py` |
| OpenAI multimodal formatting | `src/open_llm_vtuber/agent/agents/basic_memory_agent.py` (225–288) |
| Claude image block conversion | `src/open_llm_vtuber/agent/stateless_llm/claude_llm.py` (43–82) |
| WebSocket handler + model init | `src/open_llm_vtuber/websocket_handler.py` |
| TTS task ordering | `src/open_llm_vtuber/conversations/tts_manager.py` |
| Model metadata (emotions, motions) | `model_dict.json` |
| Default config template | `config_templates/conf.default.yaml` |
