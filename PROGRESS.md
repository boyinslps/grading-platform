# 評分平台 · 施工進度（PROGRESS）

> 這是 /loop 每輪的記憶。每輪：讀 `SPEC.md`＋本檔 → 接續未完成階段 → 更新本檔（勾完成、寫下一步）。
> 專案根目錄：`D:\自動化教案生成工作流\評分平台`。介面**不用 emoji**；後端串既有 `工作台/server.py`；資料庫 Firebase `pcclass-94300`。

## 階段勾選
- [x] **P0 專案骨架**：SPEC.md、PROGRESS.md、teacher.html 設計骨架（無 emoji）、資料模型定案。
- [x] **P1 學生繳交模組**：`student-submit.js` 可重用（自動掃 data-qid 或自訂 collect）＋`demo-worksheet.html` 示範＋`firestore.rules`。資料模型改扁平 `submissions`。teacher.html 已改讀扁平模型。**待教師部署 firestore.rules 後可端到端測試。**
- [x] **P2 教師端讀取**：teacher.html 由 submissions 推出學習單清單、以 worksheetId 讀繳交、表格＋統計磚＋批改抽屜。（評分動作在 P3。）
- [ ] **P2.5 真實測試**：教師部署規則 → 開 demo-worksheet.html（真檔非預覽）繳交 → teacher.html 應看到該筆。
- [x] **P3 評分引擎＋批改**：server `/api/grade`（標準答案自動核對＋開放題丟 AI，回 autoScore/aiScore/aiFeedback/perItem，**已直接測通**：客觀 50 分、AI 開放題 100 分＋中文回饋）。server 加 CORS＋OPTIONS＋靜態服務 `評分平台/`。teacher.html 批改抽屜接上：逐筆評分、顯示逐題對錯與 AI 回饋、可改最終分、寫回 `submissions`（status='graded'）；工具列「AI 批次評分」整份跑。
- [x] **P3.5 學習單設定面板**：teacher.html「學習單設定」按鈕 → 面板可編標準答案（逐題，多選用「、」）與評分規準（可增刪列）→ 存進 `worksheets/{ws}`；存後評分即套用。
- [x] **P4 名單/匯出/Classroom**（完成）：
  - [x] **P4-a 成績匯出 CSV**：teacher.html「匯出成績」→ 由 subsCache 組 CSV（座號/姓名/班級/自動/AI/最終/狀態/繳交時間）＋UTF-8 BOM → 前端 Blob 下載。
  - [x] **P4-b 名單匯入**：teacher.html「匯入名單」對話框，貼「座號,姓名」（逗號/Tab/空白分隔皆可）→ 前端解析 → firestore batch 寫 `courses/{cid}` ＋ `courses/{cid}/students/{seat}`；即時預覽筆數、匯入後刷新左欄班級。
  - [x] **P4-c Classroom**：後端 `/api/classroom/coursework`、`/students`、`/grades`（**已測**憑證與列課程/作業）。前端「回寫 Classroom」modal：選課程→選作業→拉名單→**以姓名自動對應**（對不到手動指定或「不回寫」）→送出並發還。`students` 需 `classroom.rosters.readonly` scope → **教師重新授權 Google** 才有名單。
- [ ] **P4 名單/匯出/Classroom**：CSV 名單匯入、成績 CSV 匯出、Classroom 名單匯入＋成績回寫。
- [~] **P5 Scratch 評分**：後端 `/api/grade-scratch`（.sb3 解 zip 讀 project.json → 盤點精靈/積木/變數/概念）**已測**。前端上傳 UI＋依 rubric/AI 給分＝下輪。
- [x] **獨立專案化**：評分平台成為獨立資料夾/可獨立成 repo——自有 `server.py`（靜態，port 8780）＋`啟動評分平台.bat`（用旁邊工作台的 portable Python）＋`README.md`＋`.gitignore`。**連動**：AI/Classroom/金鑰仍走工作台 8770（CORS）；本專案不存金鑰。已煙霧測試通過（8780 服務 teacher.html/worksheets.json）。
- [ ] **P6 工作台整合**：成品階段一鍵綁定學習單/開評分台；rubric 編輯器。

## 本輪做了什麼（最新在上）
- **2026-09-08 · 修錯誤訊息（權限不足診斷）**：使用者回報「新增學習單」貼網址時跳 `Missing or insufficient permissions.`——查證 firestore.rules 檔本身正確（write worksheets 需 isTeacher()，email 與 teacher.html 的 DEFAULT_TEACHER_EMAIL 一致），推斷**最可能原因是 firestore.rules 從未部署到 Firebase Console**（本機檔案不會自動生效，需手動貼到 Console 發布）。加 `friendlyErr(e)`：偵測 `permission-denied` 時，把原始 SDK 錯誤換成兩點可行動診斷（1. 規則未部署 2. 登入帳號需與 isTeacher() email 一致）＋顯示目前登入帳號；套用到新增學習單／學習單設定儲存／名單匯入／評分存檔四個寫入點。`.note` 加 `white-space:pre-line` 讓多行訊息正確換行。已驗證函式行為與訊息內容正確、無 console error。**待使用者操作**：到 Firebase Console 部署 firestore.rules 才能解除。
- **2026-09-08 · P5後端＋獨立專案化**：（1）工作台 server.py 加 `grade_scratch`＋`_scratch_inventory`＋路由 `/api/grade-scratch`；用假 .sb3 **測通**盤點（精靈/積木/變數/概念偵測正確）。（2）依教師指示把評分平台做成**獨立專案**：新增 `評分平台/server.py`（靜態伺服器 8780）、`啟動評分平台.bat`（用 `..\工作台\runtime` 的 portable Python）、`README.md`、`.gitignore`。前端仍 `WORKBENCH=8770` 連動工作台拿 AI/Classroom（金鑰只在工作台）。8780 靜態服務已煙霧測試通過。**bat 修正**：原本存成 LF 換行導致 cmd 整批亂跑，已改 CRLF、且改用 `for /d` 尋找旁邊工作台的 portable Python（避免檔內出現中文路徑）。
- **2026-09-08 · 教師指定（登錄檔＋分類收合＋讀標題＋Admin連結＋評分AI窗口）**：
  1. **worksheets.json 登錄檔**（含範例 g5-L01）：教師寫入 url 即可，教師端讀它＋Firestore＋submissions 合併成清單。
  2. **新增學習單改成貼網址**：自動由網址推 ID（deriveId，已測 `.../g5/L01/`→`g5-L01`）＋分類；建立時打 `/api/fetch-title` 讀網頁 `<title>` 當標題（已測讀到 L01 標題）。
  3. **標題直接讀學習單**：清單項目沒標題但有 url → 背景 `/api/fetch-title` 補上並寫回 Firestore。
  4. **左欄年級資料夾可收合**：category 變成可點的下拉資料夾（預設收合、點才列出、狀態存 localStorage）。
  5. **標準答案 Admin 連結**：設定面板加「開啟學習單 Admin」→ `url#admin`，非文字答案（拖曳/圖形）到學習單本身設。
  6. **評分 AI 獨立窗口**：server 重構 `_llm_call`/`_llm_models`＋新增 `grade_call`/`grade_models`/`fetch_title`＋路由 `/api/grade-models`、`/api/fetch-title`；`_ai_grade` 改用 grade_call。teacher.html「AI 設定」modal：填反向代理 URL＋Key→「測試並列出模型」（存 grade_* 到 config→`/api/grade-models`）→選模型存。未設 grade_key 時回退主 AI（已測 grade_models 回退列出真實模型）。
  7. 規範 `引導規範/AI串接窗口設定規範.md`（AI 統一串接標準）。已驗證元素齊全、無 console error、mock 呈現正確。
- **2026-09-08 · 教師指定（學習單管理＋分類）**：teacher.html —（1）「新增學習單」modal：填 ID／標題／分類 → 建 `worksheets/{id}` 文件（不必等學生繳交就能先建、先設答案）。（2）學習單設定面板加**標題**與**分類**（四上/四下/五上/五下）欄位，連同 answerKey/rubric 一起存進 `worksheets/{ws}`（已是上傳 Firebase）。（3）左欄學習單**依分類分組**顯示。存檔後即時重整左欄。已驗證元素齊全、無 console error、mock 預覽正確。→ 使用者現在可在此管理每筆學習單的答案與分類。
- **2026-09-08 · 第8輪（P4-c 前端·P4 完成）**：teacher.html 加「回寫 Classroom」modal（無 emoji）：選課程→選作業（滿分顯示）→背景拉名單→建對應表（座號/姓名/分數/Classroom 學生下拉），**以正規化姓名自動對應**、顯示對應率，對不到可手動選或「不回寫」→ 送 `/api/classroom/grades`，回報成功/失敗數。只回寫已評分（totalScore!=null）者。已驗證元素齊全、buildCCMap 定義、無 console error。**P4 全數完成。**
- **2026-09-08 · 第7輪（P4-c Classroom 後端）**：server.py 加三個 API——`classroom_coursework`（列作業）、`classroom_students`（列名單）、`classroom_grades`（回寫：patch draftGrade+assignedGrade→`:return`；找不到繳交或已發還都容錯）。加對應 GET/POST 路由。GOOGLE_SCOPES 補 `classroom.rosters.readonly`。**import 直測**：google_courses 正常列出真實課程、classroom_coursework 正常（該課無作業回空陣列）；classroom_students 目前 403＝舊 token 沒 rosters scope，**教師重新授權 Google 後**即通。grade 回寫用既有 `coursework.students` scope（已含）。
- **2026-09-08 · 第6輪（P4-b 名單匯入）**：teacher.html 加「匯入名單」modal（沿用 .gate/.panel 風格、無 emoji）。`parseRoster()` 容錯解析（逗號/Tab/空白），即時預覽筆數；「匯入」用 firestore batch 寫 `courses/{cid}`＋`students/{seat}`，完成刷新左欄。登入即啟用（不需先選學習單）。已驗證元素齊全、無 console error。
- **2026-09-08 · 第5輪（P4-a 成績匯出 CSV）**：teacher.html「匯出成績」接上 `exportCSV()`：由 subsCache 組 8 欄 CSV、加 UTF-8 BOM（Excel 中文正常）、Blob 下載，檔名 `{ws}_成績.csv`。已確認 BOM 位元組正確（EF BB BF）、無 console error。
- **2026-09-08 · 第4輪（P3.5 學習單設定面板）**：teacher.html 加「學習單設定」按鈕與可摺疊面板。標準答案區依繳交推出的題號逐題列輸入（多選用「、」分隔，留空＝開放題）；評分規準區可新增/刪除列（名稱／分數／描述）。「儲存設定」寫進 `worksheets/{ws}`（title/answerKey/rubric，merge），存後 curWsCfg 更新、評分即套用。已驗證元素齊全、無 console error。
- **2026-09-08 · 第3輪（P3 評分核心）**：server.py 加 `grade_submission`＋`_ai_grade`＋`_norm`＋路由 `/api/grade`；加 CORS 標頭、`do_OPTIONS`、把 `評分平台/` 納入靜態服務（讓 teacher.html 可同源由 8770 提供）。**已用 import 直接測通** grade_submission（客觀＋AI 混合都正確、AI 回真中文回饋）。teacher.html：`selectWs` 讀 `worksheets/{ws}` 取 answerKey/rubric；批改抽屜加「評分」按鈕→打 `/api/grade`→顯示逐題對錯＋AI 回饋＋最終分（可改）→「儲存」寫回；工具列「AI 批次評分」逐份跑。⚠ 需**重啟工作台**（載入新 server.py）grading 才會通。
- **2026-09-08 · 第2輪（P1＋P2 讀取）**：寫 `student-submit.js`（自足可重用繳交模組：自動掃 `[data-qid]` 或自訂 collect、選班級/座號/姓名、匿名登入、寫扁平 `submissions/{ws__course__seat}`、已繳交鎖定＋可覆蓋、localStorage 記身分）。建 `demo-worksheet.html`（單選/多選/開放題三型示範）。建 `firestore.rules`（quizzes＋submissions＋worksheets＋courses）。**資料模型改扁平 submissions**（避免幽靈父文件查不到），對應改 teacher.html 的 `loadWorksheets`（由繳交推學習單清單）與 `loadSubs`（where worksheetId==）。預覽窗因 data: 快照擋相對路徑，模組需開真檔＋部署規則才能端到端測。
- **2026-09-08 · 第1輪**：建立專案。寫 SPEC.md（架構／資料模型／API／階段）與本檔。建 teacher.html 教師端骨架（左欄班級＋學習單、主區 submissions 表格、批改面板；無 emoji、專業淺色；Firebase compat 已接，讀 `worksheets/{ws}/submissions`；目前空資料呈現空狀態）。更新 HTML 規範 §5.1 影片準則（大片外連／短示範內嵌）。

## 下一步（下輪從這裡接）
1. **P5 前端**：teacher.html 加「Scratch 評分」——上傳 .sb3 → 打 `/api/grade-scratch` → 顯示盤點（精靈/積木/概念勾選表）→ 依 rubric（概念清單對照）＋AI 給分。可綁到某學習單當一種題型。
2. **P6 工作台整合**：工作台成品階段一鍵「登錄為學習單」（把 06_成品 網址/標題/分類寫進評分平台的 worksheets）。
3. **把 L01 接上繳交**（待教師點頭再動 L01）：內嵌 student-submit，wsId=`g5-L01`。
4. 待教師：**重啟工作台**＋**部署 firestore.rules**＋**重新授權 Google**（rosters scope）→ 端到端測試。用 `啟動評分平台.bat` 開 8780。

## 待教師確認（見 SPEC §8）
- 繳交對應：座號＋班級是否足夠。
- 評分粒度：逐題分 vs rubric 總分。
- Classroom 作業對應方式。

## 注意
- 金鑰只在 `工作台/config.json`／server；teacher.html 只放 public firebaseConfig。
- 教師端讀 submissions 需 Email/密碼登入（isTeacher）；學生匿名只能 create 自己那筆。
- 每完成一個可視成果，用 SendUserFile 給教師看方向。
