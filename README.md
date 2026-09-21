# 評分平台（Grading Platform）

課堂評量與成績管理平台：學生繳交互動學習單 → 資料庫 → 教師端 AI／標準答案評分、名單、匯出、回寫 Google Classroom。

> **獨立專案，獨立運作**：本資料夾是一個獨立的專案，可單獨作為一個 GitHub repo。
> `server.py`（port 8780）**自帶**一份 AI 評分後端與 Google Classroom OAuth 授權，設定存在本專案自己的 `config.json`，**不需要「工作台」也能完整運作**。
> 若你偏好用工作台集中管理設定，把 `teacher.html` 裡的 `WORKBENCH` 常數從 `""` 改成 `"http://127.0.0.1:8770"` 即可切換（工作台那邊的對應 API 仍在）。**`config.json` 含金鑰，已加進 `.gitignore`，絕不會被推上 GitHub。**

## 檔案
| 檔案 | 說明 |
|---|---|
| `teacher.html` | 教師端（登入→選班級/學習單→設定分數計算/規準→評分→匯出/回寫 Classroom）。頁首「設定」整合 AI／Google Classroom／名單匯入（單班、批量匯入全部班級）為分頁 |
| `student-submit.js` | 可重用的學生「繳交」模組（互動教材引入即可）|
| `demo-worksheet.html` | 繳交測試示範頁 |
| `worksheets.json` | 學習單登錄檔：完成一份就把網址寫進來 |
| `timetable.json` | 課表（星期×節次→班級、節次上下課時間、每班本週學習單）——第一次按「儲存課表」才產生，**不進 git** |
| `firestore.rules` | Firestore 安全規則（到 Firebase Console 部署）|
| `server.py` | 本機伺服器（port 8780）：靜態檔＋AI 評分＋Google OAuth／Classroom（含依學習單名稱自動建立作業）|
| `config.json` | 本專案自己的設定（AI Key、Google client_secret、token）——**執行後自動產生，不進 git** |
| `啟動評分平台.bat` | 雙擊啟動；用本資料夾自帶的 `runtime\python`（找不到才退而找旁邊工作台的、或系統 Python） |
| `runtime/` | 自帶的可攜式 Python（跟資料夾一起複製到別台電腦／USB 就能跑，不進 git） |
| `SPEC.md` / `PROGRESS.md` | 規格與施工進度 |

## 啟動
1. 雙擊 `啟動評分平台.bat` → 瀏覽器開 `http://127.0.0.1:8780/teacher.html`（不必先開工作台）。
2. 首次使用：
   - 到 Firebase Console 部署 `firestore.rules`。
   - 登入後點右上「AI 設定」：填 AI 反向代理＋Key（測試並列出模型）；填 Google OAuth client_id/secret，把 `http://127.0.0.1:8780/oauth/callback` 加進該 OAuth 用戶端的「已授權的重新導向 URI」後按「授權 Google」。

## 資料庫
沿用 Firebase 專案 `pcclass-94300`（Firestore）。集合：`submissions`（繳交）、`worksheets`（學習單設定/答案）、`courses`（班級名單）、`feeds`（開放題即時同儕動態）。

## 當成獨立 repo 推上 GitHub
本資料夾不含任何金鑰（`config.json` 已排除），可直接 `git init` 後推成自己的 repo（例：`git@github.com:boyinslps/grading-platform.git`）。
- 完全自足：連可攜式 Python 都在 `runtime/` 資料夾內自帶，複製整個資料夾（USB／換電腦）就能跑，不需要「工作台」在同一台機器上，也不需要另外裝 Python。
