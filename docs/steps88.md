Heck yeah—let’s lock this down so we can move fast without breaking our brains later. Here’s a **specific, atomic plan** for this phase, in three parts: **spec**, **steps**, and **tests**.

---

# Phase Spec — What we will accomplish (and nothing more)

## Outcome

Close the loop from **annotated screenshot → executable plan on Pi → stabilized next screenshot → logged dataset tuple**. No ML yet—just clean data and a reliable pipeline.

## Deliverables

1. **UI JSON export (frozen schema)** including regions, actions, and metadata.
2. **Translator** `ui_to_plan.py` that converts UI JSON → `handuz.Humanizer` → **plan JSON**.
3. **Runner** `run_ui_plan.py` that sends a plan to the Pi (ZMQ REQ/REP), identical to `run_full_test.py` behavior.
4. **VM Stability Agent (v0)**: hash-based “wait until screen is stable” loop; sends one screenshot when stable (with timeout).
5. **Host Screenshot Receiver v2**: saves to per-session folders with sequential filenames and hashes.
6. **Session logging**: `runs/session_<ts>/` containing UI JSON, plan JSON, before/after screenshots, and events.
7. **Preflight safety**: warn if current screen hash doesn’t match the UI export’s `metadata.image_path` hash (stale annotations).
8. **Docs**: short runbook describing the above.

## Non-goals (defer)

* Fancy visual diff/SSIM. (We’ll start with downsampled grayscale + xxhash.)
* ML training or VLM inference.
* Expectation-runner automation (we’ll sketch it later, not implement in this phase).

---

# Atomic Steps — In the most rational order

## A. Freeze the data contracts

1. **Lock UI JSON schema** (regions, actions, metadata).

   * Add: `metadata.session_id`, `screen_size`, `image_hash`.
   * Store hash of `gui/recv_screen.png` at export time.
2. **Lock Plan JSON format** (the low-level array `[ [action, params], … ]`)—this already matches what `hid_server.py` expects.

## B. UI finish work (tiny)

3. **UI export bump**:

   * Include `image_hash` (compute on read with a tiny helper: load `recv_screen.png` → downsample → grayscale → xxhash).
   * Include `tool_version`.
   * Confirm **auto-select last drawn box** + button enable/disable states stay correct after our previous patches.
4. **UI: “Reload Screenshot” button (small)** to refresh the viewer if a new file arrives.

## C. Session structure (host)

5. **Create a `runs/` folder** on host.
6. **Session creator** (`session.py` tiny helper): `new_session()` returns `session_id` and path `runs/session_<ts>`.

## D. Host Screenshot Receiver v2

7. Replace current receiver with **v2**:

   * On first connection: create a session if none is active (or accept provided `session_id` header later—optional).
   * Save files as `image_000_before.png`, `image_001_after.png`, …
   * Compute and record `image_hash` (same method as UI) into `runs/.../events.jsonl`.
   * Expose latest image path for UI to load (`gui/recv_screen.png` can be a symlink to the latest).

## E. VM Stability Agent (v0)

8. **VM agent script** `vm_stability_agent.py`:

   * Loop at \~6–10 FPS: capture → downsample → grayscale → hash.
   * If hash unchanged for **T\_stable\_ms** (say, 700ms), send single screenshot to host and **stop**.
   * Timeout (e.g., 15s): send last frame with `stable=false`.
9. **Agent control**: either

   * Minimal: run agent continuously; it always sends the next stable frame on request marker (write a “trigger file” e.g., `/tmp/auroch_next.txt`). **or**
   * Better: add a tiny TCP/ZMQ listener on the VM for a `MONITOR_FOR_STABILITY` command.
     *(Pick one—start with the trigger file if you want zero netcode on VM.)*

## F. Translator & Runner

10. **`ui_to_plan.py`**:

    * Load UI JSON.
    * Map `box_id → center(x, y)`.
    * Walk actions in order:

      * `MOVE`/`CLICK` → `humanizer.move_to(cx, cy)`
      * `CLICK` → `humanizer.click(button)`
      * `TYPE` → `humanizer.type_text(text)`
      * `SCROLL` → `humanizer.scroll(amount)`
      * (Optional) Insert `MOVE` between consecutive clicks to different boxes (if the UI hasn’t already added an inferred one—guard against double insertion).
    * Dump `humanizer.action_plan` as **plan JSON**.
11. **`run_ui_plan.py`**:

    * Args: `--ui path/to/ui.json`, `--pi tcp://<ip>:5555`, `--session <id>` (optional)
    * Do **preflight**: compute current `gui/recv_screen.png` hash; compare with `ui.metadata.image_hash`. If mismatch, prompt `--force`.
    * Send plan JSON to Pi over ZMQ (REQ).
    * Log: `execution_plan.json` in session folder.
12. **Events logger**: helper to append to `events.jsonl` per step (`timestamp`, `type`, `detail`, `image_ix`, `hash`, `plan_len`, etc.).

## G. Orchestration glue (manual for now)

13. **Manual loop** we’ll use to test the whole chain:

    * VM: run `vm_stability_agent.py`.
    * Host: run screenshot receiver v2.
    * Host UI: annotate & export.
    * Host: `python run_ui_plan.py --ui runs/<session>/ui_export.json --pi tcp://PI:5555`.
    * VM agent: sends stabilized next screenshot; receiver stores `image_00X_after.png`.
    * UI: click “Reload Screenshot” to continue annotating next step.

## H. Logging completeness

14. In session folder, ensure we write:

    * `ui_export.json` (as-used)
    * `execution_plan.json` (as-executed)
    * `events.jsonl`
    * `image_***.png` (before/after pairs)
    * `hashes.json` (optional; or embed in events)

## I. Docs (small)

15. Add a **short** runbook to README: “Start VM, start Pi, start receiver, run VM agent, use UI → export → run → reload.”

---

# Tests — Clear acceptance criteria

## 1) UI/UX tests

* **Auto-select-on-draw**: Draw a box → left list highlights it; dashed animation starts; “Add to Queue” & “Delete Selection” become enabled.
  *Pass if states flip exactly once; no animation on unselected.*
* **Delete behavior**: Delete current selection → no box selected; no animation; “Add to Queue” disabled.
  *Pass if true and queue’s referencing actions are remapped/dropped as implemented.*
* **TYPE field**: Switch to TYPE → wide scrollable area appears with placeholder “type here…”. On focus-in, placeholder clears; on blur with empty, placeholder reappears.
  *Pass if placeholder never gets stored as real text.*

## 2) UI JSON content

* **Schema includes**: `metadata.session_id`, `image_hash`, `screen_size`, `regions`, `actions`.
* **Action params**: CLICK has `button`, TYPE has `text`, SCROLL has `amount` (string or int ok), MOVE no extra params.
  *Pass if JSON validates against our doc’ed schema and includes current hash.*

## 3) Translator → Plan unit tests

* **CLICK → move + click**: One CLICK on `box_id=0` yields `REL_MOVE` to center of box 0 followed by button press/release (with pauses).
* **Consecutive CLICK same box**: *No extra MOVE* inserted between them.
* **Consecutive CLICK different box**: Exactly one MOVE inserted between the two.
* **TYPE**: Produces only `KEY`/`PAUSE` events; no `REL_MOVE` unless a preceding CLICK or MOVE targeted the field.
* **SCROLL**: `amount < 0` → negative ticks; `amount > 0` → positive ticks.
  *Pass if generated plan matches expectations (we can assert action names and count; we don’t test Humanizer’s internal deltas).*

## 4) Pi execution smoke test

* Start `hid_server.py` (Pi).
* Send a tiny synthetic plan: `REL_MOVE(10,5)`, `PAUSE(0.05)`, `MOUSE_BTN(LEFT press/release)`
* Watch Pi logs and VM `evtest`:
  *Pass if correct events appear and cursor visibly twitches.*

## 5) Screenshot receiver v2

* Send two screenshots from VM.
* Verify: `runs/session_<ts>/image_000_before.png` and `image_001_after.png` exist, hashes recorded in `events.jsonl`.
  *Pass if filenames and hashes are correct and sequential.*

## 6) Stability agent

* On VM, run `vm_stability_agent.py`.
* Trigger monitoring (your chosen method).
* While moving a window *slightly*, ensure no “stable” is reported; after stop, “stable” sent within \~1s.
* With timeout case (hold constant motion), ensure timeout triggers and last frame is sent with `stable=false`.
  *Pass if timing behavior matches thresholds.*

## 7) Preflight safety

* Export UI JSON for `image_000_before.png`.
* Replace `recv_screen.png` with a different image and try `run_ui_plan.py` without `--force`.
  *Pass if it refuses with a clear message.*
* Rerun with `--force`.
  *Pass if it executes anyway.*

## 8) Session completeness

* After one full loop (annotate→run→stabilize→new screenshot), verify:

  * `ui_export.json` present
  * `execution_plan.json` present
  * `events.jsonl` has entries: `SCREEN_SAVED` (with hash), `PLAN_SENT` (with size), `STABLE_READY` (with duration)
    *Pass if all artifacts exist and timestamps are sensible.*

## 9) Edge cases

* **Empty TYPE text** (placeholder only): plan contains *no* `KEY` events.
* **Scroll zero/float**: coercion to at least one tick in correct direction.
* **Box deletion remap**: delete `Box 0` when actions reference `Box 1+`: all higher box ids shift down and the UI queue strings reflect “Box N” names correctly.
  *Pass if queue labels and `box_id`s are consistent.*

---

If you’re good with this, I’ll start by drafting:

* `hashing.py` (downsample+grayscale+xxhash helper)
* `ui_to_plan.py`
* `run_ui_plan.py`
* `host_recv_screenshot_v2.py` (session-aware)
* `vm_stability_agent.py` (trigger-file variant for simplicity)

Say the word and I’ll paste the first two files (translator + runner) so you can drop them in and try a small end-to-end.



Totally with you. We’ll move in **small, testable chunks**, keep the surface area minimal, and I’ll explain what each piece does before you run it.

### Today’s Step 1 (tiny + testable)

We’ll add two small files:

1. `hashing.py` — a tiny helper to compute a stable image hash (we’ll use it later for preflight checks and logging).
2. `ui_to_plan.py` — a translator that converts your UI export (`boxes` + `actions`) into a **Pi-ready plan JSON** using your existing `Humanizer`.

No UI changes yet, no ZMQ sending yet. Just: **UI JSON → plan JSON** with a clear CLI.

---

# 1) `hashing.py`

* Purpose: consistent image hashing you can reuse everywhere (UI export, receiver, preflight).
* Prefers Pillow for a *content* hash (grayscale + downsample → hash), but gracefully falls back to hashing the raw file bytes if Pillow isn’t installed.
* Hash algo: BLAKE2b (fast, strong). 16-byte digest → 32-hex string.

```python
# ~/auroch/hashing.py
import hashlib

try:
    from PIL import Image  # optional, nicer content-based hash
    _PIL_AVAILABLE = True
except Exception:
    _PIL_AVAILABLE = False


def blake2b_hex(data: bytes, digest_size: int = 16) -> str:
    """Return hex BLAKE2b over bytes (digest_size 1..64)."""
    h = hashlib.blake2b(data, digest_size=digest_size)
    return h.hexdigest()


def compute_bytes_hash(data: bytes, digest_size: int = 16) -> str:
    """Hash arbitrary bytes (used by screenshot receiver)."""
    return blake2b_hex(data, digest_size=digest_size)


def compute_image_hash(path: str, size: int = 128, digest_size: int = 16) -> str:
    """
    Stable image hash.
    If Pillow is installed: grayscale + resize to size×size → hash of pixels.
    Else: fallback to raw file hash.
    """
    if _PIL_AVAILABLE:
        try:
            with Image.open(path) as im:
                im = im.convert("L")               # grayscale
                im = im.resize((size, size))       # downsample
                return blake2b_hex(im.tobytes(), digest_size=digest_size)
        except Exception:
            pass  # fallback below

    # Fallback: hash raw file bytes
    with open(path, "rb") as f:
        return blake2b_hex(f.read(), digest_size=digest_size)
```

> If you *want* the nicer content hash, `pip install pillow` on the **host**. Otherwise it’ll just hash the file bytes — still fine for now.

---

# 2) `ui_to_plan.py`

* Purpose: read your **current UI export** (exact schema you’re already writing), produce a **plan JSON** consumable by your Pi (`hid_server.py`).
* Uses your `handuz.Humanizer` class as-is (moves, clicks, typing, scroll).
* Mapping rules (simple + predictable):

  * We always **move** to a target before a `CLICK`.
  * For `MOVE` actions: we use `act["to"]` if present, else center of `box_id`.
  * `TYPE` uses the text; placeholder never appears because your UI strips it.
  * `SCROLL` parses amount to integer ticks (down = negative).

```python
# ~/auroch/ui_to_plan.py
import argparse
import json
import os
from typing import Dict, List, Tuple, Any

# Your Humanizer (host side). Adjust the import if your file path differs.
from handuz import Humanizer


def _center_of_box(box: Dict[str, int]) -> Tuple[int, int]:
    """Return (cx, cy) center of a box dict: {x, y, width, height}."""
    cx = int(box["x"] + box["width"] // 2)
    cy = int(box["y"] + box["height"] // 2)
    return cx, cy


def _normalize_button(name: str) -> str:
    """Map UI button names to Humanizer button names."""
    if not name:
        return "LEFT"
    name = name.strip().lower()
    if name in ("left", "l"): return "LEFT"
    if name in ("right", "r"): return "RIGHT"
    if name in ("middle", "mid", "m"): return "MIDDLE"
    return "LEFT"


def _parse_scroll_amount(val: Any) -> int:
    """Coerce UI scroll amount (string/number) to int ticks."""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip()
    if s == "":
        return 0
    try:
        return int(float(s))
    except Exception:
        return 0


def translate_ui_to_plan(ui_json: Dict[str, Any]) -> List[Tuple[str, Any]]:
    """
    Convert UI export dict => Humanizer action plan list of (action, params).
    Does not send to Pi. Just returns the plan (list).
    """
    boxes: List[Dict[str, int]] = ui_json.get("boxes", [])
    actions: List[Dict[str, Any]] = ui_json.get("actions", [])

    # Build id->box dict for quick lookup
    id_to_box = {b["id"]: b for b in boxes if "id" in b}

    h = Humanizer()

    for act in actions:
        atype = act.get("type", "").upper()
        params = act.get("params", {}) or {}
        box_id = act.get("box_id", None)

        if atype == "MOVE":
            # Prefer explicit "to" pixel coords if present
            to_xy = act.get("to")
            if isinstance(to_xy, (list, tuple)) and len(to_xy) == 2:
                tx, ty = int(to_xy[0]), int(to_xy[1])
                h.move_to(tx, ty)
            elif box_id is not None and box_id in id_to_box:
                tx, ty = _center_of_box(id_to_box[box_id])
                h.move_to(tx, ty)
            # else ignore MOVE with unknown target

        elif atype == "CLICK":
            # Always move to the target region center, then click.
            if box_id is None or box_id not in id_to_box:
                # If no valid box, skip this click to be safe.
                continue
            tx, ty = _center_of_box(id_to_box[box_id])
            h.move_to(tx, ty)
            button = _normalize_button(params.get("button", "Left"))
            h.click(button)

        elif atype == "TYPE":
            text = params.get("text", "") or ""
            if text:
                h.type_text(text)

        elif atype == "SCROLL":
            amt = _parse_scroll_amount(params.get("amount", 0))
            if amt != 0:
                h.scroll(amt)

        else:
            # Unknown or unsupported types are skipped (safe default)
            pass

    # Return the low-level plan for saving or sending.
    return h.action_plan


def main():
    ap = argparse.ArgumentParser(description="Translate UI JSON -> execution plan JSON (no sending).")
    ap.add_argument("--ui", required=True, help="Path to UI export JSON (from Host UI).")
    ap.add_argument("--out", help="Path to write execution plan JSON. Defaults to <ui_dir>/execution_plan.json")
    ap.add_argument("--dry-run", action="store_true", help="If set, print a summary and do not write file.")
    args = ap.parse_args()

    with open(args.ui, "r") as f:
        ui_json = json.load(f)

    plan = translate_ui_to_plan(ui_json)

    # Simple summary
    counts = {}
    for action, _ in plan:
        counts[action] = counts.get(action, 0) + 1

    print("✅ Translation complete.")
    print(f"   Total steps: {len(plan)}")
    print("   Breakdown:")
    for k in sorted(counts):
        print(f"     - {k}: {counts[k]}")

    if args.dry_run:
        return

    out_path = args.out
    if not out_path:
        ui_dir = os.path.dirname(os.path.abspath(args.ui))
        out_path = os.path.join(ui_dir, "execution_plan.json")

    with open(out_path, "w") as f:
        json.dump(plan, f)
    print(f"📝 Wrote plan JSON: {out_path}")


if __name__ == "__main__":
    main()
```

---

## How to test this step

1. Save the two files:

* `~/auroch/hashing.py`
* `~/auroch/ui_to_plan.py`

2. Export from your **Host UI** as usual (that gives you `auroch_actions_export.json`).

3. Run the translator:

```bash
cd ~/auroch
python3 ui_to_plan.py --ui auroch_actions_export.json --dry-run
```

You should see a quick summary like:

```
✅ Translation complete.
   Total steps: 153
   Breakdown:
     - KEY: 42
     - MOUSE_BTN: 84
     - PAUSE: 26
     - REL_MOVE: 1
     - SCROLL: 0
```

4. If happy, write the plan JSON:

```bash
python3 ui_to_plan.py --ui auroch_actions_export.json --out runs/tmp/execution_plan.json
# (If --out omitted, it writes next to your UI JSON as execution_plan.json)
```

This plan JSON is exactly what your `hid_server.py` expects: a list of `["REL_MOVE", [dx,dy]]`, `["PAUSE", 0.12]`, `["MOUSE_BTN", ["LEFT","press"]]`, `["KEY", [code,mod,"press"]]`, etc.

---

## What’s coming next (after you confirm this works)

* **Step 2:** Add a tiny `run_ui_plan.py` to load the plan JSON and (optionally) send to the Pi. (We’ll include a `--send` flag and keep it safe by default.)
* **Step 3:** Wire in **preflight hash** with `hashing.compute_image_hash()` (warn on mismatch with the UI’s screenshot hash).
* **Step 4:** Sessionized screenshot receiver v2.
* **Step 5:** VM stability agent (trigger-file variant).

If anything in the translator feels off (e.g., you want different MOVE behavior), tell me and we’ll tune it *before* we start sending to the Pi.




