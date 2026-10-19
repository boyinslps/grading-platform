"""白板照片 → 座號：本機離線辨識（RapidOCR / PP-OCR，ONNX Runtime，CPU），不連網、不送任何 LLM。

用法：ocr-runtime\\python.exe ocr_rapid.py 圖片路徑      （由 server.py 的 /api/chair-ocr 呼叫）
輸出（stdout，一行 JSON）：
  {ok, engine, width, height, seconds,
   items:[{n, score, raw, box:[x,y,w,h], uncertain, why}],   # 每個座號一筆，box 是原圖座標
   hints:[{grade, className, raw}],                            # 白板上若寫了班級（401／4年1班）
   lines:[原始辨識文字]}
做法：偵測文字行 → 拉正 → 連通元件找出號碼之間的空隙 → 每一組單獨再辨識一次（避免相鄰座號黏成一串，如 12 25 18 → 122518）。
座號最多兩位：若切出三位以上，就用更小的間距重切。看起來像字母的（q→9、o→0…）會校正並標 uncertain，交給老師確認。
"""
import json
import logging
import re
import sys
import time

import cv2
import numpy as np

logging.disable(logging.CRITICAL)
from rapidocr import RapidOCR  # noqa: E402

CONFUSE = {'o': '0', 'O': '0', 'D': '0', 'l': '1', 'I': '1', '|': '1', 'i': '1', 'Z': '2', 'z': '2', 'S': '5', 's': '5',
           'b': '6', 'G': '6', 'T': '7', 'B': '8', 'q': '9', 'g': '9', 'a': '9'}
GAP_TRIES = [0.6, 0.45, 0.3, 0.2, 0.12]
MAX_EDGE = 3000
LOW_SCORE = 0.9


def order_pts(p):
    p = np.array(p, dtype="float32")
    s, d = p.sum(1), np.diff(p, axis=1).ravel()
    return np.array([p[s.argmin()], p[d.argmin()], p[s.argmax()], p[d.argmax()]], dtype="float32")


def warp(img, box):
    tl, tr, br, bl = order_pts(box)
    w = max(8, int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))))
    h = max(8, int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))))
    src = np.array([tl, tr, br, bl], dtype="float32")
    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype="float32")
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE), np.linalg.inv(m)


def ink_mask(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    k = max(15, (min(g.shape) // 2) | 1)
    bg = cv2.morphologyEx(g, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    flat = cv2.divide(g, bg, scale=255)
    _, m = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def groups(mask, gap_ratio):
    """連通元件分群：元件間水平空隙 > gap_ratio × 元件中位高度 → 不同號碼（不受每個數字各自歪斜影響）。"""
    n, _lab, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    comps = [(int(st[i, 0]), int(st[i, 0] + st[i, 2] - 1), int(st[i, 3])) for i in range(1, n)
             if st[i, 4] >= 0.01 * mask.shape[0] ** 2]
    if not comps:
        return []
    comps.sort()
    thr = gap_ratio * float(np.median([c[2] for c in comps]))
    out = [[comps[0][0], comps[0][1]]]
    for left, right, _h in comps[1:]:
        if left - out[-1][1] > thr:
            out.append([left, right])
        else:
            out[-1][1] = max(out[-1][1], right)
    return [tuple(g) for g in out]


def fix_digits(s):
    fixed = ''.join(CONFUSE.get(c, c) for c in s)
    return re.sub(r"\D", "", fixed), fixed != s and bool(re.sub(r"\D", "", fixed))


def to_box(inv, x0, x1, h):
    pts = np.array([[[x0, 0], [x1, 0], [x1, h], [x0, h]]], dtype="float32")
    o = cv2.perspectiveTransform(pts, inv)[0]
    x, y = o[:, 0].min(), o[:, 1].min()
    return [int(x), int(y), int(o[:, 0].max() - x), int(o[:, 1].max() - y)]


def main(path):
    t0 = time.time()
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return {"ok": False, "error": "讀不到這張圖片（格式不支援？）"}
    scale = 1.0
    if max(img.shape[:2]) > MAX_EDGE:
        scale = MAX_EDGE / max(img.shape[:2])
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    eng = RapidOCR()
    r = eng(img, use_det=True, use_cls=False, use_rec=True)
    items, hints, lines = [], [], []
    boxes = list(r.boxes) if r.boxes is not None else []
    for box, txt, sc in zip(boxes, list(r.txts or []), list(r.scores or [])):
        lines.append(txt)
        m = re.search(r"([1-6])\s*年\s*(\d{1,2})\s*班", txt)
        if m:
            hints.append({"grade": int(m.group(1)), "className": int(m.group(2)), "raw": txt})
        if not re.search(r"[0-9]", txt) and not re.fullmatch(r"[A-Za-z|]{1,2}", txt):
            continue
        crop, inv = warp(img, box)
        mask = ink_mask(crop)
        best, used = None, None
        for gr in GAP_TRIES:
            gs = groups(mask, gr)
            if len(gs) <= 1:
                cand = [(txt, float(sc), 0, crop.shape[1] - 1)]
            else:
                cand = []
                pad = int(0.2 * crop.shape[0])
                for a, b in gs:
                    sub = crop[:, max(0, a - pad): b + pad + 1]
                    rr = eng(sub, use_det=False, use_cls=False, use_rec=True)
                    if rr.txts:
                        cand.append((rr.txts[0], float(rr.scores[0]), a, b))
            best, used = cand, gr
            if all(len(fix_digits(t)[0]) <= 2 for t, _s, _a, _b in cand):
                break
        for t, s, a, b in best:
            digits, fixed = fix_digits(t)
            if not digits:
                continue
            why = []
            if fixed:
                why.append("字形像「%s」，已當成數字" % t)
            if s < LOW_SCORE:
                why.append("信心偏低 %.2f" % s)
            if len(digits) > 2:
                why.append("超過兩位數，可能黏在一起")
            n = int(digits)
            if len(digits) == 3 and re.fullmatch(r"[1-6]\d{2}", digits) and not fixed:
                hints.append({"grade": int(digits[0]), "className": int(digits[1:]), "raw": t})
                continue
            items.append({"n": n, "score": round(s, 3), "raw": t, "box": [int(v / scale) for v in to_box(inv, a, b, crop.shape[0])],
                          "uncertain": bool(why), "why": "；".join(why)})
    return {"ok": True, "engine": "rapidocr", "width": int(img.shape[1] / scale), "height": int(img.shape[0] / scale),
            "seconds": round(time.time() - t0, 1), "items": items, "hints": hints, "lines": lines}


if __name__ == "__main__":
    try:
        out = main(sys.argv[1])
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "error": str(e)[:300]}
    sys.stdout.buffer.write((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
