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
def _llm_call(provider, key, model, endpoint, prompt):
    provider = (provider or "openai").lower()
    key = (key or "").strip(); model = (model or "").strip(); endpoint = (endpoint or "").strip()
    if not key:
        return {"ok": False, "error": "尚未填 API Key"}
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


def _ai_grade(open_items, rubric, questions):
    qmap = {q.get("qid"): q for q in (questions or [])}
    blocks = []
    for qid, ans in open_items.items():
        pq = (qmap.get(qid, {}) or {}).get("prompt", "")
        blocks.append(f"[{qid}] 題目：{pq or '(無題幹)'}\n學生作答：{ans}")
    if rubric and rubric.get("criteria"):
        rub = "評分規準：\n" + "\n".join(
            f"- {c.get('name','')}（{c.get('points','')} 分）：{c.get('desc','')}" for c in rubric["criteria"])
    else:
        rub = "評分規準：未提供。請就內容完整度、正確性、是否切題，給 0–100 分。"
    prompt = (
        "你是國小資訊課的閱卷老師，語氣鼓勵但誠實。請依規準為以下開放題作答評分。\n"
        + rub + "\n\n" + "\n\n".join(blocks) +
        '\n\n只輸出 JSON（無多餘文字、無程式碼圍欄）：'
        '{"score":<0到100整數,整份總評分>,"feedback":"<給學生的兩三句中文回饋>",'
        '"perItem":[{"qid":"..","score":<0到100>,"feedback":"<一句>"}]}'
    )
    r = grade_call(prompt)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "AI 呼叫失敗")}
    m = re.search(r'\{.*\}', r.get("text", ""), re.S)
    if not m:
        return {"ok": False, "error": "AI 未回傳 JSON：" + r.get("text", "")[:200]}
    try:
        d = json.loads(m.group(0))
        return {"ok": True, "score": d.get("score"), "feedback": d.get("feedback", ""),
                "perItem": d.get("perItem", [])}
    except Exception as e:
        return {"ok": False, "error": f"JSON 解析失敗：{e}"}


def grade_submission(payload):
    answers = payload.get("answers") or {}
    answer_key = payload.get("answerKey") or {}
    rubric = payload.get("rubric")
    questions = payload.get("questions") or []
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
    ai_score, ai_feedback = None, ""
    if open_items:
        ai = _ai_grade(open_items, rubric, questions)
        if ai.get("ok"):
            ai_score = ai.get("score")
            ai_feedback = ai.get("feedback", "")
            for it in (ai.get("perItem") or []):
                it["type"] = "open"
                per_item.append(it)
        else:
            ai_feedback = "AI 評分失敗：" + ai.get("error", "")
    return {"ok": True, "autoScore": auto_score, "aiScore": ai_score,
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


def classroom_grades(course_id, coursework_id, grades):
    if not (course_id and coursework_id):
        return {"ok": False, "error": "缺 courseId 或 courseWorkId"}
    base = f"https://classroom.googleapis.com/v1/courses/{course_id}/courseWork/{coursework_id}/studentSubmissions"
    try:
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
                return self._send(200, read_config())
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
                cfg = read_config(); cfg.update(data); save_config(cfg)
                return self._send(200, {"ok": True})
            if u.path == "/api/grade":
                return self._send(200, grade_submission(data))
            if u.path == "/api/google/logout":
                cfg = read_config(); cfg.pop("google_token", None); save_config(cfg)
                return self._send(200, {"ok": True})
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
