# ~/auroch/run_plan.py
import argparse, json, time, zmq, random
from pathlib import Path
from handuz import Humanizer
from datetime import datetime
import sys

def ts_now():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def _normalize_type_text(s: str) -> str:
    """
    Convert UI tokens into keystrokes that Humanizer understands.
    Currently: {ENTER} -> newline (Humanizer.type_text() sends Enter for '\n').
    """
    return (s or "").replace("{ENTER}", "\n")

def _box_center(box):
    return (box['x'] + box['width'] // 2, box['y'] + box['height'] // 2)

def build_and_run(plan_path: Path, pi_ip: str, logs_dir: Path, dry_run: bool=False):
    if not plan_path.exists():
        print(f"[ERROR] Plan not found: {plan_path}")
        sys.exit(2)

    try:
        with open(plan_path, "r") as f:
            obj = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read plan: {e}")
        sys.exit(2)

    # Enforce the single expected schema
    if not (isinstance(obj, dict) and "boxes" in obj and "actions" in obj):
        print("[ERROR] Expected plan format: { 'boxes': [...], 'actions': [...] }")
        sys.exit(2)

    boxes = obj["boxes"]
    actions = obj["actions"]

    # --- (2) Random point within a box (avoid repeating last point per box) ---
    last_point_by_box = {}  # box_id -> (x,y)

    def rand_point_in_box(box_id: int):
        b = boxes[box_id]
        x0, y0, w, h = int(b['x']), int(b['y']), int(b['width']), int(b['height'])
        # Guard tiny/invalid sizes
        if w < 1 or h < 1:
            pt = (x0, y0)
            last_point_by_box[box_id] = pt
            return pt

        prev = last_point_by_box.get(box_id)
        # Try a few times to avoid repeating the exact same point
        for _ in range(6):
            x = random.randint(x0, x0 + w - 1)
            y = random.randint(y0, y0 + h - 1)
            pt = (x, y)
            if pt != prev:
                last_point_by_box[box_id] = pt
                return pt
        # Fallback: nudge 1px horizontally if possible
        if prev:
            x = min(x0 + w - 1, max(x0, prev[0] + (1 if prev[0] < x0 + w - 1 else -1)))
            y = prev[1]
            pt = (x, y)
        else:
            pt = (x0, y0)
        last_point_by_box[box_id] = pt
        return pt

    # Expand to low-level HID actions via Humanizer
    h = Humanizer()
    final_actions = []

    def flush_h():
        nonlocal final_actions
        if h.action_plan:
            final_actions.extend(h.action_plan)
            h.clear_plan()

    for idx, act in enumerate(actions):
        atype   = act.get("type")
        box_id  = act.get("box_id")
        params  = act.get("params", {}) or {}

        if atype == "WAKE":
            h.wake_up_screen(); flush_h()

        elif atype == "WAIT":
            try:
                secs = float(params.get("seconds", 0) or 0)
            except Exception:
                secs = 0.0
            final_actions.append(["PAUSE", secs])

        elif atype == "MOVE":
            if box_id is None or not (0 <= box_id < len(boxes)):
                print(f"[WARN] MOVE missing/invalid box_id at step {idx}; skipping")
                continue
            x, y = rand_point_in_box(box_id)
            h.move_to(x, y); flush_h()

        elif atype == "CLICK":
            if box_id is None or not (0 <= box_id < len(boxes)):
                print(f"[WARN] CLICK missing/invalid box_id at step {idx}; skipping")
                continue
            # Always move to a random point in the target box, then click.
            x, y = rand_point_in_box(box_id)
            h.move_to(x, y); flush_h()

            btn = (params.get("button") or "Left").upper()
            btn = {"LEFT":"LEFT","RIGHT":"RIGHT","MIDDLE":"MIDDLE"}.get(btn, "LEFT")
            h.click(btn); flush_h()

        elif atype == "TYPE":
            text = _normalize_type_text(params.get("text",""))
            h.type_text(text); flush_h()

        elif atype == "SCROLL":
            amt_raw = params.get("amount", 0)
            try:
                amt = int(amt_raw)
            except Exception:
                amt = int(str(amt_raw).strip() or 0)
            h.scroll(amt); flush_h()

        else:
            print(f"[WARN] Unknown action type '{atype}' at step {idx}; skipping")

    # --- (5) Log exactly what we wrote, and print a CREATED: line the UI can surface ---
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_log = logs_dir / f"sent_plan_{ts_now()}.json"
    with open(out_log, 'w') as f:
        json.dump(final_actions, f, indent=2)
    print(f"CREATED: {out_log}")  # <-- Rust UI will surface these lines
    print(f"--> Wrote low-level plan to {out_log}  (len={len(final_actions)})")

    if dry_run:
        print("-- DRY RUN -- not sending to Pi.")
        return

    # Send to Pi
    context = zmq.Context()
    sock = context.socket(zmq.REQ)
    sock.connect(f"tcp://{pi_ip}:5555")
    print(f"--> Connected to Pi at {pi_ip}:5555")

    sock.send_string(json.dumps(final_actions))
    reply = sock.recv_string()
    print(f"<-- Pi replied: '{reply}'")

def main():
    ap = argparse.ArgumentParser(description="Execute a UI export plan with the Humanizer and send to Pi.")
    ap.add_argument("--plan", required=True, help="Path to plan JSON (exact schema: {boxes, actions})")
    ap.add_argument("--pi", required=True, help="Pi IP address (e.g., 192.168.1.214)")
    ap.add_argument("--logs", default="runs/logs", help="Directory for sent plan logs")
    ap.add_argument("--dry-run", action="store_true", help="Build only; do not send to Pi")
    args = ap.parse_args()

    build_and_run(Path(args.plan), args.pi, Path(args.logs), dry_run=args.dry_run)

if __name__ == "__main__":
    main()
