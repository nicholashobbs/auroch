# vm_ui_perception.py
# Minimal, fast perception on the VM: OCR (Tesseract) + simple CV heuristics.
# Public API: process_screenshot(image_path: str) -> dict (UI graph)

import cv2
import numpy as np
import pytesseract
import json
from typing import List, Tuple, Dict

# If your Tesseract binary is not on PATH, uncomment and set it explicitly:
# pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"


def _bbox(x: int, y: int, w: int, h: int) -> List[int]:
    return [int(x), int(y), int(x + w), int(y + h)]


def _merge_boxes(boxes: List[List[int]]) -> List[int]:
    if not boxes:
        return [0, 0, 0, 0]
    xs1 = [b[0] for b in boxes]
    ys1 = [b[1] for b in boxes]
    xs2 = [b[2] for b in boxes]
    ys2 = [b[3] for b in boxes]
    return [min(xs1), min(ys1), max(xs2), max(ys2)]


def _iou(a: List[int], b: List[int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, inter_x2 - inter_x1), max(0, inter_y2 - inter_y1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    return inter / float(area_a + area_b - inter + 1e-6)


def _gray(img_bgr):
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


def _resize_if_needed(img_bgr, max_w: int = 1600) -> Tuple[np.ndarray, float]:
    h, w = img_bgr.shape[:2]
    if w <= max_w:
        return img_bgr, 1.0
    scale = max_w / float(w)
    new_size = (int(w * scale), int(h * scale))
    return cv2.resize(img_bgr, new_size, interpolation=cv2.INTER_AREA), scale


def _ocr_words_and_lines(img_bgr) -> Tuple[List[Dict], List[Dict]]:
    """
    Returns:
      words: [{text, conf, bbox=[x1,y1,x2,y2]}]
      lines: [{text, conf_mean, bbox=[x1,y1,x2,y2]}]
    """
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    data = pytesseract.image_to_data(img_rgb, output_type=pytesseract.Output.DICT)

    N = len(data.get("text", []))
    words = []
    # Collect words with decent confidence
    for i in range(N):
        txt = (data["text"][i] or "").strip()
        try:
            conf = int(float(data["conf"][i]))
        except Exception:
            conf = -1
        if not txt or conf < 60:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        if w <= 0 or h <= 0:
            continue
        words.append({
            "text": txt,
            "conf": conf,
            "bbox": _bbox(x, y, w, h)
        })

    # Group into lines by (block_num, par_num, line_num)
    lines_map = {}
    for i in range(N):
        try:
            b = int(data["block_num"][i]); p = int(data["par_num"][i]); l = int(data["line_num"][i])
            key = (b, p, l)
        except Exception:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        txt = (data["text"][i] or "").strip()
        try:
            conf = int(float(data["conf"][i]))
        except Exception:
            conf = -1
        if w <= 0 or h <= 0:
            continue
        if key not in lines_map:
            lines_map[key] = {"boxes": [], "texts": [], "confs": []}
        lines_map[key]["boxes"].append(_bbox(x, y, w, h))
        if txt:
            lines_map[key]["texts"].append(txt)
        if conf >= 0:
            lines_map[key]["confs"].append(conf)

    lines = []
    for key, v in lines_map.items():
        merged = _merge_boxes(v["boxes"])
        text = " ".join(v["texts"]).strip()
        conf_mean = float(np.mean(v["confs"])) if v["confs"] else 0.0
        lines.append({
            "text": text,
            "conf": conf_mean,
            "bbox": merged
        })

    return words, lines


def _find_rect_like_contours(img_bgr) -> List[List[int]]:
    """
    Generic rectangular region proposals (containers). Axis-aligned AABBs.
    """
    gray = _gray(img_bgr)
    # Edge + close to group edges
    edges = cv2.Canny(gray, 80, 160)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = gray.shape[:2]
    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if w < 20 or h < 16:
            continue
        if area < 500:  # reject tiny
            continue
        if area > 0.9 * W * H:  # reject near full screen
            continue
        boxes.append(_bbox(x, y, w, h))
    return boxes


def _mean_color(img_bgr, box: List[int]) -> Tuple[float, float, float]:
    x1, y1, x2, y2 = box
    x1 = max(0, x1); y1 = max(0, y1)
    x2 = min(img_bgr.shape[1], x2); y2 = min(img_bgr.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return (0.0, 0.0, 0.0)
    roi = img_bgr[y1:y2, x1:x2]
    b, g, r = cv2.mean(roi)[:3]
    return (b, g, r)


def _classify_inputs(img_bgr, candidates: List[List[int]]) -> List[List[int]]:
    """
    Very simple input heuristics:
    - Aspect ratio w/h typically > 2.
    - Interior fairly bright.
    - Border-ish edges around.
    """
    gray = _gray(img_bgr)
    inputs = []
    for box in candidates:
        x1, y1, x2, y2 = box
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            continue
        if w / float(h) < 2.0:
            continue
        roi = gray[y1:y2, x1:x2]
        if roi.size == 0:
            continue
        m = float(np.mean(roi))
        if m < 140:  # expect inputs to be light
            continue
        # quick border check: stronger edges near border than center
        edges = cv2.Canny(roi, 60, 120)
        border = np.hstack([
            edges[0:2, :].flatten(), edges[-2:, :].flatten(),
            edges[:, 0:2].flatten(), edges[:, -2:].flatten()
        ])
        if np.mean(border) < 8.0:  # not much border signal
            continue
        inputs.append(box)
    return inputs


def _classify_buttons(img_bgr, candidates: List[List[int]], ocr_lines: List[Dict]) -> List[List[int]]:
    """
    Button heuristics:
    - Moderate size, aspect ratio between ~1.2 and ~6.
    - Not extremely bright (to avoid input fields), not extremely dark.
    - Overlaps some OCR line (text on the button).
    """
    gray = _gray(img_bgr)
    H, W = gray.shape[:2]
    buttons = []
    for box in candidates:
        x1, y1, x2, y2 = box
        w, h = x2 - x1, y2 - y1
        if w <= 0 or h <= 0:
            continue
        area = w * h
        if area < 800 or area > 0.15 * W * H:
            continue
        ar = w / float(h)
        if ar < 1.2 or ar > 6.5:
            continue
        roi = gray[y1:y2, x1:x2]
        if roi.size == 0:
            continue
        m = float(np.mean(roi))
        if not (90 <= m <= 210):
            continue
        # Needs some text overlapping
        has_text = False
        for ln in ocr_lines:
            if _iou(box, ln["bbox"]) > 0.25:
                has_text = True
                break
        if not has_text:
            continue
        buttons.append(box)
    return buttons


def _classify_links(img_bgr, ocr_words: List[Dict]) -> List[List[int]]:
    """
    Link-like heuristics (textual):
    - Use per-word color; blueish words are likely links.
    """
    links = []
    for w in ocr_words:
        box = w["bbox"]
        b, g, r = _mean_color(img_bgr, box)
        # simple blue-ish rule
        if b > g + 10 and b > r + 20 and b > 90:
            links.append(box)
    return links


def process_screenshot(image_path: str) -> Dict:
    """
    Build a minimal UI graph for the given screenshot path.
    Schema:
    {
      "image_size": {"w": W, "h": H},
      "viewport": {"bbox": [x1,y1,x2,y2], "confidence": float},
      "containers": [{"bbox":[...], "kind":"rect"}],
      "elements": [{"id": "e1", "role":"input|button|link_like", "bbox":[...], "score":float}],
      "ocr": {
         "words":[{"text":str,"conf":int,"bbox":[...]}],
         "lines":[{"text":str,"conf":float,"bbox":[...]}]
      }
    }
    """
    img_bgr = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img_bgr is None:
        return {}

    # Optional resize for speed, then map back to original coords
    img_proc, scale = _resize_if_needed(img_bgr, max_w=1600)
    Hs, Ws = img_proc.shape[:2]
    H, W = img_bgr.shape[:2]

    def up(b):
        # map scaled box back to original coords
        x1, y1, x2, y2 = b
        if scale == 1.0:
            return [int(x1), int(y1), int(x2), int(y2)]
        return [int(x1 / scale), int(y1 / scale), int(x2 / scale), int(y2 / scale)]

    # OCR
    words_s, lines_s = _ocr_words_and_lines(img_proc)

    # Rect-like proposals (containers)
    conts_s = _find_rect_like_contours(img_proc)

    # Inputs, Buttons, Links
    inputs_s  = _classify_inputs(img_proc, conts_s)
    buttons_s = _classify_buttons(img_proc, conts_s, lines_s)
    links_s   = _classify_links(img_proc, words_s)

    # De-duplicate overlapping between roles a bit (inputs vs buttons)
    # If IoU > 0.5, prefer 'input' over 'button'
    kept_buttons = []
    for b in buttons_s:
        if all(_iou(b, i) <= 0.5 for i in inputs_s):
            kept_buttons.append(b)
    buttons_s = kept_buttons

    # Assemble graph
    graph = {
        "image_size": {"w": int(W), "h": int(H)},
        "viewport": {"bbox": [0, 0, int(W), int(H)], "confidence": 0.5},
        "containers": [{"bbox": up(b), "kind": "rect"} for b in conts_s],
        "elements": [],
        "ocr": {
            "words": [{"text": w["text"], "conf": int(w["conf"]), "bbox": up(w["bbox"])} for w in words_s],
            "lines": [{"text": l["text"], "conf": float(l["conf"]), "bbox": up(l["bbox"])} for l in lines_s],
        }
    }

    eid = 0
    for b in inputs_s:
        graph["elements"].append({"id": f"e{eid}", "role": "input", "bbox": up(b), "score": 0.6}); eid += 1
    for b in buttons_s:
        graph["elements"].append({"id": f"e{eid}", "role": "button", "bbox": up(b), "score": 0.6}); eid += 1
    for b in links_s:
        graph["elements"].append({"id": f"e{eid}", "role": "link_like", "bbox": up(b), "score": 0.6}); eid += 1

    return graph


if __name__ == "__main__":
    # Optional quick test:
    # python3 vm_ui_perception.py /path/to/image.png
    import sys
    if len(sys.argv) >= 2:
        g = process_screenshot(sys.argv[1])
        print(json.dumps(g)[:2000])
    else:
        print("Usage: python3 vm_ui_perception.py /path/to/screenshot.png")
