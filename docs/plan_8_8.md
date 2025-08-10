Awesome—here’s the clean “what’s left / what’s next” plan so we can march from your current UI to an end-to-end multi-screenshot flow and be ready to start collecting ML data.

# What remains in the UI module (tight list)

1. **Polish (nearly done)**

   * [ ] Bottom pane size/spacing (done).
   * [ ] Delete/selection/auto-selection logic (done).
   * [ ] Widened TYPE editor w/ placeholder (done).
2. **JSON completeness**

   * [ ] Finalize **export schema** so it’s executable (for the Pi) **and** learnable (for ML).
   * [ ] Include metadata: screenshot IDs, image hashes, VM timestamp, RNG seeds, UI version, etc.
3. **Ready/Next Screenshot UX**

   * [ ] “Next screenshot ready” pill/overlay on the viewer (click to advance).
   * [ ] Guardrail: warn/disable actions if the visible screenshot is stale vs. VM state.
4. **Multi-screenshot session**

   * [ ] Session concept: list of (screenshot, boxes, actions).
   * [ ] Navigation: **Prev / Next** screenshot, current index, and session export.

# JSON schema (proposed)

This gives you a single file that’s both runnable and trainable:

```json
{
  "session_id": "2025-08-08T12-34-56Z-abcd",
  "ui_version": "0.4.0",
  "vm": {"os":"win11","display_scale":1.0},
  "screens": [
    {
      "screen_id": "0001",
      "screenshot_path": "screens/0001.png",
      "screenshot_sha256": "…",
      "timestamp_vm": 1723132482.524,
      "rng_seed": 214748364,
      "boxes": [
        {"id":0,"x":341,"y":228,"width":210,"height":60},
        {"id":1,"x":128,"y":512,"width":340,"height":100}
      ],
      "actions": [
        {"type":"MOVE","from":[446,258],"to":[298,562],
         "duration_ms": 312, "curve":"lognormal", "seed":12345, "generated":true},
        {"type":"CLICK","box_id":1,"params":{"button":"Left"},"timestamp":1723132483.12},
        {"type":"TYPE","box_id":1,"params":{"text":"hello world"},"timestamp":1723132483.65},
        {"type":"SCROLL","box_id":1,"params":{"amount":"-1"},"timestamp":1723132484.00}
      ]
    },
    {
      "screen_id": "0002",
      "screenshot_path": "screens/0002.png",
      "screenshot_sha256": "…",
      "timestamp_vm": 1723132488.001,
      "boxes": [...],
      "actions": [...]
    }
  ]
}
```

Notes:

* **screens\[]** = your “acts”. Each is a stable visual state.
* **boxes** are per-screen. (IDs reset per screen—simplifies life.)
* **actions** reference **box\_id** (local to that screen) and may include **generated\:true** for inferred MOVE.
* Add **screenshot\_sha256** so the runner can sanity-check it’s acting on the expected pixels.

# Translator: JSON → Pi script (executable)

Write a tiny module (host side) that produces a runnable plan for your HID driver.

## Mapping

* **CLICK**: choose a random (uniform) point inside the box; emit `move(x,y)` then `click(button)`.
* **TYPE**: same, but first ensure focus (emit a click if the previous action wasn’t already in that box), then `type_text(text)`.
* **SCROLL**: random point inside box then `scroll(amount)` (your agent interprets “-1” as \~100px—keep the factor in one place).
* **MOVE**: either use provided `from/to/duration` (generated) or compute from centers.

## Timing / randomness

* For **durations**: you already do lognormal for MOVE. Keep it here.
* For **click coordinates**: uniform random within (x..x+w, y..y+h).
* For **inter-action delays**: optional jitter (e.g., \~N(μ=80ms, σ=25ms), clamped ≥10ms).

## Safety

* Before executing a screen’s actions, the runner checks the **current screenshot hash** from the VM reflex agent matches **screenshot\_sha256**. If mismatch → pause + prompt.

# VM “Reflex” agent (minimal first pass)

Goal: detect “screen is stable” and push next PNG to host.

**Algorithm (simple & effective):**

* Capture frames at \~5–8 FPS (lossless PNG or fast JPEG).
* Compute difference score between consecutive frames (e.g., mean absolute pixel diff or downsample + SSIM).
* Keep a sliding window (e.g., last 1–2 seconds). If all diffs below threshold for N consecutive frames (e.g., 10 frames) ⇒ **stable**.
* When stable: save PNG, compute SHA-256, send `{screen_id, ts, sha256}` + blob to host over your protobuf.
* Support **“suppress detection”** flag during action replay (host sets it to ignore intentional changes while executing a queued sequence).

**Proto sketch:**

```
message FrameNotice { string screen_id; int64 timestamp_ms; bytes png; string sha256; }
message Control      { bool suppress_stability; }
```

# UI changes to support multi-screenshot flow

* Add a **session bar** under the screenshot viewer:

  * “Current: 0003 / 0012”, **Prev**, **Next**, **Accept Next (pill)**.
* When the VM agent sends a stable screenshot for the next “act”:

  * Show a floating **“Next screenshot ready”** pill on the viewer (click = advance).
  * If user has unsaved edits (boxes/actions not exported), show a confirm.

# Data pipeline for ML (lightweight now, scalable later)

* On **export**, write:

  * `session.json` (schema above)
  * `screens/0001.png`, `screens/0002.png`, …
* Also emit a **flattened CSV/JSONL** for quick training protos:

  * One record per action with: `session_id, screen_id, action_type, box_coords, params, pixel_center, pre_sha, post_sha`
* Keep a `rejected/` folder for runs that failed guardrails.

# Step-by-step next moves (do these in order)

## Phase A — Finish UI for sessions & next-screenshot

1. **Session model**: in the host UI, add `self.session = []`, each entry like the current export “screen” object.
2. **Add “New Screen” handler**: a method to append a new screen (called by the host when the VM agent posts a stable image).
3. **Viewer pill**: show a small `Gtk.Revealer` in the top-right of the screenshot widget with “Next screenshot ready” → on click: replace image, clear bottom lists, reset selection.
4. **Prev/Next controls**: small buttons under the viewer to navigate screens you’ve already accepted (for edits).

## Phase B — JSON Translator & Dry-run harness

5. **Define a `translate_to_pi_plan(session_json)`** that emits a flat list of low-level commands:

   * `move_abs(x,y,duration_ms)`, `click_left()`, `type("…")`, `scroll(lines_or_px)`
6. **Write a CLI**: `auroch-run --session path/to/session.json --dry-run --pi localhost:9999`

   * `--dry-run` prints the plan and renders a synthetic cursor trail on images (nice for demos).
7. **Guardrail check**: before each screen’s actions, verify current VM screenshot hash == expected (from JSON). If not, abort or prompt.

## Phase C — Minimal Reflex agent on VM

8. Implement a small headless app (whatever you’re already using) to:

   * Toggle `suppress_stability` via RPC.
   * Produce `FrameNotice` upon stability.
9. Host bridge:

   * A tiny receiver that writes `screens/NNNN.png` and notifies the UI.

## Phase D — End-to-end test (single screen)

10. Draw 1–2 boxes, add actions, export JSON, run the translator to the Pi in **dry-run**.
11. Flip to **live**: send to Pi, set `suppress_stability=true`, play actions, then `suppress_stability=false` to wait for next stable frame.

## Phase E — Multi-screen flow

12. Repeat Phase D across 2–3 screens. Verify session navigation & re-edits.
13. Validate exported **session.json** round-trips: reload into the UI and re-export is identical (hash compare).

## Phase F — Data logging for ML

14. Add per-action logging on host:

* The raw screenshot (pre), the box, the action, and the post screenshot id (if you want to tie cause→effect later).

15. Emit **JSONL**/CSV alongside session.json for quick stats & sanity checks.
16. Quick smoke ML: a dumb baseline (e.g., a small model that predicts click location given a crop + action type) just to validate data shape.

# Open questions / choices to lock

* **Box IDs per screen** vs. global IDs: I recommend **per screen**, reset each time. (Simpler; your translator uses local ids.)
* **Scroll units**: lock the unit (“-1” == \~100 px at current VM DPI). Add `vm.display_scale` to JSON and centralize conversion.
* **Placeholders vs. empty TYPE**: We chose to export empty string if user didn’t type anything (placeholder ignored). Good?
* **MOVE behavior**: always center-to-center unless explicitly overridden? (Current inference does that—reasonable.)
* **Guardrail mode**: on mismatch, do we block or allow “I know what I’m doing” override? (I’d block by default with a big red prompt.)

---

If you want, next I can:

* Add the **“Next screenshot ready” pill** code (small, surgical).
* Draft the **translator** function that consumes your current export and emits a very simple plan for your Pi runner (with clear extension points).
* Provide a **minimal VM stability detector** loop (Python or C#), whichever fits your environment.

Your system architecture looks solid. The plan above keeps complexity low now, but sets us up to evolve into the reflex/“improv” layer and ML without repainting the house later.








Alright—deep breath, fresh eyes. I re-read your README, the VM/host/Pi pipeline, and all the code you dropped (UI, `ScreenshotViewer`, `host_ui.py`, `handuz.py`, `run_full_test.py`, `hid_server.py`, `vm_send_screenshot.py`, `screenshot.proto`, the screenshot receiver, and `hid.sh`). Below is a tightened, “product-grade” README you can use as a base. It mirrors what you’ve built, makes the data shapes explicit, and lays out the next steps for the UI→data→execution loop and early ML/data capture.

---

# AUROCH — Human-in-the-Loop UI Automation with Physical HID Execution

AUROCH is a host-orchestrated, virtualized UI automation system that **executes actions as a real USB mouse & keyboard** using a Raspberry Pi HID gadget, collects **annotated screenshots**, and prepares **training data** for a future multimodal agent. The near-term goal is to close the loop: **annotate → generate plan → execute on VM → detect stability → capture next screenshot → repeat**. Longer-term, a **Reflex Agent** on the VM will locally handle simple reactive tasks (e.g., wait for spinner, basic sliders) to reduce latency and host round trips.

---

## High-Level Architecture

```
┌────────────┐      Protobuf/TCP      ┌─────────┐
│   VM(s)    │ ─────────────────────► │  Host   │
│ Ubuntu     │   screenshots          │(Control)│
│ 24.04      │ ◄────────────────────── │  UI+Brain
└────┬───────┘    “next screenshot”    └────┬────┘
     │   passthrough USB HID                 │ ZMQ REQ
     ▼                                        ▼
┌────────────┐        ZMQ REP            ┌──────────────┐
│ Raspberry  │ ◄──────────────────────── │  Humanizer   │
│   Pi (HID) │     action plans (JSON)   │ (host-side)  │
│  /dev/hidg0│ ──hid reports──────────►  └──────────────┘
│  /dev/hidg1│
└────────────┘
```

* **VM(s):** Identical clones built from `vm_template.xml`, Ubuntu 24.04, VirtIO disk/net, VGA/VNC graphics, USB Tablet for cursor sanity. A VirtIO-FS share connects `/mnt/host_share` for low-latency host↔guest file exchange when needed.
* **Host (UI + Brain):** GTK UI to draw regions, queue actions, and export a **UI JSON** that defines all steps. It also receives VM screenshots (Protobuf/TCP).
* **Pi (Hand):** USB gadget emulating a mouse + keyboard. Receives **action plans** (JSON) via ZMQ, translates them to HID reports to the VM.

---

## Key Components (current state)

### Host UI

* **File:** `~/auroch/host_ui.py`
* **Widget:** `~/auroch/gui/widgets/screenshot_viewer.py`
* **What it does:**

  * Displays latest VM screenshot.
  * Draws bounding boxes (auto-IDs, animated dashed border on selection).
  * Selection list (left) and Action queue (right) are **dedicated columns** (25/50/25 layout).
  * Middle column = action type radios (CLICK/TYPE/SCROLL/MOVE) and **param panel**:

    * **TYPE** uses a wide, scrollable `TextView` with placeholder (“type here…”).
  * Bottom row of middle column:

    * **Left**: “Delete Selection” (single-line button), enabled only when a region is selected.
    * **Right**: vertical stack: “Add to Queue”, “Remove from Queue”, “Export JSON”.
  * Auto-selects newest box after drawing (highlights it, enables “Add to Queue”). On deletion: clears selection, stops animation, disables “Add”.
  * Exports `auroch_actions_export.json`.

### Humanizer (Host → Pi Plan Generator)

* **File:** `handuz.py` (host)
* **What it does:** Converts **absolute targets** and action semantics into **low-level HID-ish steps**:

  * `REL_MOVE`, `PAUSE`, `MOUSE_BTN`, `KEY`, `SCROLL`
  * Human-like pathing via fractal detours, interpolation, and noise.
  * `generate_output(format=…)`: debugging log/plot or “pi\_command” strings (you currently send JSON plans instead).
* **Used by:** `run_full_test.py` to synthesize and send an action plan to the Pi.

### Host ↔ Pi Bridge

* **Sender:** `run_full_test.py` (host → ZMQ REQ)
* **Receiver/Executor:** `~/auroch_pi/hid_server.py` (Pi → ZMQ REP)
* **HID Gadget Setup:** `hid.sh` (Pi)
* **Plan format:** A JSON array of `[action_name, params]`, executed step-by-step into:

  * **Mouse:** `/dev/hidg0`  (4 bytes: buttons, dx, dy, wheel)
  * **Keyboard:** `/dev/hidg1` (8-byte 104-key report)

### VM ↔ Host Screenshots

* **VM Sender:** `vm_send_screenshot.py` → Protobuf (`screenshot.proto`) → length-prefixed TCP.
* **Host Receiver:** current minimal server that writes to `recv_screen.png` (or `recv_<name>`).
* **Near-term:** extend to a **stability detector** on VM and a **UI “Next screenshot ready”** nudge on host.

---

## Canonical Data Shapes

### 1) UI JSON (exported by Host UI)

The UI export must support **both**:

* Executable plan generation (via Humanizer).
* ML data capture (simplified action intent + regions + timing).

**Proposed schema:**

```json
{
  "metadata": {
    "session_id": "uuid-1234",
    "vm_name": "vm-test-001",
    "screenshot_ts": 1736123456789,
    "image_path": "gui/recv_screen.png",
    "screen_size": {"width": 1280, "height": 800},
    "tool_version": "ui-0.3.0"
  },
  "regions": [
    {"id": 0, "x": 100, "y": 200, "width": 160, "height": 40},
    {"id": 1, "x": 420, "y": 240, "width": 320, "height": 60}
  ],
  "actions": [
    {
      "id": 0,
      "type": "CLICK",
      "box_id": 0,
      "params": {"button": "Left"},
      "timestamp": 1736123456899
    },
    {
      "id": 1,
      "type": "TYPE",
      "box_id": 1,
      "params": {"text": "hello world"},
      "timestamp": 1736123457899
    },
    {
      "id": 2,
      "type": "SCROLL",
      "box_id": 1,
      "params": {"amount": "-20"},
      "timestamp": 1736123458899
    }
  ]
}
```

* `regions`: the on-screen annotated boxes (“Box N”)—**authoritative** for targets.
* `actions`: ordered queue with `box_id` linkage; each has action-specific `params`.
* `metadata`: ties outputs to VM session, original screenshot, and tool version.

**Notes**

* “MOVE” as an explicit UI action is optional—your pipeline already infers MOVE between CLICKs on different boxes by inserting a generated MOVE using centers of regions.
* All click positions for execution derive from the **region center** (or configurable target point within the box).

### 2) Plan JSON (host → Pi)

The plan sent to the Pi is intentionally simple (what `hid_server.py` executes):

```json
[
  ["REL_MOVE", [12, 5]],
  ["PAUSE", 0.021],
  ["MOUSE_BTN", ["LEFT", "press"]],
  ["PAUSE", 0.06],
  ["MOUSE_BTN", ["LEFT", "release"]],
  ["SCROLL", [-1]],
  ["KEY", [0x28, 0x00, "press"]],
  ["KEY", [0x00, 0x00, "release"]]
]
```

---

## Execution Flow (Phase 1–2)

1. **VM boot + passthrough Pi HID**

   * Clone/start with `auroch.sh`.
   * In virt-manager, passthrough the Pi device(s) (Logitech-ish IDs).
   * Optional: mount VirtIO-FS host share at `/mnt/host_share`.

2. **Pi setup**

   * `sudo bash -x hid.sh` (creates `/dev/hidg0`, `/dev/hidg1`).
   * `sudo /home/agar/mouse/bin/python3 hid_server.py` (ZMQ REP on `*:5555`).

3. **Host services**

   * Start **screenshot receiver** (TCP) on the host.
   * Start **Host UI** (`python host_ui.py`), which loads `gui/recv_screen.png`.

4. **Manual kick-off (for now)**

   * On VM: `python vm_send_screenshot.py` → host replaces `recv_screen.png` → UI updates.

5. **Annotate + Queue**

   * Draw one or more **regions** (left column shows “Box N”).
   * Pick **action** type (CLICK/TYPE/SCROLL/MOVE).
   * Enter params (button, text, amount). “Add to Queue”.
   * Export **UI JSON**.

6. **Translate + Execute**

   * A small translator (`ui_to_plan.py`) reads the UI JSON and builds a **Humanizer plan**, inserting MOVE(s) as needed using region centers, then sends to Pi via ZMQ, same as `run_full_test.py`.

7. **Reflex (v0 heuristic)**

   * After actions that imply visual change (SCROLL/CLICK/TYPING), VM agent runs a **stability window** (e.g., “last N hashes unchanged for 500ms”), then sends a **single** stabilized screenshot to host.
   * Host UI shows a subtle **“Next screenshot ready”** chip overlay; clicking it advances the viewer and **disables stabilization detection** while you annotate/edit.

---

## Reflex Agent (v0) — Minimal Spec (do this soon)

Goal: **Local latency hiding** on VM for common “wait until settled” cases, without ML.

* **Trigger:** Host sends an “action boundary” flag (or just assume after certain actions).
* **VM loop:**

  * Capture frames at \~5–10 FPS, compute a cheap hash (e.g., `xxhash` of downsampled grayscale).
  * If `hash` unchanged for **≥ T\_stable\_ms** (e.g., 500–800 ms), stop and send **one** screenshot to host.
* **Edge cases:** max wait (e.g., 15 s), bail and send “NOT\_STABLE” + last frame.
* **Optional heuristics:** detect spinner via small ROI motion energy; ignore caret blinks via frequent single-line diffs.

**Minimal API:** (use TCP or ZMQ)

* Host → VM: `MONITOR_FOR_STABILITY` (with timeout)
* VM → Host: `STABLE_READY` + screenshot (existing Protobuf)

---

## “Expectation Runner” (pre-ML heuristic, optional)

A way to **practice flows** across multiple screens without ML:

* Prepare a sequence of **expected states**: each step has:

  * One or more **reference crops** (regions that should match within tolerance),
  * A **tolerance** (`SSIM ≥ 0.85` or color histogram delta ≤ threshold),
  * The **action** to take next (from the UI JSON template).
* At runtime: for each step

  * VM captures a candidate stabilized screen, host computes similarity vs reference(s).
  * If match: proceed automatically with the queued action.
  * If mismatch: flag UI (“unexpected state”), pause, let human fix/skip/retrain.

This lets you dry-run deterministic flows before ML.

---

## UI ↔ Humanizer Mapping

| UI Action | Params                  | Target (from region)      | Humanizer calls                                |
| --------- | ----------------------- | ------------------------- | ---------------------------------------------- |
| CLICK     | `button` (“Left/Right”) | Center of `box_id`        | `move_to(cx, cy)` → `click(button)`            |
| TYPE      | `text`                  | Focus should be set first | (Optional preceding CLICK) → `type_text(text)` |
| SCROLL    | `amount` (±ticks)       | View at that time         | `scroll(amount)`                               |
| MOVE      | —                       | Center of `box_id`        | `move_to(cx, cy)`                              |

**Inference rule:** when two consecutive **CLICK** actions target different `box_id`s, insert a `MOVE` between centers. (You’re already doing this.)

---

## `ui_to_plan.py` (Translator) — Proposal

**Purpose:** Convert `auroch_actions_export.json` (UI JSON) → a **single plan** JSON (what the Pi expects). Also compatible with `handuz.Humanizer` for pathing realism.

**Steps:**

1. Load UI JSON.
2. Build a `box_id → center(x, y)` map.
3. For each action:

   * If it needs a location (`CLICK`, `MOVE`), `move_to(cx, cy)`.
   * Then apply semantics (`click(button)`, `type_text(text)`, `scroll(amount)`).
   * Insert intermediate `MOVE`s when needed (as you already do).
4. Dump `humanizer.action_plan` to JSON and send over ZMQ (or return it to caller).

*You can call this from a new `run_ui_plan.py` that points at a UI export file, so designers can go UI→execute without writing Python.*

---

## Setup & Runbook

### Raspberry Pi (once per boot)

```bash
sudo bash -x hid.sh
sudo /home/agar/mouse/bin/python3 ~/auroch_pi/hid_server.py
# Expect: "✅ Pi Executor is running. Waiting for a plan..."
```

### Host

```bash
# 1) Screenshot receiver (host)
python host_recv_screenshot.py

# 2) Host UI
python host_ui.py
# UI loads gui/recv_screen.png (ensure at least one VM screenshot has been sent)

# 3) (Temporary) translate & send
#   Option A: run_full_test.py (hardcoded sequence)
python run_full_test.py

#   Option B: (after we add) run_ui_plan.py path/to/auroch_actions_export.json
```

### VM (manual test)

```bash
python vm_send_screenshot.py
# Host should print "Saved to recv_screen.png"
# UI updates automatically (if reloading; otherwise reload image manually for now)
```

---

## Logging & Data Capture

* **Host UI export:** `auroch_actions_export.json` (contains regions + actions + tool metadata).
* **Pi execution logs:** console prints each plan step and raw HID bytes sent.
* **Humanizer logs:** `generate_output(format='human', log_file=...)` per step in `run_full_test.py`.
* **Screenshots:** host receives stabilized images as `recv_screen.png` (we’ll add chronological filenames and a session folder).

**Data for ML (minimum viable):**

* `(image_before, action_intent, region_bbox, action_params, image_after, timestamps)`
* We can derive this by pairing adjacent screenshots with the action that occurred between them, using the UI JSON ids & timestamps.

---

## Guardrails / Safety

* **Selection gating:** “Add to Queue” disabled unless a region is selected.
* **After delete:** selection cleared, animation stopped, add disabled.
* **Execution preflight:** (coming) ensure current screen hash still matches `image_path` hash embedded in UI JSON; warn if mismatch.
* **Scroll/Typing:** mark these as **“reflex required”** (i.e., wait for stabilization before allowing the next annotation).

---

## Known Constraints & Choices

* **VM GPU mode:** VGA/VNC is chosen for **stable HID cursor & debugging**.
* **Wayland screenshots:** using `gnome-screenshot`. Consider `grim`/`wf-recorder` alternatives if needed.
* **Throughput vs fidelity:** Only **before/after** screenshots are kept (your choice)—we skip intermediates to keep datasets lean.

---

## Roadmap (near-term)

### Phase 3a — Finalize UI JSON + Translator

* [ ] Freeze UI JSON schema (above).
* [ ] Add `ui_to_plan.py` to convert UI JSON → `Humanizer` → plan JSON.
* [ ] Add `run_ui_plan.py` to send a UI export end-to-end via ZMQ to Pi.

### Phase 3b — Stabilization & Host UI Nudge

* [ ] VM: add **stability monitor** loop (hash-based).
* [ ] Protocol: `MONITOR_FOR_STABILITY` request & timeout.
* [ ] Host UI: add **“Next screenshot ready”** chip; clicking replaces screenshot; disable detection during edits.

### Phase 4 — Data Logging Pass

* [ ] Create a **run session folder** (e.g., `runs/session_<timestamp>/`) with:

  * `image_000_before.png` / `image_001_after.png` …
  * `ui_export.json` (as-used)
  * `execution_plan.json` (flattened)
  * `events.jsonl` (timings, hashes, errors)

### Phase 5 — Heuristic “Expectation Runner”

* [ ] Define a `flow.json` with expected image features + tolerances per step.
* [ ] Implement a runner: compare stabilized screenshot vs expected; auto-advance or flag.

### Phase 6 — Dry-run Data Collection for ML

* [ ] Wedge a simple **action summarizer** (CLICK/TYPE/SCROLL only) for ML.
* [ ] Accumulate 100–1,000 labeled `(before, intent, bbox, params, after)` tuples.
* [ ] Validate data coverage (UI widgets, text fields, scrollables).

---

## Potential Improvements (nice wins)

* **systemd units** for Pi `hid_server.py` and `hid.sh` (post-boot).
* **Host screenshot service**: persistent, rotating filenames, session IDs.
* **UI affordances**: “Rename Box N”, duplicate region, quick target point (center vs top-left vs custom).
* **Click position sampling**: option to randomize within bbox; parameterize padding.
* **Hashing**: use `xxhash` on downsampled grayscale (e.g., 256×160) for stability; store in metadata.
* **Keyboard map**: finalize a complete US mapping + simple IME handling (enter/tab/esc combos).

---

## Glossary

* **Region / Box**: a user-drawn bounding box to ground an action.
* **Action**: CLICK/TYPE/SCROLL/MOVE + parameters + linked `box_id`.
* **Plan**: low-level list of steps the Pi executes (`REL_MOVE`, `PAUSE`, etc.).
* **Reflex**: on-VM heuristic to detect visual stability (no ML).

---

## Non-Goals (for now)

* Full OCR/CV on the VM.
* Continuous video logging.
* Robust visual diff beyond simple hashing/SSIM.
* Non-Ubuntu guest templates.

---

## FAQ-ish

**How heavy should the VM be?**
2 vCPU + 4GB RAM is fine for the reflex (hash-based). Sliders/puzzles handled reflexively might need very light CV later—but not now.

**Why not keep intermediate screenshots?**
We’re optimizing for “only relevant states” to train discrete step-transitions. We can always turn on verbose capture later for a subset of runs.

**Can actions run if the screen changed since annotation?**
Add a preflight check (hash of current vs `metadata.image_path`). If mismatch, warn & require re-annotation or “force”.

---

If you’re happy with this version, I’ll:

* Draft `ui_to_plan.py` (+ tiny `run_ui_plan.py`).
* Add the VM **stability monitor** loop + the host UI **“Next screenshot ready”** chip scaffolding.
* Wire the “session folder” logging so your first dry-run produces ML-ready tuples automatically.
