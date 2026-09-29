# -*- coding: utf-8 -*-
"""
評分平台 · 本機伺服器（獨立專案，port 8780）

服務本資料夾的靜態檔（teacher.html / student-submit.js / worksheets.json …），
並且**自帶一份 Google Classroom 授權與 AI 評分後端**，讓評分平台不必依賴「工作台」
（8770）就能獨立運作——設定存在本資料夾自己的 config.json，跟工作台的設定各自獨立。
"""
import json, re, io, sys, math, base64, zipfile, mimetypes, unicodedata, urllib.request, urllib.parse, time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 隨附的可攜式 Python 用 ._pth 鎖死 sys.path（只有直譯器自己那個資料夾，不含這個腳本的資料夾），
# import updater 在這種環境下預設會找不到模組——先把腳本自己的資料夾加進 sys.path。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import updater   # 自動更新（見 updater.py／《自動更新規範》）

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.json"
PORT = 8780
REDIRECT_URI = f"http://127.0.0.1:{PORT}/oauth/callback"
GOOGLE_SCOPES = " ".join([
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.announcements",   # 繳交紀錄「發布缺交名單」（2026-09-29 加，舊授權要重新授權一次）
])


def read_config():
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text("utf-8"))
        except Exception:
            pass
    return {}


def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")


# ========== 課表（存本資料夾的 timetable.json，跟含金鑰的 config.json 分開）==========
TIMETABLE = HERE / "timetable.json"
DEFAULT_PERIODS = [
    {"no": 1, "start": "08:45", "end": "09:25"},
    {"no": 2, "start": "09:35", "end": "10:15"},
    {"no": 3, "start": "10:30", "end": "11:10"},
    {"no": 4, "start": "11:20", "end": "12:00"},
    {"no": 5, "start": "13:40", "end": "14:20"},
    {"no": 6, "start": "14:30", "end": "15:10"},
    {"no": 7, "start": "15:20", "end": "16:00"},
]
_SLOT_KEY = re.compile(r"^[1-7]-([1-9]|1[0-2])$")


def _hhmm(v):
    """正規化成 HH:MM；「9:30」這種單位數小時補成「09:30」（否則字串比大小會錯），格式不對回空字串。"""
    t = str(v or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", t)
    if not m:
        return ""
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return ""
    return f"{h:02d}:{mi:02d}"


def _clean_periods(arr):
    """只留形狀正確的節次（no 1–12、start/end 是 HH:MM），壞掉的整筆丟掉而不是塞預設值——
    課表是老師自己填的，靜靜補一個假時間會讓「現在第幾節」算錯，不如讓那節消失看得出來。"""
    out = []
    for it in (arr or []):
        if not isinstance(it, dict):
            continue
        try:
            no = int(it.get("no"))
        except Exception:
            continue
        st, en = _hhmm(it.get("start")), _hhmm(it.get("end"))
        if not (1 <= no <= 12) or not st or not en or en <= st:
            continue
        out.append({"no": no, "start": st, "end": en})
    out.sort(key=lambda x: x["no"])
    seen, uniq = set(), []
    for it in out:
        if it["no"] in seen:
            continue
        seen.add(it["no"]); uniq.append(it)
    return uniq


def read_timetable():
    """{periods:[{no,start,end}], slots:{"{星期1-5}-{節次}": 班級id}, currentWs:{班級id: 學習單id}, updatedAt}"""
    data = {}
    if TIMETABLE.exists():
        try:
            data = json.loads(TIMETABLE.read_text("utf-8"))
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    periods = _clean_periods(data.get("periods")) or [dict(x) for x in DEFAULT_PERIODS]
    slots = {k: str(v) for k, v in (data.get("slots") or {}).items()
             if _SLOT_KEY.match(str(k)) and str(v or "").strip()}
    cur = {str(k): str(v) for k, v in (data.get("currentWs") or {}).items() if str(v or "").strip()}
    return {"periods": periods, "slots": slots, "currentWs": cur,
            "updatedAt": data.get("updatedAt") or 0}


def save_timetable(data):
    tt = {
        "periods": _clean_periods((data or {}).get("periods")) or [dict(x) for x in DEFAULT_PERIODS],
        "slots": {str(k): str(v) for k, v in ((data or {}).get("slots") or {}).items()
                  if _SLOT_KEY.match(str(k)) and str(v or "").strip()},
        "currentWs": {str(k): str(v) for k, v in ((data or {}).get("currentWs") or {}).items()
                      if str(v or "").strip()},
        "updatedAt": time.time(),
    }
    TIMETABLE.write_text(json.dumps(tt, ensure_ascii=False, indent=2), "utf-8")
    return {"ok": True, "timetable": tt}

# ========== AI 評分（openai 相容聊天補全；見《AI串接窗口設定規範》）==========
def _bad_header_chars(*vals):
    """API Key/端點/模型這些會被塞進 HTTP header 的欄位，含中文等非 latin-1 字元會讓 urllib 在送出當下
    直接丟 UnicodeEncodeError（訊息長得像『latin-1' codec can't encode...』，老師看了完全看不懂哪裡壞了）。
    先在呼叫前檢查、給一句看得懂的錯誤，好過讓例外炸到深層 http.client 才被籠統的 except Exception 接住。"""
    return any(not all(ord(c) < 256 for c in (v or "")) for v in vals)


def _llm_call(provider, key, model, endpoint, prompt):
    provider = (provider or "openai").lower()
    key = (key or "").strip(); model = (model or "").strip(); endpoint = (endpoint or "").strip()
    if not key:
        return {"ok": False, "error": "尚未填 API Key"}
    if _bad_header_chars(key, model):
        return {"ok": False, "error": "API Key 或模型名稱含不支援的字元（可能不小心貼到別的文字），請到「設定→AI 評分」重新貼上正確的 API Key。"}
    try:
        if provider.startswith("gemini"):
            base = endpoint if endpoint else "https://generativelanguage.googleapis.com/v1beta"
            url = base.rstrip("/") + f"/models/{model or 'gemini-2.0-flash'}:generateContent?key={urllib.parse.quote(key)}"
            body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            return {"ok": True, "text": data["candidates"][0]["content"]["parts"][0]["text"]}
        if not endpoint:
            return {"ok": False, "error": "OpenAI 相容模式需填『端點 URL』（反向代理，通常結尾 /v1）"}
        url = endpoint.rstrip("/") + "/chat/completions"
        body = json.dumps({"model": model or "gpt-4o-mini",
                           "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        return {"ok": True, "text": data["choices"][0]["message"]["content"]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _llm_models(provider, key, endpoint):
    provider = (provider or "openai").lower(); key = (key or "").strip(); endpoint = (endpoint or "").strip()
    if not key:
        return {"ok": False, "error": "尚未填 API Key"}
    if _bad_header_chars(key):
        return {"ok": False, "error": "API Key 含不支援的字元（可能不小心貼到別的文字），請重新貼上正確的 API Key。"}
    try:
        if provider.startswith("gemini"):
            base = endpoint if endpoint else "https://generativelanguage.googleapis.com/v1beta"
            url = base.rstrip("/") + f"/models?key={urllib.parse.quote(key)}"
            req = urllib.request.Request(url, headers={"User-Agent": "gradingPlatform"})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = json.loads(r.read().decode("utf-8"))
            models = [m.get("name", "").split("/")[-1] for m in data.get("models", [])
                      if "generateContent" in (m.get("supportedGenerationMethods") or [])]
        else:
            if not endpoint:
                return {"ok": False, "error": "OpenAI 相容模式需填『端點 URL』（通常結尾 /v1）"}
            url = endpoint.rstrip("/") + "/models"
            req = urllib.request.Request(url, headers={
                "User-Agent": "gradingPlatform", "Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = json.loads(r.read().decode("utf-8"))
            models = [m.get("id", "") for m in data.get("data", [])]
        models = sorted(set(x for x in models if x))
        return {"ok": True, "models": models}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def grade_call(prompt):
    c = read_config()
    return _llm_call(c.get("grade_provider") or "openai", c.get("grade_key"), c.get("grade_model"), c.get("grade_endpoint"), prompt)


def grade_models():
    c = read_config()
    return _llm_models(c.get("grade_provider") or "openai", c.get("grade_key"), c.get("grade_endpoint"))


def fetch_title(url):
    if not url:
        return {"ok": False, "error": "缺 url"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 gradingPlatform"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read(60000).decode("utf-8", "replace")
        m = re.search(r'<title[^>]*>(.*?)</title>', raw, re.S | re.I)
        import html as _html
        return {"ok": True, "title": _html.unescape(m.group(1).strip())[:80] if m else ""}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _norm(v):
    if isinstance(v, list):
        return sorted(_norm(x) for x in v)
    return str(v).strip().lower()


# ========== AI 評分（通用引擎；規範見 ../引導規範/AI評分規範.md）==========
# 每一題開放題有自己的「題目規格」（題幹＋評分方式＋標準＋配分，存在 worksheets/{id}.questions）。
# AI 只負責「判斷」，分數一律由伺服器依規格計算，所以：
#   - 每題得分不可能超過該題配分；開放題總分＝各題加總（不是平均）。
#   - 同一題裡正規化後相同的作答只送一次、必得同分。
# 三種評分方式：
#   condition 條件查核：學生列出 N 個項目，AI 只回答每個項目符不符合條件；判定結果存成「判定紀錄」，
#                      之後任何班級遇到同一個項目直接沿用，老師改一次就全部套用。
#   checklist 檢核點：AI 逐項判斷有沒有做到（要附學生原文當證據），分數＝做到的檢核點配分加總。
#   levels    分級：AI 給 0～4 級，分數＝配分×等級÷4。可選「班級相對」：先從這班的作答挑出錨點，
#                  再對照錨點分級；錨點存起來，同班重評或補交都用同一組尺標。

DEFAULT_MASTER_RUBRIC = """【評分總則】（每一題都適用；各題的配分、評分方式與標準列在題目下方）
1. 只依照該題列出的評分標準或檢核點判斷，不要自己追加標準；不看字數多寡、用詞華麗。
2. 內容相同或意思相同的作答，必須得到相同的判斷結果。
3. 與題目完全無關的亂打、只抄題目，視為沒有達成任何標準。
4. 對象是國小學生：回饋語氣鼓勵但誠實，要具體可行（指出一個還可以補上的點），不要只說「很棒」這種空話。"""

LEVEL_TOP = 4
DEFAULT_POINTS = 10
BONUS_DEFAULT_POINTS = 3
MODES = ("levels", "checklist", "condition")
CHUNK_ANSWERS = 40
CHUNK_PIECES = 60
ANCHOR_SAVE_MIN = 5   # 不同作答少於這個數量時挑出的錨點不存（樣本太少，存了會讓之後全班都被小樣本的尺標綁住）
BLANK_NOTE = "這次沒有作答，先把想法寫下來就有分數了。"
DEFAULT_STANDARD = "有沒有回答到題目問的；內容是否具體（有例子、理由或自己的觀察）；是否有自己的想法。"


def master_rubric(points=None):
    """教師自訂的評分總則（沒填用預設）；{max} 換成這一題的配分。"""
    tpl = (read_config().get("grade_master_rubric") or "").strip() or DEFAULT_MASTER_RUBRIC
    return tpl.replace("{max}", str(points) if points is not None else "")


def _half_up(x):
    return int(math.floor(float(x) + 0.5))


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except Exception:
        return None


def _ans_text(v):
    if isinstance(v, list):
        return "、".join(str(x) for x in v if x is not None)
    return "" if v is None else str(v)


def _norm_key(v):
    """比對用的正規化：全半形統一、英文小寫、去掉空白與標點。相同 key＝視為相同作答。"""
    s = unicodedata.normalize("NFKC", str(v or "")).lower()
    return re.sub(r"[\s\W_]+", "", s, flags=re.U)


def _is_blank(v):
    """空白／只有標點空格＝沒作答（伺服器直接判 0 分，不送 AI）。"""
    return not _norm_key(_ans_text(v))


def _legacy_rubric_points(rubric):
    total = 0.0
    for c in ((rubric or {}).get("criteria") or []):
        total += max(0.0, _num(c.get("points")) or 0.0)
    return _half_up(total) if total > 0 else None


def _legacy_rubric_standard(rubric):
    lines = []
    for c in ((rubric or {}).get("criteria") or []):
        n, d = str(c.get("name") or "").strip(), str(c.get("desc") or "").strip()
        if n or d:
            lines.append(f"{n}：{d}" if n and d else (n or d))
    return "；".join(lines)


def build_spec(qid, raw, rubric=None, is_bonus=False):
    """把教師設定的題目規格補齊成引擎用的完整形狀。舊資料（沒有 mode／points）一律當 levels，
    標準沿用舊的整份評分規準，配分沿用規準總分——舊學習單不用改設定也能評。"""
    raw = raw if isinstance(raw, dict) else {}
    mode = raw.get("mode") if raw.get("mode") in MODES else "levels"
    checks = []
    for c in (raw.get("checks") or []):
        if not isinstance(c, dict):
            continue
        desc, pts = str(c.get("desc") or "").strip(), _num(c.get("pts"))
        if desc and pts and pts > 0:
            checks.append({"id": f"c{len(checks) + 1}", "desc": desc, "pts": _half_up(pts)})
    conditions = [str(c).strip() for c in (raw.get("conditions") or []) if str(c).strip()]
    if mode == "checklist" and not checks:
        mode = "levels"
    if mode == "condition" and not conditions:
        mode = "levels"
    points = sum(c["pts"] for c in checks) if mode == "checklist" else _num(raw.get("points"))
    if not points or points <= 0:
        points = BONUS_DEFAULT_POINTS if is_bonus else (_legacy_rubric_points(rubric) or DEFAULT_POINTS)
    standard = str(raw.get("standard") or "").strip()
    if not standard and not is_bonus:
        standard = _legacy_rubric_standard(rubric)
    relative = raw.get("relative")
    relative = (not is_bonus) if relative is None else bool(relative)
    need = _num(raw.get("need"))
    return {
        "qid": qid, "prompt": str(raw.get("prompt") or "").strip(), "mode": mode,
        "points": max(1, _half_up(points)), "standard": standard or DEFAULT_STANDARD,
        "relative": relative, "need": max(1, _half_up(need)) if need else 1,
        "conditions": conditions, "basis": str(raw.get("basis") or "").strip(),
        "checks": checks, "bonus": bool(is_bonus),
    }


def _ask_json(prompt):
    r = grade_call(prompt)
    if not r.get("ok"):
        return None, r.get("error") or "AI 呼叫失敗"
    txt = (r.get("text") or "").strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return None, "AI 未回傳 JSON：" + txt[:200]
    try:
        d = json.loads(m.group(0))
    except Exception as e:
        return None, f"JSON 解析失敗：{e}"
    if not isinstance(d, dict):
        return None, "AI 回傳的不是 JSON 物件"
    return d, None


def _ask_for(aliases, make_prompt, validate, on_response=None):
    """問 AI 並逐一驗證每個代號的回覆；沒回來或格式不對的代號再問一次（只問缺的）。
    回傳 ({代號: 驗證後的值}, 錯誤訊息或 None)。"""
    got, err, todo = {}, None, list(aliases)
    for _ in range(2):
        if not todo:
            break
        d, e = _ask_json(make_prompt(todo))
        if d is None:
            err = e
            continue
        if on_response:
            on_response(d, todo)
        for a in todo:
            v = validate(a, d.get(a))
            if v is not None:
                got[a] = v
        todo = [a for a in todo if a not in got]
        err = ("AI 漏回 %d 份作答" % len(todo)) if todo else None
    return got, err


def _q_header(spec, overview):
    parts = []
    ov = str(overview or "").strip()
    if ov:
        parts.append("【學習單背景】\n" + ov[:1500])
    parts.append(f"【題目 {spec['qid']}】{spec['prompt'] or '（未提供題幹，請從作答內容推斷題意）'}")
    return "\n\n".join(parts)


def _answers_block(aliases, amap):
    return "\n".join(f"[{a}] {amap[a]}" for a in aliases)


# ---------- condition：條件查核 ----------
def _split_pieces(text):
    out = []
    for p in re.split(r"[、,，;；/／|｜\n\r\t]+|\s+|以及", str(text or "")):
        p = p.strip(" 　.。!！?？:：()（）[]【】「」『』\"'“”‘’-－~～")
        if _norm_key(p):
            out.append(p)
    return out


def _condition_prompt(spec, overview, known, aliases, amap):
    conds = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(spec["conditions"]))
    known_line = ("【已知正式名稱】片段指的是其中之一時，name 請用完全相同的寫法：" + "、".join(known[:200]) + "\n\n") if known else ""
    return (
        "你是事實查核助手，協助國小老師檢查學生在查資料題寫下的項目是否符合題目條件。你只判斷事實，不評分、不寫回饋。\n\n"
        + _q_header(spec, overview) + "\n\n"
        + "【條件】項目要「全部」符合：\n" + conds + "\n"
        + "【判斷依據】" + (spec["basis"] or "以一般公開資料為準") + "\n\n"
        + known_line
        + "以下是學生寫的片段（p0、p1…），每個片段可能是：一個名稱、好幾個名稱連在一起、錯字或簡稱、或根本不是具體項目。\n"
        "對每個片段：\n"
        "- 找出它指的具體項目，name 用正式全名（錯字、簡稱還原成正式名稱；同一個項目不同寫法要用同一個 name）。\n"
        "- ok：符合全部條件填 true；不符合填 false；沒有把握或查不到這個項目填 null。不確定一定要填 null，不要猜。\n"
        "- why：10 字內的理由（不符合時說明哪個條件不符）。\n"
        "- 片段不是任何具體項目（亂打、只寫類別或地區）就回空陣列 []。\n\n"
        + _answers_block(aliases, amap) + "\n\n"
        '只輸出 JSON（不要多餘文字、不要程式碼圍欄）：{"p0":[{"name":"<正式名稱>","ok":true,"why":"<理由>"}],"p1":[]}'
    )


def _grade_condition(spec, groups, overview, vcache):
    vc = {"pieces": dict((vcache or {}).get("pieces") or {}),
          "items": {k: dict(v) for k, v in ((vcache or {}).get("items") or {}).items() if isinstance(v, dict)}}
    canon_index = {_norm_key(n): n for n in vc["items"]}
    gp = {nk: _split_pieces(g["text"]) for nk, g in groups.items()}
    unknown, seen = [], set()
    for ps in gp.values():
        for p in ps:
            k = _norm_key(p)
            if k not in vc["pieces"] and k not in seen:
                seen.add(k)
                unknown.append(p)
    error = None
    for i in range(0, len(unknown), CHUNK_PIECES):
        chunk = unknown[i:i + CHUNK_PIECES]
        aliases = [f"p{j}" for j in range(len(chunk))]
        amap = dict(zip(aliases, chunk))

        def validate(a, v):
            if not isinstance(v, list):
                return None
            out = []
            for it in v:
                if not isinstance(it, dict):
                    continue
                name = str(it.get("name") or "").strip()
                if not _norm_key(name):
                    continue
                ok = it.get("ok")
                out.append({"name": name, "ok": ok if isinstance(ok, bool) else None,
                            "why": str(it.get("why") or "")[:40]})
            return out

        got, err = _ask_for(aliases, lambda todo: _condition_prompt(spec, overview, list(vc["items"]), todo, amap), validate)
        if err:
            error = err
        for a, lst in got.items():
            canons = []
            for it in lst:
                nk = _norm_key(it["name"])
                canon = canon_index.get(nk)
                if canon is None:
                    canon = it["name"]
                    canon_index[nk] = canon
                    vc["items"][canon] = {"ok": it["ok"], "by": "ai", "why": it["why"]}
                if canon not in canons:
                    canons.append(canon)
            vc["pieces"][_norm_key(amap[a])] = canons
    need, points, results = spec["need"], spec["points"], {}
    for nk in groups:
        entries, seen_c, unresolved = [], set(), False
        for p in gp[nk]:
            k = _norm_key(p)
            if k not in vc["pieces"]:
                unresolved = True
                break
            for c in vc["pieces"][k]:
                if c in seen_c:
                    continue
                seen_c.add(c)
                v = vc["items"].get(c) or {}
                entries.append({"name": c, "ok": v.get("ok"), "why": v.get("why", ""), "by": v.get("by", "ai")})
        if unresolved:
            continue   # 這份作答有片段沒判斷到 → 不給假分數，整位學生留在未評分
        used, extra = entries[:need], entries[need:]
        good = [e["name"] for e in used if e["ok"] is True]
        bad = [e for e in used if e["ok"] is False]
        unsure = [e["name"] for e in used if e["ok"] is None]
        notes = []
        if good:
            notes.append("符合：" + "、".join(good))
        if bad:
            notes.append("不符合：" + "、".join(e["name"] + (f"（{e['why']}）" if e["why"] else "") for e in bad))
        if unsure:
            notes.append("待老師確認：" + "、".join(unsure))
        if len(used) < need:
            notes.append(f"還少 {need - len(used)} 個")
        if extra:
            notes.append(f"只採計前 {need} 個")
        results[nk] = {
            "score": _half_up(points * len(good) / need),
            "detail": {"mode": "condition", "need": need, "items": used, "ignored": [e["name"] for e in extra]},
            "note": "；".join(notes) if notes else "沒有找到具體的項目",
            "flag": bool(unsure),
        }
    return results, vc, error


# ---------- checklist：檢核點 ----------
def _grade_checklist(spec, groups, overview):
    keys = list(groups)
    results, error = {}, None
    checks_txt = "\n".join(f"{c['id']}（{c['pts']} 分）：{c['desc']}" for c in spec["checks"])
    example = ",".join(f'"{c["id"]}":{{"ok":true,"ev":"<原文片段>"}}' for c in spec["checks"])
    for i in range(0, len(keys), CHUNK_ANSWERS):
        chunk = keys[i:i + CHUNK_ANSWERS]
        aliases = [f"a{j}" for j in range(len(chunk))]
        amap = {a: groups[k]["text"] for a, k in zip(aliases, chunk)}

        def make_prompt(todo):
            return (
                "你是國小資訊課的閱卷老師。\n\n" + master_rubric(spec["points"]) + "\n\n" + _q_header(spec, overview) + "\n\n"
                + f"【評分方式：檢核點】本題滿分 {spec['points']} 分，由系統依你判斷的檢核點計分，你不用打分數。\n"
                + checks_txt + "\n\n"
                "規則：\n"
                "- 每個檢核點各自判斷「有沒有做到」，只看內容，不看字數與文筆。\n"
                "- 判定做到（ok:true）時，ev 要從學生原文一字不改地照抄能證明的關鍵片段（20 字內）；原文找不到能證明的片段，就是沒做到（ok:false，ev 留空）。\n"
                "- note：給這位學生一句具體建議（30 字內），優先提醒還沒做到的檢核點；全部做到就肯定一個具體優點。\n\n"
                + _answers_block(todo, amap) + "\n\n"
                + '只輸出 JSON（不要多餘文字、不要程式碼圍欄），每份作答用 [] 裡的代號當鍵名、一個不漏：{"a0":{' + example + ',"note":"<建議>"}}'
            )

        def validate(a, v):
            if not isinstance(v, dict):
                return None
            out = {}
            for c in spec["checks"]:
                cv = v.get(c["id"])
                if not isinstance(cv, dict) or not isinstance(cv.get("ok"), bool):
                    return None
                out[c["id"]] = {"ok": cv["ok"], "ev": str(cv.get("ev") or "")[:60]}
            out["_note"] = str(v.get("note") or "")[:120]
            return out

        got, err = _ask_for(aliases, make_prompt, validate)
        if err:
            error = err
        for a, k in zip(aliases, chunk):
            v = got.get(a)
            if v is None:
                continue
            ans_norm = _norm_key(groups[k]["text"])
            checks, score, flag = [], 0, False
            for c in spec["checks"]:
                cv = v[c["id"]]
                ev_ok = (not cv["ok"]) or (bool(_norm_key(cv["ev"])) and _norm_key(cv["ev"]) in ans_norm)
                if cv["ok"]:
                    score += c["pts"]
                if not ev_ok:
                    flag = True   # AI 說做到了，但引用的證據在原文找不到 → 請老師確認
                checks.append({"id": c["id"], "desc": c["desc"], "pts": c["pts"], "ok": cv["ok"], "ev": cv["ev"], "evMissing": not ev_ok})
            results[k] = {"score": min(score, spec["points"]), "detail": {"mode": "checklist", "checks": checks},
                          "note": v["_note"], "flag": flag}
    return results, error


# ---------- levels：分級（可選班級相對） ----------
def _grade_levels(spec, groups, overview, anchors_in, allow_pick):
    keys = list(groups)
    results, error = {}, None
    anchors = {k: v for k, v in (anchors_in or {}).items() if k in ("4", "2", "1") and str(v or "").strip()} if spec["relative"] else {}
    state = {"anchors": anchors, "picked": False}
    can_pick = spec["relative"] and not anchors and allow_pick and len(keys) >= 3
    basis = "anchors" if anchors else ("pick" if can_pick else "absolute")

    for i in range(0, len(keys), CHUNK_ANSWERS):
        chunk = keys[i:i + CHUNK_ANSWERS]
        aliases = [f"a{j}" for j in range(len(chunk))]
        amap = {a: groups[k]["text"] for a, k in zip(aliases, chunk)}

        def make_prompt(todo):
            head = ("你是國小資訊課的閱卷老師。\n\n" + master_rubric(spec["points"]) + "\n\n" + _q_header(spec, overview) + "\n\n"
                    + f"【配分】本題滿分 {spec['points']} 分。你只要給等級 0～4，分數由系統換算。\n"
                    + "【評分標準】" + spec["standard"] + "\n"
                    + "【等級】4＝優秀　3＝良好　2＝基本達成　1＝明顯不足　0＝與題目無關或無意義\n\n")
            picking = can_pick and not state["anchors"]
            if state["anchors"]:
                a = state["anchors"]
                how = ("【班級相對：本班錨點】以下是這個班級定下的代表作答，是固定的尺標，請和它們比較後給等級（不要重新挑選）：\n"
                       + (f"4 級代表：「{a['4']}」\n" if a.get("4") else "")
                       + (f"2 級代表：「{a['2']}」\n" if a.get("2") else "")
                       + (f"1 級代表：「{a['1']}」\n" if a.get("1") else "")
                       + "和 4 級代表相當或更好給 4；介於 4 級和 2 級代表之間給 3；和 2 級代表相當給 2；和 1 級代表相當或更弱但有回答到題目給 1。\n\n")
            elif picking:
                how = ("【班級相對】以這個班級的整體表現當尺標。先讀完全部作答，從中挑三份當本班錨點："
                       "本班最好的代表（4 級）、本班中間水準的代表（2 級）、本班偏弱但有回答到題目的代表（1 級），把代號填在 anchors；"
                       "再把每份作答和錨點比較給等級。\n\n")
            else:
                how = "【絕對標準】依評分標準判斷每份作答，不和其他同學比較。\n\n"
            rules = ("規則：\n"
                     "- 只看內容是否回應題目、符合評分標準、夠不夠具體，不看字數與文筆。\n"
                     "- 品質相近的作答給相同等級；如果大家都一樣好，就都給一樣的等級，不需要為了拉開差距硬分高低。\n"
                     "- note：給這位學生一句具體建議（30 字內），指出一個還可以補上的點。\n\n")
            anchor_schema = '"anchors":{"4":"<代號>","2":"<代號>","1":"<代號>"},' if picking else ""
            return (head + how + rules + _answers_block(todo, amap) + "\n\n"
                    + '只輸出 JSON（不要多餘文字、不要程式碼圍欄），每份作答用 [] 裡的代號當鍵名、一個不漏：{'
                    + anchor_schema + '"a0":{"level":<0到4整數>,"note":"<建議>"}}')

        def on_response(d, todo):
            if not (can_pick and not state["anchors"]):
                return
            an = d.get("anchors")
            if not isinstance(an, dict):
                return
            picked = {lv: amap[str(an.get(lv))] for lv in ("4", "2", "1") if str(an.get(lv)) in amap}
            if picked:
                state["anchors"] = picked
                state["picked"] = True

        def validate(a, v):
            if not isinstance(v, dict):
                return None
            lv = _num(v.get("level"))
            if lv is None:
                return None
            return {"level": max(0, min(LEVEL_TOP, _half_up(lv))), "note": str(v.get("note") or "")[:120]}

        got, err = _ask_for(aliases, make_prompt, validate, on_response)
        if err:
            error = err
        for a, k in zip(aliases, chunk):
            v = got.get(a)
            if v is None:
                continue
            results[k] = {"score": _half_up(spec["points"] * v["level"] / LEVEL_TOP),
                          "detail": {"mode": "levels", "level": v["level"], "basis": "absolute" if basis == "absolute" else "relative"},
                          "note": v["note"], "flag": False}
    keep = state["picked"] and len(keys) >= ANCHOR_SAVE_MIN
    return results, (state["anchors"] if keep else None), error


# ---------- 引擎：逐題評完，再組回每位學生 ----------
def _grade_engine(items, questions, bonus_qids, open_qids, overview, verdicts, anchors, allow_pick, rubric=None):
    bonus_set = set(bonus_qids or [])
    qmap = {q.get("qid"): q for q in (questions or []) if isinstance(q, dict) and q.get("qid")}
    answered_qids, per_q = [], {}
    for it in items:
        for q, a in (it.get("answers") or {}).items():
            if q not in answered_qids:
                answered_qids.append(q)
            txt = _ans_text(a)
            if _is_blank(txt):
                continue
            g = per_q.setdefault(q, {}).setdefault(_norm_key(txt), {"text": txt.strip(), "keys": []})
            g["keys"].append(it["key"])
    main_qids = [q for q in (open_qids or []) if q not in bonus_set]
    main_qids += [q for q in answered_qids if q not in bonus_set and q not in main_qids]
    specs = {q: build_spec(q, qmap.get(q), rubric, q in bonus_set) for q in set(main_qids) | set(answered_qids)}

    def run(q):
        spec, groups = specs[q], per_q[q]
        if spec["mode"] == "condition":
            res, vc, err = _grade_condition(spec, groups, overview, (verdicts or {}).get(q))
            return q, res, err, vc, None
        if spec["mode"] == "checklist":
            res, err = _grade_checklist(spec, groups, overview)
            return q, res, err, None, None
        res, anc, err = _grade_levels(spec, groups, overview, (anchors or {}).get(q), allow_pick)
        return q, res, err, None, anc

    qres, errors, new_verdicts, new_anchors = {}, [], {}, {}
    todo = [q for q in specs if per_q.get(q)]
    if todo:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for q, res, err, vc, anc in ex.map(run, todo):
                qres[q] = res
                if err:
                    errors.append(f"{q}：{err}")
                if vc is not None:
                    new_verdicts[q] = vc
                if anc:
                    new_anchors[q] = anc

    ai_max = sum(specs[q]["points"] for q in main_qids) if main_qids else None
    results, missing = {}, []
    for it in items:
        ans = it.get("answers") or {}
        student_qids = main_qids + [q for q in ans if q in bonus_set]
        scores, bonus_scores, details, notes, flags, bad, any_answer = {}, {}, {}, [], [], False, False
        for q in student_qids:
            spec, txt = specs[q], _ans_text(ans.get(q))
            if _is_blank(txt):
                sc, d = 0, {"mode": spec["mode"], "blank": True}
            else:
                any_answer = True
                r = (qres.get(q) or {}).get(_norm_key(txt))
                if r is None:
                    bad = True
                    break
                sc, d = r["score"], dict(r["detail"])
                d["note"] = r.get("note") or ""
                if d["note"]:
                    notes.append((q, d["note"]))
                if r.get("flag"):
                    flags.append(q)
            d["points"], d["bonus"] = spec["points"], spec["bonus"]
            details[q] = d
            (bonus_scores if q in bonus_set else scores)[q] = min(sc, spec["points"])
        if bad:
            missing.append(it["key"])
            continue
        out = {"details": details, "flags": flags, "aiMax": ai_max}
        if main_qids:
            out["scores"] = scores
            out["score"] = sum(scores.values())
        if any(q in bonus_set for q in student_qids):
            out["bonusScores"] = bonus_scores
            out["bonusScore"] = sum(bonus_scores.values())
        if not any_answer:
            out["feedback"] = BLANK_NOTE
        elif len(notes) == 1:
            out["feedback"] = notes[0][1]
        else:
            out["feedback"] = "　".join(f"【{q}】{n}" for q, n in notes)
        results[it["key"]] = out
    return {"results": results, "missing": missing, "aiMax": ai_max, "verdicts": new_verdicts,
            "anchors": new_anchors, "error": "；".join(errors) if errors else None}


def grade_batch(payload):
    """POST /api/grade-batch：整個班級一次評完。對教師來說仍是一個按鈕批改全班；
    內部改成「逐題」組 prompt（同一題的全班作答放一起、用同一套標準），各題平行呼叫。"""
    items = [it for it in (payload.get("items") or []) if isinstance(it, dict) and it.get("key")]
    r = _grade_engine(items, payload.get("questions"), payload.get("bonusQids"), payload.get("openQids"),
                      payload.get("overview"), payload.get("verdicts"), payload.get("anchors"), True, payload.get("rubric"))
    return {"ok": True, **r}


def grade_submission(payload):
    """POST /api/grade：批改抽屜單筆評分。同一套引擎；班級相對的題目沿用該班已存的錨點，
    沒有錨點時（單筆沒有母體可挑）退回絕對標準。"""
    answers = payload.get("answers") or {}
    answer_key = payload.get("answerKey") or {}
    per_item, auto_ok, auto_total = [], 0, 0
    for qid, correct in answer_key.items():
        got = answers.get(qid)
        ok = _norm(got) == _norm(correct)
        auto_total += 1
        auto_ok += 1 if ok else 0
        per_item.append({"qid": qid, "type": "objective", "correct": ok, "expected": correct, "got": got})
    auto_score = round(auto_ok / auto_total * 100) if auto_total else None
    open_items = {q: v for q, v in answers.items() if q not in answer_key}
    out = {"ok": True, "autoScore": auto_score, "aiScore": None, "bonusScore": None, "scores": None,
           "bonusScores": None, "aiMax": None, "aiFeedback": "", "details": None, "flags": [],
           "verdicts": {}, "perItem": per_item, "autoCorrect": auto_ok, "autoTotal": auto_total}
    if not open_items:
        return out
    r = _grade_engine([{"key": "one", "answers": open_items}], payload.get("questions"), payload.get("bonusQids"),
                      payload.get("openQids"), payload.get("overview"), payload.get("verdicts"), payload.get("anchors"),
                      False, payload.get("rubric"))
    out["aiMax"], out["verdicts"] = r["aiMax"], r["verdicts"]
    res = r["results"].get("one")
    if not res:
        out["aiFeedback"] = "AI 評分失敗：" + (r.get("error") or "AI 沒有回應")
        return out
    out.update({"aiScore": res.get("score"), "scores": res.get("scores"), "bonusScore": res.get("bonusScore"),
                "bonusScores": res.get("bonusScores"), "aiFeedback": res.get("feedback", ""),
                "details": res.get("details"), "flags": res.get("flags") or []})
    return out


def fetch_grading_spec(url):
    """讀學習單網頁裡的 <script type="application/json" id="grading-spec">（見《學習單資料與提交規範》§2-e），
    讓出題時就寫好的「題幹＋評分方式＋標準＋配分」一鍵帶進評分平台。"""
    if not url:
        return {"ok": False, "error": "缺 url"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 gradingPlatform"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read(3_000_000).decode("utf-8", "replace")
        m = re.search(r'<script[^>]*id=["\']grading-spec["\'][^>]*>(.*?)</script>', raw, re.S | re.I)
        if not m:
            return {"ok": False, "error": "這份學習單沒有內嵌評分設定（id=\"grading-spec\" 的 JSON）"}
        d = json.loads(m.group(1).strip())
        qs = d.get("questions") if isinstance(d, dict) else d
        if not isinstance(qs, list):
            return {"ok": False, "error": "評分設定格式不對：要有 questions 陣列"}
        # scoring（選填）：出題時就寫好的分數計算——總分、起跳分數、每題預設扣分、非開放題逐題配分（見提交規範 §2-e）
        sc_in = d.get("scoring") if isinstance(d, dict) and isinstance(d.get("scoring"), dict) else {}
        scoring = {}
        for k in ("base", "floor", "deduction"):
            v = _num(sc_in.get(k))
            if v is not None and v >= 0:
                scoring[k] = v
        ip = {str(q): _num(v) for q, v in (sc_in.get("itemPoints") or {}).items()} if isinstance(sc_in.get("itemPoints"), dict) else {}
        ip = {q: v for q, v in ip.items() if v is not None and v >= 0}
        if ip:
            scoring["itemPoints"] = ip
        return {"ok": True, "questions": [q for q in qs if isinstance(q, dict) and q.get("qid")],
                "summary": (d.get("summary") if isinstance(d, dict) else "") or "", "scoring": scoring}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _html_text(fragment):
    """HTML 片段 → 純文字（去掉 style／svg／標籤，保留 script 內文：題目常寫在 JS 陣列裡）。"""
    import html as _html
    t = re.sub(r"<(style|svg)[^>]*>.*?</\1>", " ", fragment, flags=re.S | re.I)
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", _html.unescape(t)).strip()


def _scale_checks(checks, target):
    """檢核點配分依比例調成加總＝target（每點至少 1 分，差額補在配分最大的那點）。"""
    s = sum(c["pts"] for c in checks)
    if not target or not s or s == target or len(checks) > target:
        return checks
    for c in checks:
        c["pts"] = max(1, _half_up(c["pts"] * target / s))
    diff = target - sum(c["pts"] for c in checks)
    big = max(checks, key=lambda c: c["pts"])
    big["pts"] = max(1, big["pts"] + diff)
    return checks


def gen_grading_spec(payload):
    """AI 先讀學習單網頁，替每一題開放題寫評分設定（題幹、評分方式、標準、配分）。
    結果只回給教師端填進卡片，老師檢查後按「儲存設定」才寫進 worksheets/{id}.questions——綁這份學習單，各班共用。"""
    url = str(payload.get("url") or "").strip()
    wanted = [q for q in (payload.get("questions") or []) if isinstance(q, dict) and str(q.get("qid") or "").strip()]
    if not url:
        return {"ok": False, "error": "這份學習單還沒登記網址，AI 讀不到內容。"}
    if not wanted:
        return {"ok": False, "error": "目前沒有開放題可以設定（還沒有人繳交、下面也沒有題目卡片）。"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 gradingPlatform"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read(3_000_000).decode("utf-8", "replace")
    except Exception as e:
        return {"ok": False, "error": f"讀不到學習單網頁：{e}"}
    body = re.sub(r"<head[^>]*>.*?</head>", " ", raw, count=1, flags=re.S | re.I)
    page = _html_text(body)[:30000]
    blocks = []
    for q in wanted:
        qid = str(q["qid"]).strip()
        ctx = []
        for m in list(re.finditer(r'data-qid=["\']' + re.escape(qid) + r'["\']', raw))[:2]:
            ctx.append(_html_text(raw[max(0, m.start() - 2500):m.start() + 800])[-900:])
        samples = [str(s)[:200] for s in (q.get("samples") or []) if str(s).strip()][:6]
        target = _num(q.get("points"))
        blocks.append(
            f"### 題號 {qid}（{'加分題' if q.get('bonus') else '主要開放題'}）\n"
            + (f"- 目前題幹：{str(q.get('prompt') or '').strip()}\n" if str(q.get('prompt') or '').strip() else "")
            + (f"- 指定配分：{_half_up(target)} 分（必須照這個配分）\n" if target and target > 0 else "- 配分：由你建議（主要題 2～10、加分題 1～3）\n")
            + ("- 題目附近的網頁文字：" + " …… ".join(ctx) + "\n" if ctx else "")
            + ("- 幾份學生實際作答（看作答長相用，不代表對錯）：\n" + "\n".join("  · " + s for s in samples) + "\n" if samples else ""))
    prompt = (
        "你是國小資訊課老師的評分設計助手。請先讀完下面這份學習單的內容，再替指定的每一題開放題寫評分設定。\n\n"
        f"學習單標題：{payload.get('title') or ''}\n"
        + (f"老師寫的概要：{payload.get('summary')}\n" if payload.get("summary") else "")
        + "\n【評分方式怎麼選】\n"
        "- condition（條件查核）：查資料、答案只要「符合條件」就對，可能的答案多到列不完（例：找出 2 個中西區的景點）。"
        "要填 conditions（條件，每個項目必須全部符合）、need（要找幾個）、basis（判斷依據，選填，例：以台南旅遊網的分類為準）。\n"
        "- checklist（檢核點）：開放但有明確要素（例：說出景點＋用查到的資料說明理由）。要填 checks：2～4 個「有沒有做到」的項目，每項 desc 與整數 pts，pts 加總＝配分。\n"
        "- levels（分級）：表達想法、品質有高低（心得、你會怎麼做）。要填 standard：一兩句「好的回答要做到什麼」。"
        "主要題 relative=true（以班級程度當尺標），加分題 relative=false。\n\n"
        "【原則】\n"
        "1. 標準只要求題目真的有問的東西，符合國小學生程度，不額外要求字數、修辭或題目沒提到的內容。\n"
        "2. 每個標準都要能從學生寫的文字直接判斷有沒有做到，不寫「用心」「認真」這種看不出來的描述。\n"
        "3. prompt 填學生在學習單上看到的題目文字（從網頁內容找；找不到就沿用目前題幹）。\n"
        "4. 有指定配分的題目，points 必須等於指定配分；checklist 的 pts 加總也必須等於它。\n\n"
        "【學習單內容（網頁文字，已去掉排版）】\n" + page + "\n\n"
        "【要設定的題目】\n" + "\n".join(blocks) + "\n"
        "只回傳 JSON，不要其他文字，格式：\n"
        '{"summary":"一句話說這份學習單在教什麼","questions":[{"qid":"題號","prompt":"題幹","mode":"levels|checklist|condition",'
        '"points":整數,"standard":"","relative":true,"checks":[{"desc":"","pts":整數}],"conditions":[""],"need":1,"basis":""}]}'
    )
    d, err = _ask_json(prompt)
    if err:
        return {"ok": False, "error": err}
    want = {str(q["qid"]).strip(): q for q in wanted}
    out = []
    for q in (d.get("questions") or []):
        if not isinstance(q, dict):
            continue
        qid = str(q.get("qid") or "").strip()
        if qid not in want or any(o["qid"] == qid for o in out):
            continue
        is_bonus = bool(want[qid].get("bonus"))
        spec = build_spec(qid, q, None, is_bonus)
        target = _num(want[qid].get("points"))
        target = _half_up(target) if target and target > 0 else None
        checks = [{"desc": c["desc"], "pts": c["pts"]} for c in spec["checks"]]
        if spec["mode"] == "checklist":
            checks = _scale_checks(checks, target)
            points = sum(c["pts"] for c in checks)
        else:
            points = target or spec["points"]
        out.append({
            "qid": qid, "prompt": spec["prompt"] or str(want[qid].get("prompt") or "").strip(), "mode": spec["mode"],
            "points": points, "standard": str(q.get("standard") or "").strip(), "relative": spec["relative"],
            "checks": checks, "conditions": spec["conditions"], "basis": spec["basis"], "need": spec["need"]})
    if not out:
        return {"ok": False, "error": "AI 沒有回傳可用的題目設定，請再試一次。"}
    missing = [q for q in want if not any(o["qid"] == q for o in out)]
    return {"ok": True, "questions": out, "summary": str(d.get("summary") or "").strip()[:120], "missing": missing}


# ========== Google Classroom（自帶授權，redirect 指向 8780）==========
def _http(url, method="GET", headers=None, data=None, timeout=90):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:500]}") from None
    return json.loads(raw) if raw.strip() else {}


def _post_form(url, form):
    data = urllib.parse.urlencode(form).encode()
    return _http(url, "POST", {"Content-Type": "application/x-www-form-urlencoded"}, data)


def google_auth_url():
    cfg = read_config()
    cid = (cfg.get("google_client_id") or "").strip()
    if not cid:
        return {"ok": False, "error": "尚未填 Google client_id"}
    params = {"client_id": cid, "redirect_uri": REDIRECT_URI, "response_type": "code",
              "scope": GOOGLE_SCOPES, "access_type": "offline", "prompt": "consent",
              "include_granted_scopes": "true"}
    return {"ok": True, "url": "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)}


def google_exchange(code):
    cfg = read_config()
    tok = _post_form("https://oauth2.googleapis.com/token", {
        "code": code, "client_id": cfg.get("google_client_id", ""),
        "client_secret": cfg.get("google_client_secret", ""),
        "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"})
    cfg["google_token"] = {"access_token": tok.get("access_token"),
                           "refresh_token": tok.get("refresh_token"),
                           "expires_at": time.time() + tok.get("expires_in", 3600),
                           "scope": tok.get("scope", "")}
    save_config(cfg)
    return tok


def google_access_token():
    cfg = read_config()
    t = cfg.get("google_token") or {}
    if not t.get("access_token"):
        return None
    if t.get("expires_at", 0) < time.time() + 60 and t.get("refresh_token"):
        nt = _post_form("https://oauth2.googleapis.com/token", {
            "refresh_token": t["refresh_token"], "client_id": cfg.get("google_client_id", ""),
            "client_secret": cfg.get("google_client_secret", ""), "grant_type": "refresh_token"})
        if nt.get("access_token"):
            t["access_token"] = nt["access_token"]
            t["expires_at"] = time.time() + nt.get("expires_in", 3600)
            cfg["google_token"] = t
            save_config(cfg)
    return t.get("access_token")


def _gapi(url, method="GET", body=None):
    token = google_access_token()
    if not token:
        raise RuntimeError("尚未授權 Google（請在設定按『授權 Google』）")
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    return _http(url, method, headers, data)


def google_courses():
    try:
        data = _gapi("https://classroom.googleapis.com/v1/courses?courseStates=ACTIVE&teacherId=me&pageSize=100")
        courses = [{"id": c["id"], "name": c.get("name", ""), "section": c.get("section", "")}
                   for c in data.get("courses", [])]
        return {"ok": True, "courses": courses}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def classroom_announce(course_id, text):
    """在 Classroom 課程的訊息串發一則公告（繳交紀錄的「發布缺交名單」）。"""
    text = str(text or "").strip()
    if not course_id or not text:
        return {"ok": False, "error": "缺課程或公告內容"}
    scope = ((read_config().get("google_token") or {}).get("scope") or "")
    if scope and "classroom.announcements" not in scope:
        return {"ok": False, "needReauth": True,
                "error": "目前的 Google 授權沒有「發布公告」權限，請到「設定 → Google Classroom」重新按一次「授權 Google」。"}
    try:
        r = _gapi(f"https://classroom.googleapis.com/v1/courses/{course_id}/announcements", "POST",
                  {"text": text[:30000], "state": "PUBLISHED"})
        return {"ok": True, "id": r.get("id"), "link": r.get("alternateLink", "")}
    except Exception as e:
        msg = str(e)
        if "403" in msg and ("scope" in msg.lower() or "insufficient" in msg.lower() or "PERMISSION" in msg):
            return {"ok": False, "needReauth": True,
                    "error": "Google 拒絕發布（權限不足）。請到「設定 → Google Classroom」重新授權一次後再試。"}
        return {"ok": False, "error": msg}


def classroom_coursework(course_id):
    if not course_id:
        return {"ok": False, "error": "缺 courseId"}
    try:
        data = _gapi(f"https://classroom.googleapis.com/v1/courses/{course_id}/courseWork?pageSize=100")
        works = [{"id": w["id"], "title": w.get("title", ""), "maxPoints": w.get("maxPoints")}
                 for w in data.get("courseWork", [])]
        return {"ok": True, "courseWork": works}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def classroom_students(course_id):
    if not course_id:
        return {"ok": False, "error": "缺 courseId"}
    try:
        data = _gapi(f"https://classroom.googleapis.com/v1/courses/{course_id}/students?pageSize=200")
        studs = [{"userId": s["userId"],
                  "name": (s.get("profile", {}).get("name", {}) or {}).get("fullName", "")}
                 for s in data.get("students", [])]
        return {"ok": True, "students": studs}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _norm_title(s):
    return re.sub(r"\s+", "", str(s or "")).lower()


def classroom_find_coursework(course_id, title):
    """依標題找現有作業（正規化比對，忽略空白與大小寫）。回傳 courseWork dict 或 None。"""
    data = _gapi(f"https://classroom.googleapis.com/v1/courses/{course_id}/courseWork?pageSize=100")
    want = _norm_title(title)
    for w in data.get("courseWork", []):
        if _norm_title(w.get("title")) == want:
            return w
    return None


def classroom_create_coursework(course_id, title, max_points=100, link="", description=""):
    """找不到同名作業時，依學習單名稱建立一份新作業（PUBLISHED，全班指派）。"""
    if not (course_id and str(title or "").strip()):
        return {"ok": False, "error": "缺 courseId 或作業標題"}
    try:
        found = classroom_find_coursework(course_id, title)
        if found:
            return {"ok": True, "created": False, "id": found["id"],
                    "title": found.get("title", ""), "maxPoints": found.get("maxPoints")}
        body = {
            "title": str(title).strip(),
            "workType": "ASSIGNMENT",
            "state": "PUBLISHED",
            "maxPoints": float(max_points) if max_points else 100.0,
        }
        if description:
            body["description"] = str(description)[:2000]
        if link:
            body["materials"] = [{"link": {"url": link}}]
        w = _gapi(f"https://classroom.googleapis.com/v1/courses/{course_id}/courseWork", "POST", body)
        return {"ok": True, "created": True, "id": w["id"],
                "title": w.get("title", ""), "maxPoints": w.get("maxPoints")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def classroom_grades(course_id, coursework_id, grades):
    if not (course_id and coursework_id):
        return {"ok": False, "error": "缺 courseId 或 courseWorkId"}
    base = f"https://classroom.googleapis.com/v1/courses/{course_id}/courseWork/{coursework_id}/studentSubmissions"
    try:
        subs = _gapi(base + "?pageSize=200")
        by_user = {s.get("userId"): s.get("id") for s in subs.get("studentSubmissions", [])}
        # 剛建立的作業，Classroom 生成每位學生的 studentSubmission 有短暫延遲；空的話等一下再讀一次。
        if not by_user:
            time.sleep(2)
            subs = _gapi(base + "?pageSize=200")
            by_user = {s.get("userId"): s.get("id") for s in subs.get("studentSubmissions", [])}
    except Exception as e:
        return {"ok": False, "error": "讀取作業繳交失敗：" + str(e)}
    done, failed = [], []
    for g in (grades or []):
        uid, grade = g.get("userId"), g.get("grade")
        sid = by_user.get(uid)
        if not sid:
            failed.append({"userId": uid, "error": "此作業找不到該生的繳交"})
            continue
        try:
            _gapi(f"{base}/{sid}?updateMask=draftGrade,assignedGrade", "PATCH",
                  {"draftGrade": grade, "assignedGrade": grade})
        except Exception as e:
            failed.append({"userId": uid, "error": str(e)[:100]})
            continue
        try:
            _gapi(f"{base}/{sid}:return", "POST", {})
        except Exception:
            pass
        done.append(uid)
    return {"ok": True, "done": len(done), "failed": failed}


def diagnostics():
    cfg = read_config()
    out = {"ai": {"configured": bool(cfg.get("grade_key")), "provider": cfg.get("grade_provider", "")}}
    g = {"client": bool(cfg.get("google_client_id")), "authorized": bool((cfg.get("google_token") or {}).get("access_token"))}
    if g["authorized"]:
        c = google_courses()
        g["ok"] = c.get("ok", False)
        g["detail"] = (f"{len(c['courses'])} 門課程" if c.get("ok") else c.get("error", "")[:120])
    out["google"] = g
    return {"ok": True, "diag": out}


# ========== HTTP handler：API 優先，其餘走靜態檔 ==========
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path):
        rel = urllib.parse.unquote(path.lstrip("/")) or "teacher.html"
        f = (HERE / rel).resolve()
        if not str(f).startswith(str(HERE)) or not f.is_file():
            return self._send(404, {"error": "not found"})
        data = f.read_bytes()
        ct = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/api/settings":
                # 底線開頭＝唯讀附加欄位（前端顯示用，POST 回來時會被丟掉，不會寫進 config）
                cfg = dict(read_config())
                cfg["_default_master_rubric"] = DEFAULT_MASTER_RUBRIC
                return self._send(200, cfg)
            if u.path == "/api/grade-models":
                return self._send(200, grade_models())
            if u.path == "/api/fetch-title":
                return self._send(200, fetch_title(q.get("url", [""])[0]))
            if u.path == "/api/grading-spec":
                return self._send(200, fetch_grading_spec(q.get("url", [""])[0]))
            if u.path == "/api/google/auth-url":
                return self._send(200, google_auth_url())
            if u.path == "/api/google/courses":
                return self._send(200, google_courses())
            if u.path == "/api/classroom/coursework":
                return self._send(200, classroom_coursework(q.get("courseId", [""])[0]))
            if u.path == "/api/classroom/students":
                return self._send(200, classroom_students(q.get("courseId", [""])[0]))
            if u.path == "/api/diagnostics":
                return self._send(200, diagnostics())
            if u.path == "/api/timetable":
                return self._send(200, {"ok": True, "timetable": read_timetable()})
            if u.path == "/api/update/check":
                return self._send(200, updater.check_update(HERE))
            if u.path == "/oauth/callback":
                code = q.get("code", [""])[0]; err = q.get("error", [""])[0]
                if err:
                    return self._send(200, f"<h2>授權失敗：{err}</h2>", "text/html; charset=utf-8")
                try:
                    google_exchange(code)
                    return self._send(200, "<meta charset='utf-8'><h2>已完成 Google 授權</h2><p>可關閉此分頁，回評分平台按「測試連線」確認。</p>", "text/html; charset=utf-8")
                except Exception as e:
                    import html as _html
                    return self._send(200, f"<meta charset='utf-8'><h2>換 token 失敗</h2><pre>{_html.escape(str(e))}</pre>", "text/html; charset=utf-8")
            if u.path in ("/", "/index.html"):
                return self._serve_static("/teacher.html")
            return self._serve_static(u.path)
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        ln = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(ln) if ln else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            data = {}
        try:
            if u.path == "/api/update/apply":
                return self._send(200, updater.apply_update(HERE))
            if u.path == "/api/settings":
                cfg = read_config()
                # 密鑰欄位「留空＝不變更」：避免前端欄位還沒載入就按下按鈕，把已存的金鑰洗掉。
                # 要清除授權請用 /api/google/logout。
                for k, v in (data or {}).items():
                    if k.startswith("_"):      # 唯讀附加欄位（如 _default_master_rubric），不落地
                        continue
                    if k in ("google_client_secret", "grade_key") and not str(v or "").strip() and cfg.get(k):
                        continue
                    cfg[k] = v
                save_config(cfg)
                return self._send(200, {"ok": True})
            if u.path == "/api/timetable":
                return self._send(200, save_timetable(data))
            if u.path == "/api/grade":
                return self._send(200, grade_submission(data))
            if u.path == "/api/grade-batch":
                return self._send(200, grade_batch(data))
            if u.path == "/api/gen-grading-spec":
                return self._send(200, gen_grading_spec(data))
            if u.path == "/api/google/logout":
                cfg = read_config(); cfg.pop("google_token", None); save_config(cfg)
                return self._send(200, {"ok": True})
            if u.path == "/api/classroom/coursework":
                return self._send(200, classroom_create_coursework(
                    data.get("courseId", ""), data.get("title", ""),
                    data.get("maxPoints", 100), data.get("link", ""), data.get("description", "")))
            if u.path == "/api/classroom/announce":
                return self._send(200, classroom_announce(data.get("courseId", ""), data.get("text", "")))
            if u.path == "/api/classroom/grades":
                return self._send(200, classroom_grades(data.get("courseId", ""), data.get("courseWorkId", ""), data.get("grades", [])))
            return self._send(404, {"error": "no route"})
        except Exception as e:
            return self._send(500, {"error": str(e)})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"評分平台 running → http://127.0.0.1:{PORT}/teacher.html")
    print(f"獨立運作：Google 授權與 AI 評分設定都在自己的「設定」面板裡，不需要工作台也能用。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
