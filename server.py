# -*- coding: utf-8 -*-
"""
評分平台 · 本機靜態伺服器（獨立專案，port 8780）

只負責服務本資料夾的靜態檔（teacher.html / student-submit.js / worksheets.json / demo-worksheet.html …）。
特權動作（AI 評分、Google Classroom 回寫、金鑰）不在這裡——由『工作台』(http://127.0.0.1:8770) 提供，
本平台的前端會跨來源呼叫它（連動；工作台已開 CORS）。金鑰只留在工作台，本專案不碰。
"""
import mimetypes, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = 8780


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/", "/index.html"):
            p = "/teacher.html"
        rel = urllib.parse.unquote(p.lstrip("/"))
        f = (HERE / rel).resolve()
        if not str(f).startswith(str(HERE)) or not f.is_file():
            self.send_response(404); self.end_headers(); self.wfile.write(b"not found"); return
        data = f.read_bytes()
        ct = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"評分平台 running → http://127.0.0.1:{PORT}/teacher.html")
    print("特權動作（AI 評分／Classroom）需『工作台』同時開著：http://127.0.0.1:8770")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
