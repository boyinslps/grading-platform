# 評分平台（Grading Platform）

課堂評量與成績管理平台：學生繳交互動學習單 → 資料庫 → 教師端 AI／標準答案評分、名單、匯出、回寫 Google Classroom。

> **獨立專案**：本資料夾是一個獨立的專案，可單獨作為一個 GitHub repo。
> **與「工作台」連動**：AI 評分、Classroom 回寫、金鑰等特權動作**不在本專案**，由旁邊的「工作台」(`../工作台`) 在 `http://127.0.0.1:8770` 提供；本平台前端跨來源呼叫它（工作台已開 CORS）。**金鑰只留在工作台，本專案不儲存任何金鑰。**

## 檔案
| 檔案 | 說明 |
|---|---|
| `teacher.html` | 教師端（登入→選學習單→設定答案/規準→評分→匯出/回寫 Classroom）|
| `student-submit.js` | 可重用的學生「繳交」模組（互動教材引入即可）|
| `demo-worksheet.html` | 繳交測試示範頁 |
| `worksheets.json` | 學習單登錄檔：完成一份就把網址寫進來 |
| `firestore.rules` | Firestore 安全規則（到 Firebase Console 部署）|
| `server.py` | 本機靜態伺服器（port 8780）|
| `啟動評分平台.bat` | 雙擊啟動；用旁邊工作台的 portable Python 執行 |
| `SPEC.md` / `PROGRESS.md` | 規格與施工進度 |

## 啟動
1. 先啟動「工作台」（`../工作台/啟動工作台.bat`）——提供 AI／Classroom。
2. 雙擊 `啟動評分平台.bat` → 瀏覽器開 `http://127.0.0.1:8780/teacher.html`。
3. 首次使用：到 Firebase Console 部署 `firestore.rules`；工作台 ⚙ 設定按「AI 設定」填反向代理與模型、必要時重新授權 Google。

## 資料庫
沿用 Firebase 專案 `pcclass-94300`（Firestore）。集合：`submissions`（繳交）、`worksheets`（學習單設定/答案）、`courses`（班級名單）。

## 當成獨立 repo 推上 GitHub
本資料夾不含任何金鑰，可直接 `git init` 後推成自己的 repo（例：`git@github.com:boyinslps/grading-platform.git`）。
- 執行期才需要「工作台」在同一台機器上跑（連動），repo 本身不必包含工作台。
- 若把本資料夾搬離 `../工作台` 旁邊，`啟動評分平台.bat` 找不到 portable Python，請改用系統 Python 或自備。
