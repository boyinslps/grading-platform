# -*- coding: utf-8 -*-
"""
評分平台 · 本機伺服器（獨立專案，port 8780）

服務本資料夾的靜態檔（teacher.html / student-submit.js / worksheets.json …），
並且**自帶一份 Google Classroom 授權與 AI 評分後端**，讓評分平台不必依賴「工作台」
（8770）就能獨立運作——設定存在本資料夾自己的 config.json，跟工作台的設定各自獨立。
"""
import json, re, io, base64, zipfile, mimetypes, urllib.request, urllib.parse, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.json"
PORT = 8780
REDIRECT_URI = f"http://127.0.0.1:{PORT}/oauth/callback"
GOOGLE_SCOPES = " ".join([
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
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


# ========== AI 評分總則（最上級評分規範）==========
# 每次呼叫 AI 評分都會先插入這一段，再接該份學習單自己的「評分規準」。
# 教師可在「設定 → AI 評分 → 評分總則」自行修改，改過的存在 config.json 的 grade_master_rubric；
# 留空＝用下面這份預設。規範原文同步維護在 ../引導規範/AI評分規範.md。
DEFAULT_MASTER_RUBRIC = """【評分總則】
1. 給分上限：你能給的最高分＝下方「評分規準」各項配分的總和（本次上限為 {max} 分），任何情況都不可超過，也不要自己換算成百分制。
2. 相對表現（重點）：同一批是同一個班級的作答，請先看完全部，再依「和同儕比的突出程度」給分——以這批作答的平均水準當基準線，明顯比多數人具體、完整、有自己觀察的往上拉，只有一兩句、照抄題目或含糊其辭的往下壓。**不要因為人數多就每個人給差不多的分數**，分數該拉開就要拉開，讓高低差看得出來。
3. 沒作答＝0 分：空白、只有標點或無意義字元、與題目完全無關的亂打，一律 0 分，不給同情分。
4. 評分依序看：有沒有回答到題目問的 → 內容是否具體（有例子、理由或自己的觀察） → 是否有自己的想法。**不是看字數多寡或用詞華麗**。
5. 對象是國小學生：語氣鼓勵但誠實；回饋要具體可行（指出一個還可以再補上的點），不要只說「很棒」這種空話。"""


def master_rubric(ai_max):
    """取教師自訂的評分總則（沒填就用預設），並把本次的給分上限填進去。"""
    tpl = (read_config().get("grade_master_rubric") or "").strip() or DEFAULT_MASTER_RUBRIC
    return tpl.replace("{max}", str(ai_max))


def _rubric_total(rubric):
    """評分規準（開放題用）各項配分總和＝AI 給分上限；沒有規準時退回 100。"""
    total = 0.0
    for c in ((rubric or {}).get("criteria") or []):
        try:
            total += float(c.get("points") or 0)
        except Exception:
            pass
    total = int(round(total))
    return total if total > 0 else 100


def _rubric_text(rubric, ai_max):
    if rubric and rubric.get("criteria"):
        return ("評分規準（各項配分加總＝上限 %d 分）：\n" % ai_max) + "\n".join(
            f"- {c.get('name','')}（{c.get('points','')} 分）：{c.get('desc','')}" for c in rubric["criteria"])
    return "評分規準：這份學習單沒有另外訂規準，請就『有沒有回答到題目、內容具體程度、是否有自己的想法』給 0–%d 分。" % ai_max


def _open_qid_note(main_items, bonus_items):
    """列在評分規準前面：這次送評的開放題／開放加分題各有哪些編號（qid），
    讓 AI 在看規準之前就先知道要分辨的題目範圍（2026-09-16 教師指定）。
    main_items/bonus_items 為空的那一類就不提，兩者都空就整段不輸出。"""
    parts = []
    if main_items:
        parts.append("主要開放題＝" + "、".join(main_items.keys()))
    if bonus_items:
        parts.append("加分題＝" + "、".join(bonus_items.keys()))
    if not parts:
        return ""
    caveat = "（下面規準的給分上限只適用於主要開放題；加分題不算進規準，另外用 0～3 分尺規評）" if bonus_items else ""
    return "本次開放題編號：" + "；".join(parts) + caveat + "\n\n"


def _is_blank(v):
    """空白／只有標點空格＝沒作答（評分總則第 3 點，由伺服器直接判定，不交給 AI 判斷）。"""
    return not re.sub(r'[\s\W_]+', '', str(v or ''), flags=re.U)


def _split_open(open_items, bonus_qids):
    """把開放題答案拆成「主要」與「加分」兩組（見《學習單資料與提交規範》§2-b：
    加分題仍是 open 型，只是另外被 bonusQids 標記，一樣要送 AI，只是分開算分、獨立疊加）。"""
    bonus_qids = set(bonus_qids or [])
    main = {q: a for q, a in (open_items or {}).items() if q not in bonus_qids}
    bonus = {q: a for q, a in (open_items or {}).items() if q in bonus_qids}
    return main, bonus


def _ai_grade(open_items, rubric, questions, bonus_qids=None):
    qmap = {q.get("qid"): q for q in (questions or [])}
    ai_max = _rubric_total(rubric)
    main_items, bonus_items = _split_open(open_items, bonus_qids)
    has_main, has_bonus = bool(main_items), bool(bonus_items)
    main_blank = (not has_main) or all(_is_blank(v) for v in main_items.values())
    bonus_blank = (not has_bonus) or all(_is_blank(v) for v in bonus_items.values())
    # 全部（主要＋加分）都空白 → 不必呼叫 AI，直接 0 分（評分總則第 3 點）
    if (not has_main or main_blank) and (not has_bonus or bonus_blank):
        return {"ok": True, "score": 0 if has_main else None, "bonusScore": 0 if has_bonus else None,
                "feedback": "這次沒有作答，先把想法寫下來就有分數了。", "perItem": [], "aiMax": ai_max}
    blocks = []
    if has_main and not main_blank:
        for qid, ans in main_items.items():
            pq = (qmap.get(qid, {}) or {}).get("prompt", "")
            blocks.append(f"[{qid}] 題目：{pq or '(無題幹)'}\n學生作答：{ans}")
    bonus_blocks = []
    if has_bonus and not bonus_blank:
        for qid, ans in bonus_items.items():
            pq = (qmap.get(qid, {}) or {}).get("prompt", "")
            bonus_blocks.append(f"[{qid}] 題目：{pq or '(無題幹)'}\n學生作答：{ans}")
    schema_fields = []
    if has_main and not main_blank:
        schema_fields.append(f'"score":<0到{ai_max}整數,主要開放題總評分>')
    if has_bonus and not bonus_blank:
        schema_fields.append('"bonusScore":<0到3整數,加分題等級：0未達到/1簡短/2普通/3詳細>')
    schema_fields.append('"feedback":"<給學生的兩三句中文回饋>"')
    qid_note = _open_qid_note(main_items if (has_main and not main_blank) else {},
                               bonus_items if (has_bonus and not bonus_blank) else {})
    prompt = "你是國小資訊課的閱卷老師。請依下列總則與規準評分。\n\n" + master_rubric(ai_max) + "\n\n" + qid_note + _rubric_text(rubric, ai_max)
    if blocks:
        prompt += "\n\n【主要開放題】\n" + "\n\n".join(blocks)
    if bonus_blocks:
        prompt += (
            "\n\n【加分題，獨立於主要分數之外，額外加分用，不算進上面的評分規準】\n"
            "依內容完整度給 0～3 分：完全沒寫或跟題目無關給 0，只有一兩句、籠統帶過給 1，"
            "內容完整合理給 2，具體、有自己觀察或例子給 3。\n" + "\n\n".join(bonus_blocks)
        )
    prompt += (
        '\n\n只輸出 JSON（無多餘文字、無程式碼圍欄）：{' + ",".join(schema_fields)
        + ',"perItem":[{"qid":"..","score":<0到100>,"feedback":"<一句>"}]}'
    )
    r = grade_call(prompt)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "AI 呼叫失敗")}
    m = re.search(r'\{.*\}', r.get("text", ""), re.S)
    if not m:
        return {"ok": False, "error": "AI 未回傳 JSON：" + r.get("text", "")[:200]}
    try:
        d = json.loads(m.group(0))
    except Exception as e:
        return {"ok": False, "error": f"JSON 解析失敗：{e}"}
    # 上限由伺服器強制夾住，不靠 AI 自律（評分總則第 1 點）；沒作答的那一組不論 AI 說什麼，一律覆蓋成 0
    def clamp(v, hi):
        try:
            return max(0, min(hi, round(float(v))))
        except Exception:
            return None
    per = []
    for it in (d.get("perItem") or []):
        if isinstance(it, dict):
            per.append({"qid": it.get("qid"), "score": clamp(it.get("score"), 100),
                        "feedback": it.get("feedback", "")})
    score = (0 if main_blank else clamp(d.get("score"), ai_max)) if has_main else None
    bonus_score = (0 if bonus_blank else clamp(d.get("bonusScore"), 3)) if has_bonus else None
    return {"ok": True, "score": score, "bonusScore": bonus_score, "feedback": d.get("feedback", ""),
            "perItem": per, "aiMax": ai_max}


def _ai_grade_batch(items, rubric, questions, want_feedback, bonus_qids=None):
    """整批（同一班）一次 AI 呼叫評完，不是逐筆呼叫 /api/grade。
    items: [{"key":<submission id>, "answers":{qid:text,...}}, ...]
    回傳 {"ok":True,"results":{key:{"score":?,"bonusScore":?,"feedback":str}},"missing":[key,...]} 或 {"ok":False,"error":...}
    加分題（bonus_qids 標記的 qid）跟主要開放題一起送 AI，但分開算分、分開回傳（見《學習單資料與提交規範》§2-b）。
    """
    if not items:
        return {"ok": True, "results": {}, "missing": [], "aiMax": _rubric_total(rubric)}
    qmap = {q.get("qid"): q for q in (questions or [])}
    ai_max = _rubric_total(rubric)

    def parts(it):
        main, bonus = _split_open(it.get("answers"), bonus_qids)
        has_main, has_bonus = bool(main), bool(bonus)
        main_blank = (not has_main) or all(_is_blank(v) for v in main.values())
        bonus_blank = (not has_bonus) or all(_is_blank(v) for v in bonus.values())
        return main, bonus, has_main, has_bonus, main_blank, bonus_blank

    # 完全沒作答（主要＋加分都空白）的先挑出來直接 0 分（評分總則第 3 點）：不送進 prompt，省 token，
    # 也不會讓一堆空白作答拉低 AI 對「這批平均水準」的判斷（第 2 點的相對比較只看有寫的人）。
    results, graded = {}, []
    for it in items:
        main, bonus, has_main, has_bonus, main_blank, bonus_blank = parts(it)
        if (not has_main or main_blank) and (not has_bonus or bonus_blank):
            entry = {}
            if has_main: entry["score"] = 0
            if has_bonus: entry["bonusScore"] = 0
            if want_feedback: entry["feedback"] = "這次沒有作答，先把想法寫下來就有分數了。"
            results[it["key"]] = entry
        else:
            graded.append((it, main, bonus, has_main, has_bonus, main_blank, bonus_blank))
    if not graded:
        return {"ok": True, "results": results, "missing": [], "aiMax": ai_max}
    # 用短代號（k0、k1…）當 JSON 鍵，不直接把 Firestore doc id 塞進 prompt——
    # 代號在伺服器端跟 key 一一對應，回來再換回去，不必擔心 doc id 裡的符號讓 AI 產生非法 JSON 鍵名。
    aliases = [f"k{i}" for i in range(len(graded))]
    # 整批共用一份規準，所以在規準前面列的是這份學習單這批人「出現過」的開放題／加分題編號聯集，
    # 不是逐生列（逐生的 qid 已經在各自的【kN】區塊裡標了）。
    all_main_qids, all_bonus_qids = {}, {}
    for (it, main, bonus, has_main, has_bonus, main_blank, bonus_blank) in graded:
        if has_main and not main_blank:
            for q in main.keys():
                all_main_qids.setdefault(q, True)
        if has_bonus and not bonus_blank:
            for q in bonus.keys():
                all_bonus_qids.setdefault(q, True)
    qid_note = _open_qid_note(all_main_qids, all_bonus_qids)
    blocks = []
    any_bonus_asked = False
    for alias, (it, main, bonus, has_main, has_bonus, main_blank, bonus_blank) in zip(aliases, graded):
        lines = [f"【{alias}】"]
        if has_main and not main_blank:
            lines.append("主要開放題：")
            for qid, ans in main.items():
                pq = (qmap.get(qid, {}) or {}).get("prompt", "")
                lines.append(f"[{qid}] 題目：{pq or '(無題幹)'}\n學生作答：{ans}")
        if has_bonus and not bonus_blank:
            any_bonus_asked = True
            lines.append("加分題（獨立於主要分數之外）：")
            for qid, ans in bonus.items():
                pq = (qmap.get(qid, {}) or {}).get("prompt", "")
                lines.append(f"[{qid}] 題目：{pq or '(無題幹)'}\n學生作答：{ans}")
        blocks.append("\n".join(lines))
    feedback_field = ',"feedback":"<給這位學生的兩三句中文回饋>"' if want_feedback else ""
    bonus_field = ',"bonusScore":<0到3整數，加分題等級；這位沒有加分題作答就不用給>' if any_bonus_asked else ""
    schema = "{" + f'"{aliases[0]}":{{"score":<0到{ai_max}整數，沒有主要開放題作答就不用給>{bonus_field}{feedback_field}}}' + ",...}"
    prompt = (
        "你是國小資訊課的閱卷老師。以下是同一個班級、同一份學習單裡多位學生的開放題作答，請依下列總則與規準逐一評分。\n"
        "每位學生的作答可能分成「主要開放題」與「加分題」：主要開放題依評分規準評分；"
        "加分題獨立於主要分數之外，依內容完整度給 0～3 分（完全沒寫或跟題目無關 0 分，"
        "只有一兩句、籠統帶過 1 分，內容完整合理 2 分，具體、有自己觀察或例子 3 分）。\n\n"
        + master_rubric(ai_max) + "\n\n" + qid_note
        + _rubric_text(rubric, ai_max) + "\n\n" + "\n\n".join(blocks) +
        "\n\n只輸出一個 JSON 物件（無多餘文字、無程式碼圍欄），"
        f"每位學生都要用【】裡的代號當鍵名、一個不漏，格式例如：{schema}"
    )
    r = grade_call(prompt)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "AI 呼叫失敗")}
    m = re.search(r'\{.*\}', r.get("text", ""), re.S)
    if not m:
        return {"ok": False, "error": "AI 未回傳 JSON：" + r.get("text", "")[:300]}
    try:
        parsed = json.loads(m.group(0))
    except Exception as e:
        return {"ok": False, "error": f"JSON 解析失敗：{e}"}
    if not isinstance(parsed, dict):
        return {"ok": False, "error": "AI 回傳的不是預期的 JSON 物件"}

    def clamp(v, hi):
        try:
            return max(0, min(hi, round(float(v))))
        except Exception:
            return None

    missing = []
    for alias, (it, main, bonus, has_main, has_bonus, main_blank, bonus_blank) in zip(aliases, graded):
        entry = parsed.get(alias)
        if not isinstance(entry, dict):
            missing.append(it["key"]); continue
        out = {}
        if has_main:
            sc = 0 if main_blank else clamp(entry.get("score"), ai_max)
            if sc is None:
                missing.append(it["key"]); continue
            out["score"] = sc
        if has_bonus:
            bs = 0 if bonus_blank else clamp(entry.get("bonusScore"), 3)
            out["bonusScore"] = bs if bs is not None else 0
        if want_feedback:
            out["feedback"] = entry.get("feedback") or ""
        results[it["key"]] = out
    return {"ok": True, "results": results, "missing": missing, "aiMax": ai_max}


def grade_batch(payload):
    """POST /api/grade-batch：整個班級一次呼叫（見 _ai_grade_batch）；超過 CHUNK 人才分段，
    每段仍是一次呼叫評多人，不會退化成逐筆呼叫。"""
    items = payload.get("items") or []
    rubric = payload.get("rubric")
    questions = payload.get("questions") or []
    bonus_qids = payload.get("bonusQids") or []
    want_feedback = bool(payload.get("wantFeedback"))
    CHUNK = 40
    all_results, all_missing, errors = {}, [], []
    for i in range(0, len(items), CHUNK):
        chunk = items[i:i + CHUNK]
        r = _ai_grade_batch(chunk, rubric, questions, want_feedback, bonus_qids)
        if not r.get("ok"):
            errors.append(r.get("error", "AI 呼叫失敗"))
            all_missing.extend(it["key"] for it in chunk)
            continue
        all_results.update(r.get("results") or {})
        all_missing.extend(r.get("missing") or [])
    return {"ok": True, "results": all_results, "missing": all_missing,
            "aiMax": _rubric_total(rubric),
            "error": "；".join(errors) if errors else None}


def grade_submission(payload):
    answers = payload.get("answers") or {}
    answer_key = payload.get("answerKey") or {}
    rubric = payload.get("rubric")
    questions = payload.get("questions") or []
    bonus_qids = payload.get("bonusQids") or []
    per_item, auto_ok, auto_total = [], 0, 0
    for qid, correct in answer_key.items():
        got = answers.get(qid)
        ok = _norm(got) == _norm(correct)
        auto_total += 1
        auto_ok += 1 if ok else 0
        per_item.append({"qid": qid, "type": "objective", "correct": ok,
                         "expected": correct, "got": got})
    auto_score = round(auto_ok / auto_total * 100) if auto_total else None
    open_items = {q: v for q, v in answers.items() if q not in answer_key}
    ai_score, ai_bonus_score, ai_feedback, ai_max = None, None, "", _rubric_total(rubric)
    if open_items:
        ai = _ai_grade(open_items, rubric, questions, bonus_qids)
        if ai.get("ok"):
            ai_score = ai.get("score")
            ai_bonus_score = ai.get("bonusScore")
            ai_max = ai.get("aiMax", ai_max)
            ai_feedback = ai.get("feedback", "")
            for it in (ai.get("perItem") or []):
                it["type"] = "open"
                per_item.append(it)
        else:
            ai_feedback = "AI 評分失敗：" + ai.get("error", "")
    return {"ok": True, "autoScore": auto_score, "aiScore": ai_score,
            "bonusScore": ai_bonus_score, "aiMax": ai_max,
            "aiFeedback": ai_feedback, "perItem": per_item,
            "autoCorrect": auto_ok, "autoTotal": auto_total}


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
            if u.path == "/api/grade":
                return self._send(200, grade_submission(data))
            if u.path == "/api/grade-batch":
                return self._send(200, grade_batch(data))
            if u.path == "/api/google/logout":
                cfg = read_config(); cfg.pop("google_token", None); save_config(cfg)
                return self._send(200, {"ok": True})
            if u.path == "/api/classroom/coursework":
                return self._send(200, classroom_create_coursework(
                    data.get("courseId", ""), data.get("title", ""),
                    data.get("maxPoints", 100), data.get("link", ""), data.get("description", "")))
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
