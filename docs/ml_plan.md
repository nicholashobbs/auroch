# Multimodal agent architecture: deep dive and tradeoffs

You’re building an embodied, screen-native agent. The big design decision is how to combine perception (what’s on the screen?), grounding (what is each thing for?), and policy (what should I do next given my goal?). Below is a deep, implementation-level blueprint with concrete tradeoffs so you can spec the UI, data, and training loops with confidence.

---

## VLM vs modular pipeline: what, why, and when

### What is a VLM?
A vision-language model jointly encodes pixels and text tokens with cross-attention and can “read” a screenshot and produce text or structured outputs directly. It can also act as a planner if you prompt it with goal + screen.

### What is a modular pipeline?
A set of specialized components: detector + OCR + layout/role classifier + planner + controller. Each is trained on targeted labels and stitched via a common UI graph/JSON.

### Strategic comparison

| Dimension | VLM-first agent | Modular CV/OCR + LLM agent |
|---|---|---|
| Perception accuracy | Strong zero/few-shot on common UI patterns; may miss fine UI states (disabled, hidden) | High with targeted labels; robust to small visual variants |
| Data needs | Less explicit supervision; benefits from instruction-tuning on your tasks | Needs curated labels per module; cheaper per-label and easier to bootstrap synthetically |
| Latency | Often higher; big context images + long responses | Lower; small, specialized models; parallelizable |
| Interpretability | Low: “black-box” attention | High: explicit elements, roles, states, confidences |
| Controllability | Hard to constrain outputs to safe actions | Strong: validate pre/post-conditions before acting |
| Failure modes | Hallucination; overgeneralization | Integration complexity; cascading module errors |
| Incremental improvement | Monolithic finetune | Swap/finetune modules independently |
| On-device feasibility | Hard (size/memory) | Plausible with quantized detectors/OCR/local LLM |
| Data lifecycle | Logs are textual; harder to tie to UI pixels | Rich, structured telemetry for active learning |
| Human-in-the-loop | Hard to granularly correct | Easy: correct boxes, roles, relations, plans |

Recommendation: use a hybrid. Let specialized perception build a structured UI graph; use a small planner model locally; selectively escalate to a VLM (local or remote) for ambiguous reasoning or unseen UI paradigms. This preserves speed, control, and data quality while keeping a “big brain” on call.

---

## Formalizing the problem

- State \(\mathcal{S}\): current screenshot, scroll offset, cursor, focus, and a structured UI graph.
- Actions \(\mathcal{A}\): move(x,y), click(kind), type(text), keypress(key), scroll(Δ), wait(cond), select(range), drag(start,end).
- Transition \(T(s,a)\): VM executes; returns new screenshot and events.
- Reward \(R\): sparse (goal completion), plus shaped rewards (field filled, page advanced, error avoided).
- Policy \(\pi(a|s,g)\): conditioned on goal \(g\) and state \(s\).
- Planner horizon: short (single step) for “reflex”; medium (N-step) for forms; long for multi-page flows.

You’ll split this into perception (to build the UI graph) and control (to pick actions using that graph).

---

## The perception stack (propose → verify → track)

### 1) Element proposal (detector)
- Model: transformer-based detector (DETR-family) with custom classes.
- Outputs: bounding boxes, class logits, confidence.
- Classes: button, text_field, password_field, checkbox, radio, dropdown, link, image, icon, modal, toast, error, label, tab, pagination, captcha, hidden-like, disabled-like.
- Loss: Hungarian matching + L1 box + GIoU + class CE.
- Tricks:
  - Multi-scale features to catch tiny icons.
  - Class-agnostic proposals + class head to reduce blind spots.
  - Domain randomization with synthetic HTML renders to bootstrap.

### 2) OCR (read text and attributes)
- Model: high-accuracy OCR with bounding boxes and reading order; add a text-line detector if necessary.
- Outputs:
  - token: text, bbox, logit confidence
  - attributes: font size, bold/italic, color, contrast estimates (weak proxy for affordance)
- Post-process:
  - Merge tokens into lines/labels.
  - Language detection for locale-aware patterns (dates, phone numbers).

### 3) Role assignment and affordances
- Inputs: detector boxes, OCR tokens, spatial relations.
- Tasks:
  - Role classification: map boxes to semantic roles beyond detector classes (primary_button, destructive_button, inline_link, nav_link, social_oauth, TOS_checkbox).
  - Label association: link text labels to fields (via proximity, alignment, arrows/asterisks).
  - State inference: {enabled/disabled, selected, focused, required, invalid}.
- Model: graph neural net or transformer over an “element graph.”
- Outputs: a typed node set with attributes and confidences.

### 4) Layout and structure
- Build a UI graph:
  - Nodes: elements with {bbox_norm, role, text, state, z-index order, visibility score, scroll_container_id}.
  - Edges: spatial (above/below/left_of/overlaps), logical (label_for, described_by), containment (dom-like pane grouping), navigation (tab-order approximations via focus tests).
- Maintain temporal correspondence across frames:
  - Element tracking via IoU + text fingerprint + embedding similarity.
  - Assign persistent element_ids across scrolls and page changes.

### 5) Precondition checks (safety/precision)
- Validate clickability: overlap with hit region, not covered by modal, enabled, visible > threshold, within viewport.
- Validate typing: caret/focus presence; fall back to click-then-type if needed.

This stack yields a high-quality, explicit UI graph your planners can consume.

---

## Action representation and DSL

Define an action schema that’s both human-auditable and machine-trainable.

- Atomic actions:
  - move_to(element_id|x,y, strategy)
  - click(element_id|x,y, button=left|right|middle, clicks=1|2)
  - type_text(text, method=insert|replace)
  - keypress(key), hotkey([keys])
  - scroll(container_id|global, dy)
  - wait_for(predicate, timeout_ms)
- Predicates: element_visible(id), url_matches(regex), text_present(str), toast_contains(str), network_idle(ms)
- Macro actions (for planner to emit but expanded by executor):
  - focus_and_type(field_id, text, mask_policy)
  - select_dropdown(option_text|index)
  - dismiss_modal()
  - navigate_back()

Represent planner outputs as JSON so you can log, diff, and replay.

---

## Planning stack: reflex → tactical → strategic

### 1) Reflex controller (local, small)
- Inputs: UI graph, current goal step.
- Outputs: next atomic action.
- Model: sequence model over serialized UI graph and goal step, trained via behavior cloning.
- Use cases: “click the ‘Sign up’ button,” “type email,” “scroll to reveal next field.”
- Training data: your labeled steps; DAgger-style corrections.

### 2) Tactical planner (local LLM or small VLM)
- Inputs: full UI graph, short-horizon task (“complete this form”).
- Outputs: action plan (macro + atomics), with expected pre/post-conditions and per-step confidence.
- Reasoning mode: chain-of-state (no free-form chain-of-thought in prod); request missing info explicitly (“need password policy”).
- Calibration: temperature=low for determinism; abstain when confidence < τ.

### 3) Strategic planner (optional, remote LLM/VLM)
- Inputs: long-horizon goal (“sign up for X, confirm email, set profile”).
- Outputs: subgoal decomposition and guardrails (success criteria, checkpoints).
- Triggered only when:
  - New domain with unfamiliar UI patterns.
  - High uncertainty across multiple steps.
  - Repeated failures or loops detected.

### Arbitration policy
- Confidence gating:
  - If reflex confidence ≥ τ1 → execute.
  - Else ask tactical. If tactical ≥ τ2 → execute.
  - Else escalate to strategic or human.
- Backoff on failure:
  - Roll back last N steps; try alternative candidates.
  - If three consecutive failures → escalate.

### Memory
- Short-term: last K frames with element_id continuity.
- Episodic: per-domain heuristics learned (e.g., “login often in navbar top-right”).
- External: credential vault, PII policies, and templates.

---

## Learning paradigms and losses

### Perception
- Detection: DETR losses (Hungarian + L1 + GIoU + CE).
- OCR: CTC or seq2seq cross-entropy with augmentation.
- Role/state: cross-entropy; multi-label BCE for states.
- Tracking: contrastive loss to keep same-element embeddings close across frames; triplet loss for different elements.

### Policy
- Behavior cloning:
  - Represent each step as (UI graph serialization, goal_step) → action.
  - Loss: cross-entropy for discrete parts; L1 for coordinates; auxiliary loss on precondition prediction.
- DAgger:
  - Run the current policy; allow human corrections; aggregate to dataset.
- RL fine-tuning (optional, targeted):
  - On simulators or non-destructive sandboxes.
  - Reward shaping: +1 for valid field filled, +5 for form submit, -1 for error dialog, small - for extraneous clicks.
  - Algorithm: advantage actor-critic or offline RL with conservative Q-learning on logs.

### Calibration and abstention
- Temperature scaling or Platt scaling on action logits.
- Monte Carlo dropout for uncertainty proxies on small models.
- Train a separate “can-I-do-this?” classifier over state-action pairs to decide when to escalate.

---

## Data and labeling: make the UI earn you perfect training signals

### Ground-truth objects to capture
- Elements: bbox_norm [x1,y1,x2,y2], class, role, states, text, z-index, visibility score, scroll_container_id, element_id (persistent), confidence (if auto-proposed).
- Relations: label_for, described_by, within_modal, above/below/left_of, tab_order_index (approximate).
- OCR tokens: text, bbox, confidence, line_id.
- Actions: schema described earlier, actor=human|agent, success, error, retries, pre/post screenshots.
- Goals: episode_id, goal_text, subgoals, success criteria, stop reasons.
- Env: URL, viewport size, DPI, OS/browser skin, theme, locale.
- Outcome: success/failure, time-to-complete, human_interventions, reasons_for_intervention.

### Episode structure
- A “workflow” is an episode with steps; every step links to:
  - Input state (screenshot_id + UI graph hash)
  - Intended action (gold)
  - Candidate actions and scores (from models)
  - Executed action and outcome
  - Delta (DOM/text diff if available; otherwise visual diff + element graph diff)

### Labeling UI must-haves
- Auto-propose boxes + roles + label links; accept/correct with single keystrokes.
- Bind label text to nearest field quickly (hover-to-link).
- Temporal linking tools: “same element across frames” one-click matcher.
- Step composer:
  - Pick element → choose action → set parameters (text) → define expected post-condition.
  - Mark failures and provide the correct action (for DAgger).
- Diff viewer: before/after screenshot + highlighted changed nodes.
- Uncertainty-first queue: active learning surfaces low-confidence or high-disagreement samples.
- Synthetic booster: load procedurally generated pages with known ground truth for fast labeling warm-start.

### Serialization (example)
```json
{
  "episode_id": "ep_2025-08-07T14:32Z_001",
  "goal": "Create account on example.com",
  "steps": [
    {
      "step_id": 1,
      "screenshot_id": "img_001",
      "ui_graph": {
        "elements": [
          {"element_id":"e17","bbox":[0.72,0.12,0.85,0.17],"role":"button.primary","text":"Sign up","state":{"enabled":true,"visible":true},"z":9,"container":"root"}
        ],
        "relations":[{"type":"above","src":"e17","dst":"e42"}]
      },
      "action_intent": {"type":"click","target":"e17"},
      "candidates":[
        {"action":{"type":"click","target":"e17"},"score":0.91},
        {"action":{"type":"click","target":"e03"},"score":0.22}
      ],
      "executed_action":{"type":"click","target":"e17"},
      "outcome":{"success":true,"post_screenshot_id":"img_002"}
    }
  ]
}
```

---

## UI graph serialization for models

Serialize the graph into a token sequence for planners:
- Global header: goal, url domain, viewport.
- Element tokens: [ELEM id role x1 y1 x2 y2 visible enabled text_substr]
- Relation tokens: [REL id1 type id2]
- Container boundaries: [CONTAINER id start/end]
- Special tokens for focus, cursor, scroll offsets.

Keep text truncated with hashes to preserve privacy while retaining matching ability.

---

## Execution engine and feedback

- Deterministic mouse paths: curved Bézier with randomization bounded by a reproducibility seed.
- Click validation: sample a few pixels inside target bbox to avoid off-by-one; verify state change or event.
- Text entry:
  - Prefer OS-level paste when allowed; otherwise per-keystroke with rate variance.
  - Verify field value via OCR echo or by re-focusing and selecting-all → OCR.
- Scroll strategy:
  - If element not visible, scroll container in small steps; after each, re-run cheap local detector on downsampled image to find target.
- Recovery:
  - Detect popups/modals/toasts; attempt dismiss patterns; if destructive risk detected, abstain and escalate.

---

## Escalation and human-in-the-loop

- Triggers:
  - Confidence below thresholds.
  - No progress after K steps or T seconds.
  - Repeated unexpected state transitions (e.g., captcha, 2FA prompts).
- Ask mode:
  - Present compact UI graph + top-3 candidate actions with scores.
  - Human selects/edits; feedback captured as gold for DAgger.
- Teach mode:
  - Human can define a macro (e.g., “OAuth via Google”) once; agent reuses by matching patterns later.

---

## Synthetic data to accelerate cold start

- Procedural HTML generation with variability:
  - Layouts: single/multi-column, stacked forms, wizards.
  - Skins: light/dark, fonts, icon sets.
  - Content: realistic labels with noise (typos, asterisks).
- Render to images; export perfect ground-truth elements/relations.
- Domain randomization: jitter bbox, blur, scaling, noise to mimic VMs.

---

## Evaluation suite

- Perception:
  - mAP@IoU for detection.
  - OCR word accuracy; character error rate.
  - Role/state F1; label-field association accuracy.
  - Tracking IDF1 across frames.
- Control:
  - Task success rate per domain.
  - Steps to success vs expert.
  - Human interventions per 100 episodes.
  - Action validity rate (preconditions met).
  - Calibration: ECE for action confidence.
- System:
  - End-to-end latency per step.
  - Token/compute budget by tier (reflex/tactical/strategic).
  - Robustness: theme swap, zoom levels, popups.

---

## Model choices by tier (representative families)

- Detector: DETR/Deformable-DETR variants; YOLOX/YOLOv8 as speed baselines.
- OCR: high-accuracy recognizer (seq2seq) + fast lightweight fallback; consider dictionary bias for emails/domains.
- Role/state: transformer over serialized graph with relative spatial encodings.
- Reflex policy: small encoder-decoder transformer distilled from tactical planner.
- Tactical planner: local LLM (4–13B) fine-tuned on your graph serialization; optionally conditioned on cropped element images.
- Strategic planner: remote LLM/VLM with tool-use restriction to planning; returns JSON-only plan.

Quantize and distill aggressively; cache global screenshot embeddings across small DOM changes; use crop-level re-evaluation to save time.

---

## Security, privacy, and safety constraints in the policy

- PII handling: mask or synthesize data; disallow typing sensitive info unless explicitly authorized by goal.
- Destructive actions: require dual confirmation or human approval (delete, purchase).
- Domain allowlist/denylist; rate limits; honor robots/ToS constraints for automation where applicable.

---

## Putting it together: end-to-end loop

1. Capture screenshot; compute quick-hash to reuse cached graph if trivial changes.
2. Run detector + lightweight OCR; build/refresh UI graph and track element_ids.
3. Validate candidate targets against preconditions.
4. Try reflex policy. If low confidence, call tactical planner on serialized graph.
5. Execute action via executor; verify post-condition (change in graph or predicate).
6. If failure or low progress, alternative candidate; else escalate to strategic or human.
7. Log everything for training: proposals, corrections, confidences, outcomes.
8. Nightly:
   - Retrain detector/role on corrected labels.
   - DAgger aggregate policy data.
   - Distill tactical into reflex for speed.
   - Recalibrate confidence thresholds.

---

## What this means for your labeling UI spec

- Schema-first: implement the JSON above; every widget in the UI writes to that schema.
- Speed matters: all corrections must be one-keystroke operations; power annotators with bulk actions.
- Sequence-aware: the “step composer” is as important as the box tool—action, pre/post-conditions, and outcome are gold.
- Active learning: feed annotators the hardest/most-uncertain samples; you get 10× data value per minute.
- Temporal linking: make it trivial to say “this element equals that one in the next frame.”
- Macro definition: let humans define named macros; log matches when agent reuses them.

---

## Where a VLM still helps

- Ambiguous icons, novel widgets, or dense dashboards where text cues are weak.
- Explaining unexpected states (“Your password must include …”) to adapt the plan.
- Generalizing layout heuristics across unseen design systems.

Use it sparingly: pass in a compact, cropped panel or the serialized graph with thumbnails to keep token cost down; request JSON outputs with explicit action candidates and confidences; never let free-form text directly drive the executor.

---

## Open design choices to decide (and I can help you nail them)

1. Graph serialization format and max token budget for the local planner.
2. Class taxonomy for roles/states that balances coverage and labeler effort.
3. Confidence thresholds τ1/τ2 and failure backoff policy.
4. Synthetic data generator spec (HTML components library and variation knobs).
5. Which elements/relations to track across frames for stability vs cost.
6. Privacy strategy for text logs (hashing, truncation, on-disk encryption).

If you share a sample episode (screenshot + your current labeling JSON), I’ll tailor the taxonomy, serialization, and the active-learning loop to your exact needs—and we can wire the UI to produce training-perfect data from day one.