# Glossary of terms from the multimodal agent design

Use this as a study map. It’s organized by domain, with concise, practical definitions.

---

## Core model types and paradigms

- **VLM (Vision-Language Model)**: A model that jointly processes images and text via cross-attention, enabling it to “read” screens and respond or plan actions directly.

- **LLM (Large Language Model)**: A text-only model used here for planning, decomposition, and reasoning over a structured UI graph and goals.

- **Hybrid agent (VLM-assisted)**: An agent that primarily uses specialized perception and a small planner, and only escalates to a VLM/remote LLM for ambiguous or novel cases.

- **Modular pipeline**: An architecture composed of distinct, specialized models (detector, OCR, role classifier, planner, executor) connected via a shared data representation.

- **Zero-shot/few-shot generalization**: Ability to perform tasks without (zero) or with very few (few) task-specific examples, typically via pretrained models.

- **Instruction tuning**: Fine-tuning a model on instruction-response pairs to better follow task prompts.

---

## Computer vision and OCR

- **Detector (object detection)**: A model that proposes bounding boxes and classes for visual elements (e.g., buttons, fields).

- **DETR (DEtection TRansformer)**: A transformer-based detector that treats detection as set prediction with Hungarian matching.

- **Deformable-DETR**: A DETR variant using deformable attention for multi-scale, sparse sampling to improve speed and small-object detection.

- **YOLOX / YOLOv8**: Single-stage detection families optimized for speed with competitive accuracy; useful baselines or fast proposals.

- **Bounding box (bbox)**: Rectangle enclosing an element, typically recorded as normalized coordinates [x1, y1, x2, y2].

- **Logits**: Pre-softmax raw scores output by a model representing unnormalized class evidence.

- **Confidence (score)**: A probability-like value (often post-softmax/sigmoid) expressing model certainty in a prediction.

- **Multi-scale features**: Feature maps at multiple resolutions to capture both large and small elements.

- **Class-agnostic proposals**: Region proposals generated without committing to a specific class until a later classification stage.

- **Domain randomization**: Data augmentation altering styles, fonts, colors, and layouts to improve robustness and generalization.

- **Synthetic HTML renders**: Artificially generated web UIs rendered to images with perfect ground-truth labels for bootstrapping.

- **OCR (Optical Character Recognition)**: Recognizing text from images; outputs tokens with text content and bounding boxes.

- **CTC (Connectionist Temporal Classification)**: A training criterion for sequence models that aligns input frames to output tokens without explicit per-frame labels.

- **Seq2seq (Sequence-to-sequence)**: A model that maps an input sequence (e.g., image features) to an output sequence (text), used in OCR and planning.

- **Reading order**: The sequence in which OCR tokens are arranged to reconstruct lines/paragraphs; important for label association.

---

## UI elements, roles, and states

- **Role**: Semantic type of an element (e.g., button.primary, text_field, dropdown) beyond raw visual class.

- **Affordance**: Visual cues that suggest possible actions (e.g., raised button, underlined link).

- **State**: Dynamic properties like enabled/disabled, focused/blurred, required/optional, valid/invalid, selected/unselected.

- **Modal**: A blocking overlay/dialog requiring interaction before returning to the underlying UI.

- **Toast**: A transient notification overlay, often non-blocking.

- **Captcha / 2FA prompt**: Anti-bot or verification UI that introduces special handling or human intervention.

- **Label association**: Linking a textual label to the correct input field using proximity, alignment, or arrows/ARIA semantics.

- **Visibility score**: A numeric estimate of how visible an element is (based on size, contrast, occlusion, opacity).

- **Z-index / Z-order**: The stacking order of elements; higher values appear above lower ones.

- **Viewport**: The currently visible portion of the screen/scroll container.

- **Hit region**: The clickable area of an element; may differ slightly from the visual bbox.

- **Scroll container**: A sub-region with independent scrolling (e.g., a div with overflow).

---

## Graph representation and serialization

- **UI graph / element graph**: A structured representation of the screen, with nodes (elements) and edges (relationships).

- **Nodes (elements)**: Items with attributes: bbox, role, text, state, z-index, visibility, container_id, element_id.

- **Edges (relations)**:
  - Spatial: above/below/left_of/overlaps.
  - Containment: element within container/pane/modal.
  - Logical: label_for, described_by.
  - Navigation: approximated tab order or focus order.

- **Element_id (persistent id)**: A stable identifier assigned across frames to the same evolving element.

- **IoU (Intersection over Union)**: Overlap metric for boxes, used for tracking and detection evaluation.

- **Text fingerprint**: A compact representation (e.g., hash/embedding) of an element’s text for matching across frames.

- **Embedding similarity**: Vector similarity (cosine/dot) used to match elements or compare contexts.

- **Serialization**: Converting the UI graph into a linear token sequence or JSON for model inputs and logs.

- **Relation tokens**: Serialized tokens encoding edges such as [REL e1 above e2].

- **Container boundaries**: Markers indicating the start/end of a group of elements (e.g., a form section).

- **Token budget**: The maximum number of tokens your planner can ingest; drives how much detail you serialize.

---

## Actions, predicates, and execution schema

- **Atomic action**: Minimal executable unit (move_to, click, type_text, keypress, scroll, wait_for).

- **Macro action**: A higher-level action expanded into atomics (focus_and_type, select_dropdown, dismiss_modal).

- **Predicates**: Boolean checks over state (element_visible, text_present, url_matches, network_idle).

- **Preconditions / post-conditions**: Expected state before/after an action to validate correctness.

- **Executor / controller**: Component that converts planned actions into mouse/keyboard events and verifies outcomes.

- **JSON action schema**: A structured format logging intended, candidate, and executed actions along with outcomes.

- **Network idle**: A predicate approximating that background network activity has settled before proceeding.

- **Hotkey**: A combination of keypresses (e.g., Ctrl+C) executed as a single action.

---

## Planning and control hierarchy

- **Reflex controller**: A small, fast model mapping current state + subgoal to the next atomic action.

- **Tactical planner**: A local (small) LLM/VLM that produces short-horizon plans for tasks like completing a form.

- **Strategic planner**: A higher-capacity (often remote) model handling long-horizon goals and subgoal decomposition.

- **Arbitration policy**: Logic that decides whether to act via reflex, consult tactical, escalate to strategic, or ask a human.

- **Confidence gating**: Threshold-based decision to act or escalate depending on model confidence (e.g., below \(\tau_1, \tau_2\)).

- **Backoff / rollback**: Reverting recent actions and trying alternatives after failures.

- **Horizon (planning horizon)**: The number of steps ahead a planner considers (short, medium, long).

- **Guardrails**: Constraints that prevent unsafe or out-of-scope actions (e.g., destructive operations).

- **Abstention**: The model explicitly choosing not to act when uncertainty is high.

- **Tool-use restriction**: Limiting a planner to emit plans (JSON) rather than directly controlling the executor.

- **Chain-of-state (reasoning)**: Producing explicit state transitions and checks instead of free-form internal thoughts.

---

## Learning algorithms and training losses

- **Behavior cloning (BC)**: Supervised learning from expert demonstrations mapping state to action.

- **DAgger (Dataset Aggregation)**: Iteratively collecting data where the current policy acts, and an expert corrects mistakes; new data is aggregated for training.

- **RL (Reinforcement Learning)**: Learning a policy \(\pi(a|s,g)\) to maximize expected reward via interaction.

- **MDP (Markov Decision Process)**: Formalism with state \(\mathcal{S}\), actions \(\mathcal{A}\), transition \(T(s,a)\), and reward \(R\).

- **Sparse reward**: Reward only at goal completion.

- **Reward shaping**: Intermediate rewards for sub-goals (e.g., field filled, page advanced).

- **Advantage actor-critic (A2C/A3C)**: RL algorithms using a policy (actor) and value function (critic) for stable learning.

- **Offline RL**: Learning from logged trajectories without online interaction.

- **CQL (Conservative Q-Learning)**: Offline RL method that penalizes out-of-distribution actions for safer policies.

- **Hungarian matching**: Optimal bipartite matching used in DETR to align predictions with ground-truth boxes.

- **L1 loss**: Absolute error loss for regression targets (e.g., box coordinates).

- **GIoU loss (Generalized IoU)**: A box regression loss that accounts for non-overlapping boxes better than IoU alone.

- **Cross-entropy (CE) loss**: Standard classification loss comparing predicted probabilities to one-hot labels.

- **Contrastive loss**: Trains embeddings to pull similar items together and push dissimilar ones apart.

- **Triplet loss**: A contrastive variant using anchor–positive–negative triplets to shape embedding space.

---

## Calibration and uncertainty

- **Calibration**: Aligning predicted probabilities with true likelihoods of correctness.

- **Temperature scaling**: Post-hoc calibration dividing logits by a temperature parameter before softmax.

- **Platt scaling**: Logistic regression-based calibration mapping scores to probabilities.

- **Monte Carlo dropout**: Estimating uncertainty by performing multiple forward passes with dropout enabled.

- **ECE (Expected Calibration Error)**: A metric quantifying the gap between predicted confidence and observed accuracy.

- **Abstention classifier (“can-I-do-this?”)**: A model predicting whether the agent should act or escalate given state-action.

---

## Data, labeling, and synthetic generation

- **Active learning**: Prioritizing uncertain or high-value samples for labeling to maximize data efficiency.

- **Uncertainty-first queue**: A labeling queue ordered by model uncertainty/disagreement.

- **Temporal linking**: Labeling the same element across frames for consistent element_id assignment.

- **Diff viewer**: A tool showing before/after states with highlighted changes to validate effects of actions.

- **Bulk actions**: UI labeling operations applied to many items at once (e.g., accept all high-confidence boxes).

- **One-keystroke corrections**: UI design pattern to speed annotation with minimal friction.

- **Class taxonomy**: The set of element roles and states you choose to label; impacts model coverage and labeling effort.

- **Schema (logging/labeling)**: The structured fields (JSON) you record for episodes, steps, elements, and outcomes.

- **Synthetic data generator**: A system that procedurally creates UIs and ground-truth labels for rapid pretraining.

- **HTML component library**: A catalog of UI widgets used by the synthetic generator to compose varied pages.

---

## Execution engine and interaction mechanics

- **Deterministic mouse paths**: Reproducible cursor trajectories generated via parametric curves.

- **Bézier curve**: A smooth polynomial curve commonly used to model human-like mouse movements.

- **Seed (random seed)**: A number that initializes pseudo-randomness to make behavior reproducible.

- **Click validation**: Verifying that a click produced the intended state change (e.g., focus gained, element toggled).

- **Off-by-one error**: A boundary or indexing mistake that can cause clicks to land one pixel outside the target.

- **OCR echo**: Re-reading text via OCR after typing to confirm field contents.

- **Caret**: The text cursor indicating insertion point in a text field.

- **Downsampled image**: A lower-resolution version used for fast, coarse detection between full passes.

- **Cache reuse / quick-hash**: Skipping expensive recomputation by hashing frames and reusing prior graphs if unchanged.

---

## Escalation and human-in-the-loop workflows

- **Escalation triggers**: Conditions like low confidence, repeated failures, or novel UI that prompt consultation.

- **Ask mode**: The agent presents candidates and uncertainty; a human selects the correct action.

- **Teach mode**: A human demonstrates or defines a macro once; the agent reuses it when detecting similar contexts.

- **Macro reuse**: Pattern matching to invoke previously taught multi-step actions.

---

## Evaluation metrics and diagnostics

- **mAP@IoU (mean Average Precision at IoU)**: Detector performance averaged across IoU thresholds and classes.

- **IDF1 (Identity F1)**: Tracking metric combining precision/recall of correctly maintained identities across frames.

- **OCR word accuracy / CER (Character Error Rate)**: OCR correctness at word/character levels.

- **F1 score**: The harmonic mean of precision and recall for classification tasks (e.g., role/state).

- **Task success rate**: Percentage of episodes where the end goal is achieved.

- **Steps-to-success**: Number of actions taken versus an expert baseline.

- **Interventions per 100 episodes**: How often human help is required; measures autonomy.

- **Action validity rate**: Fraction of actions that met preconditions and were sensible.

- **ECE (Expected Calibration Error)**: See Calibration; used to assess confidence quality.

- **End-to-end latency**: Time from screenshot capture to action execution.

- **Robustness tests**: Performance under theme changes, zoom levels, fonts, popups, and layout variants.

- **Token/compute budget**: Limits on model input size and computational resources per decision.

---

## Performance optimization and deployment

- **Quantization**: Reducing numerical precision (e.g., FP32 → INT8/INT4) to speed inference and reduce memory.

- **Distillation**: Training a smaller “student” to mimic a larger “teacher,” preserving performance with lower cost.

- **Global screenshot embeddings**: Reusable vector summaries of screens to speed matching or planning.

- **Crop-level re-evaluation**: Re-running models on localized regions instead of the full image to save compute.

- **Caching**: Storing intermediate results (graphs, embeddings) to avoid redundant computation.

---

## Security, privacy, and safety

- **PII (Personally Identifiable Information) handling**: Strategies to mask, synthesize, or restrict sensitive data use.

- **Dual confirmation**: Requiring two approvals for destructive actions (e.g., delete, purchase).

- **Allowlist/denylist**: Domains or actions explicitly allowed or blocked.

- **Rate limiting**: Restricting action frequency to avoid abuse or detection.

- **Robots/ToS constraints**: Respecting site policies and terms of service for automation.

- **Hashing / truncation**: Techniques to anonymize stored text while enabling matching.

- **On-disk encryption**: Encrypting logs and datasets at rest.

- **Guarded execution**: Enforcing preconditions and human confirmation before high-risk actions.

---

## Open design knobs (tunable choices)

- **Graph serialization format**: The exact token/JSON layout for planners; impacts accuracy vs token budget.

- **Class taxonomy granularity**: How detailed your role/state classes should be for useful generalization.

- **Confidence thresholds \(\tau_1, \tau_2\)**: Gates for reflex vs tactical vs strategic vs human escalation.

- **Failure backoff policy**: Rules for retries, alternative candidates, and rollback windows.

- **Synthetic generator spec**: The variety and parameters (layouts, skins, locales) for synthetic UI data.

- **Privacy strategy**: Which texts are hashed/truncated, where encryption applies, and retention windows.

- **Active-learning loop**: Criteria for uncertainty sampling and annotator queues.

- **Calibration regimen**: Choice of temperature/Platt scaling and validation datasets.

---

## Mathematical notation (used in planning)

- **State \(\mathcal{S}\)**: All information about the environment at a time (screenshot, UI graph, focus, cursor).

- **Actions \(\mathcal{A}\)**: The set of possible operations (click, type, scroll, etc.).

- **Policy \(\pi(a|s,g)\)**: Probability of action \(a\) given state \(s\) and goal \(g\).

- **Transition \(T(s,a)\)**: The environment’s state update after taking action \(a\) in state \(s\).

- **Reward \(R\)**: Scalar feedback for goal progress; can be sparse or shaped.

- **Planning horizon**: The number of future steps considered when choosing actions.

---
