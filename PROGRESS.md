# 評分平台 · 施工進度（PROGRESS）

> 這是 /loop 每輪的記憶。每輪：讀 `SPEC.md`＋本檔 → 接續未完成階段 → 更新本檔（勾完成、寫下一步）。
> 專案根目錄：`D:\自動化教案生成工作流\評分平台`。介面**不用 emoji**；資料庫 Firebase `pcclass-94300`。
> **2026-09-08 起：後端已改為評分平台自己的 `server.py`（8780）獨立運作**（AI 評分＋Google OAuth／Classroom 都在這裡，設定存本專案自己的 `config.json`）；`工作台/server.py` 的對應 API 仍在，`teacher.html` 的 `WORKBENCH` 常數可切換要打哪一邊，預設打自己（同源，避免任何跨來源問題）。

## 階段勾選
- [x] **P0 專案骨架**：SPEC.md、PROGRESS.md、teacher.html 設計骨架（無 emoji）、資料模型定案。
- [x] **P1 學生繳交模組**：`student-submit.js` 可重用（自動掃 data-qid 或自訂 collect）＋`demo-worksheet.html` 示範＋`firestore.rules`。資料模型改扁平 `submissions`。teacher.html 已改讀扁平模型。**待教師部署 firestore.rules 後可端到端測試。**
- [x] **P2 教師端讀取**：teacher.html 由 submissions 推出學習單清單、以 worksheetId 讀繳交、表格＋統計磚＋批改抽屜。（評分動作在 P3。）
- [ ] **P2.5 真實測試**：教師部署規則 → 開 demo-worksheet.html（真檔非預覽）繳交 → teacher.html 應看到該筆。
- [x] **P3 評分引擎＋批改**：server `/api/grade`（標準答案自動核對＋開放題丟 AI，回 autoScore/aiScore/aiFeedback/perItem，**已直接測通**：客觀 50 分、AI 開放題 100 分＋中文回饋）。server 加 CORS＋OPTIONS＋靜態服務 `評分平台/`。teacher.html 批改抽屜接上：逐筆評分、顯示逐題對錯與 AI 回饋、可改最終分、寫回 `submissions`（status='graded'）；工具列「AI 批次評分」整份跑。
- [x] **P3.5 學習單設定面板**：teacher.html「學習單設定」按鈕 → 面板可編標準答案（逐題，多選用「、」）與評分規準（可增刪列）→ 存進 `worksheets/{ws}`；存後評分即套用。
- [x] **P4 名單/匯出/Classroom**（完成，P8 再強化見下）：
  - [x] **P4-a 成績匯出 CSV**：改列年級/班級/學號/正確率/體驗完成度/AI分/最終分/狀態/繳交時間＋UTF-8 BOM，且**只匯出目前篩選的班級**（見 P8）。
  - [x] **P4-b 名單匯入**：三管道（貼上文字／上傳 CSV 或 XLSX／從 Classroom 匯入），寫 `courses/{grade}-c{className}` ＋ `students/{seat}`（見 P8 詳述）。
  - [x] **P4-c Classroom**：後端 `/api/classroom/coursework`、`/students`、`/grades`。前端回寫 modal：選課程→選作業→拉名單→自動對應（**已升級成可用 classroomUserId 精準比對**，見 P8）→送出並發還。
- [~] **P5 Scratch 評分**：後端 `/api/grade-scratch`（.sb3 解 zip 讀 project.json → 盤點精靈/積木/變數/概念）**已測**。前端上傳 UI＋依 rubric/AI 給分＝下輪。
- [x] **獨立專案化**：評分平台成為獨立資料夾——自有 `server.py`（靜態，port 8780）＋`啟動評分平台.bat`（用旁邊工作台的 portable Python，已修正 CRLF/中文路徑問題）＋`README.md`＋`.gitignore`。**連動**：AI/Classroom/金鑰仍走工作台 8770（CORS）；本專案不存金鑰。已煙霧測試通過。**已 `git init` 並完成初始 commit**（`81d91dd`，本機、未推遠端）；**待教師指定遠端 repo 名稱/URL 才能 push**（曾詢問未得到回覆，不擅自建立）。
- [x] **P7 學習單資料標準大改版（教師指定）**：新增權威規範 `引導規範/學習單資料與提交規範.md`（識別列年級/班級/學號數字限制、題型標註 score/experience/open、submissions 資料契約、即時同儕動態 feeds 集合）。**識別模型從「班級/座號/姓名」全面改為「年級/班級/學號」三個數字**（無真實資料，改版無包袱）：
  - `student-submit.js` 重寫：注入識別列（含 localStorage 持久化＋數字過濾）、`autoCollect()` 依 `data-qid`/`data-qtype`/`data-correct` 分類並算 `accuracyRate`/`experienceCompletion`、confirm-before-submit、`StudentSubmit.liveFeed()`（讀寫 `feeds/{ws}/messages`，含搶先簽到匿名解決讀取權限競態）。**已在瀏覽器實測**：identity 收集、score/experience/open 三型收集、統計計算、寫入嘗試皆正確（因規則未部署而預期失敗於 permission-denied，非程式錯誤）。
  - `demo-worksheet.html` 改為三題型示範＋live feed 參考實作。
  - **L01（`materials/五年級上學期/L01.../06_成品.html`）依規範改版並實測**：加識別列（沿用 `wk_identity` key）；8 則投票卡與危害勾選標 `experience`（因這節是體驗課、故意不計分，呼應教學設計意圖）；危害推論短文標 `open`＋新增「同學們的推論」即時留言牆（讀寫同一份既有 db/auth，不重複載入 SDK）；新增「繳交學習單」按鈕（confirm 對話框顯示體驗完成度／開放題填寫狀況→寫入 `submissions`，同步寫一筆到 `feeds`）。**已推送 GitHub**（`d53dfe5..73f07b6`，SSH）。**觀察**：測試時發現 `quizzes/L01` 目前活生生處於「已公布」狀態（教師先前測試後未按還原）——與本次改版無關，但提醒教師記得用 `#admin`→「還原」，避免學生現在打開就看到答案。
  - `firestore.rules` 重寫為完整版：`quizzes`＋`submissions`（含 grade/className/studentId 型別檢查）＋`worksheets`＋`courses`＋新增 `feeds`（留言長度上限、不可編輯、老師可刪）。**這是唯一該貼進 Firebase Console 的檔案**。
  - `teacher.html` 改讀新欄位：`wkLabel()`/`wkSortKey()` 取代 seatNo/studentName 顯示與排序；表格合併「座號/姓名」為單一「學生」欄＋顯示正確率/完成度；CSV 匯出改列年級/班級/學號/正確率/體驗完成度；Classroom 對應表格顯示改用 wkLabel；`gradeOne()` 改只把 `openAnswers` 送 AI（不再誤把投票/勾選丟給 AI「評分」）、最終分優先採用學習單自算的 `accuracyRate`。**已實測**：無 console error，`wkLabel`/`wkSortKey` 行為正確。
  - `SPEC.md` 全面更新（架構圖、資料模型指向新規範、API 表對齊實際路由、§8 決策定案、§9 新增「已知限制」：新身分模型無姓名，Classroom 自動姓名比對對新式提交失效，只能手動指定）。
  - 各規範文件互相加了指向新規範的「延伸」連結，避免未來學習單製作漏看。
- [ ] **P6 工作台整合**：成品階段一鍵綁定學習單/開評分台；rubric 編輯器。
- [x] **P8 教師指定的一批強化**（名單/篩選/評分UX/學習單規範）：
  - **名單匯入三管道**：貼上文字（原有）／上傳 CSV／上傳 XLSX（用 cdnjs 的 SheetJS，用到才動態載入，非事先綁定）／**從 Google Classroom 匯入**——按教師提供的命名慣例「`{年級}{班級2碼} {座號} {姓名}`」（例：`510 01 黃博胤`）自動 regex 解析出年級/班級/座號/姓名，解析不到的整列標橘色讓老師手動填；匯入時把 Classroom 的 `userId` 存進 `courses/{cid}/students/{seat}.classroomUserId`。roster 表單也改成年級+班級數字（不再是自由文字班級名），courseId 規則化為 `g{grade}-c{className}`。
  - **回寫 Classroom 對應升級**：`buildCCMap()` 若目前班級是從 Classroom 匯入（存了 classroomUserId），改用「座號→classroomUserId」精準比對，不必再靠姓名猜；沒有 classroomUserId 的班級才退回姓名比對。解決了先前 SPEC §9 記錄的已知限制。
  - **篩選順序＝先選班級再選學習單**：左欄「班級」變成可點選（`curCourse`），並固定加一個「其他」項，放 grade/className 對不到任何已匯入班級的繳交（`matchCourse()`）。`renderSubs`／`exportCSV`／`batchGrade`／`buildCCMap`／`pushClassroom` 全部改吃 `currentSubs()`（目前篩選出的班級），不再對整份學習單的所有班級一起動作。
  - **AI 評分「兩個獨立計算系統」**：`gradeOne()` 先判斷有沒有開放題（`openAnswers`）——**沒有就完全不呼叫 AI**，直接拿 `accuracyRate` 當最終分，狀態顯示「此份沒有開放題，不需要呼叫 AI」；有開放題才顯示「AI 評分處理中…」。錯誤訊息區分「缺少 AI 設定（尚未填 API Key）」vs 一般失敗。`batchGrade()` 統計「呼叫 AI／直接採正確率／失敗」三種數量，遇到缺 API Key 直接中止並給明確訊息（不會對整批重複噴同一個錯誤）。
  - **Firestore 免費方案容量**：查證官方頁面（1GiB 儲存／50K 讀/日／20K 寫/日／20K 刪/日／10GiB 傳輸/月），單一學校規模遠低於此，已記進 SPEC §9；唯一要注意的是「一次性批次寫入全校成千上萬筆」這種操作要分批。
  - **學習單標準補兩條規則（寫進《學習單資料與提交規範》§5）**：① 每個學習單的 `#admin` 都要有「預覽學生模式」切換（暫時隱藏教師列，不必開新分頁）——**已在 L01 實作**（`previewModeBtn`＋浮動「返回教師模式」鍵）。② 使用者看得到的文字不得洩漏技術/除錯資訊（「Firestore」「規則」「部署」這類詞只能留在 `console.warn`）——**已修正** `student-submit.js` 的 `liveFeed()` 與 L01 的 `initFeed()` 錯誤訊息。
  - **「推送」與「繳交學習單」明確拆成兩個獨立按鈕/動作**（原本推送藏在繳交的副作用裡，沒交卷就看不到同學動態）：L01 的危害推論短文加「📤 推送給同學看」按鈕（只寫 `feeds`），`demo-worksheet.html` 同步加對應示範（用 `StudentSubmit.liveFeed()` 回傳的 `post()`）；規範 §4／§7 都加了這條要求。
  - 全部改動**已在瀏覽器實測**（Classroom 姓名解析 regex 對兩種真實格式都正確、`parseRoster` 正確跳過標題列、`matchCourse`/`currentSubs` 過濾邏輯正確、`gradeOne` 無開放題時不打網路請求且正確採用 accuracyRate、教師端所有新增 DOM 元素齊全、無 console error）。L01 已推送 GitHub（`73f07b6..7571f18`）。評分平台本機 commit 待遠端指定。

## 本輪做了什麼（最新在上）
- **2026-09-08 · 評分平台獨立運作（自帶 AI＋Google OAuth）＋修真正的 fetch 故障根因**：
  - 教師回報「工作台後端也開了，還是 fetch 不到」。**實際診斷**：`netstat` 發現 8770／8780 上各同時卡了好幾個殘留的舊 server 行程（我先前測試時 `kill $(cat pidfile)` 沒有真的殺掉背景的 python.exe 子行程），瀏覽器的請求隨機打到「沒有 CORS 修正」的舊行程上，導致 fetch 間歇性失敗——外觀上就是「fetch 不到」。已用 `taskkill //F //PID` 逐一清乾淨，兩個 port 現在都只剩一個乾淨行程。**教訓**：以後起測試 server 要用 `netstat` 確認真的只有一個行程在聽，不能只信任 kill 有成功。
  - 依教師指示，把 8770 依賴徹底拔掉：**評分平台/server.py 重寫**，自己實作一份完整的 AI 評分（`_llm_call`/`_llm_models`/`grade_call`/`grade_submission`/`_ai_grade`）與 Google OAuth／Classroom（`google_auth_url`/`google_exchange`/`google_access_token`/`google_courses`/`classroom_coursework`/`classroom_students`/`classroom_grades`），設定讀寫走自己的 `config.json`（`google_client_secret`／`grade_key` 這類金鑰**已加進 `.gitignore`**，且確認從未進過 git 歷史）。OAuth redirect 改成 `http://127.0.0.1:8780/oauth/callback`。
  - `teacher.html`：`WORKBENCH` 常數改成空字串（同源，打自己的 8780），徹底消滅 CORS 疑慮；「AI 評分串接設定」modal 擴充成「設定」，同時放 AI（反向代理/Key/模型/測試）與 Google Classroom（client_id/secret/授權/清除授權/測試連線＋診斷），對應規範：教師要求「就設定裡面放 classroom 和 ai 的」。
  - **暫緩 P5 Scratch**：依教師指示移除本輪之前加的 Scratch 評分 UI（按鈕/modal/JS），保留後端 `/api/grade-scratch` 留在工作台不動，之後要做再重新接。
  - 已實測：新 server.py 語法通過；`/api/settings`、`/api/google/auth-url`（含 client_id 情境）、`/api/diagnostics` 直接 curl 測試正確；瀏覽器端到端測試 teacher.html 的「設定」modal 同源讀取成功、診斷按鈕正確回報未設定狀態，全程 0 個 console error。
- **2026-09-08 · P8 教師指定強化批（名單三管道＋Classroom精準比對＋班級篩選＋AI兩系統＋學習單規範補強）**：詳見上方 P8 條目。額外查證：Firestore Spark 免費額度（1GiB/50K讀/20K寫/20K刪/10GiB傳輸）對單校規模綽綽有餘。中途修正一個誤判——「預覽學生模式」按鈕一開始被我錯放進 teacher.html，教師指正後改放回學習單自己的 `#admin` 列（正確位置）。L01 已推送 GitHub。
- **2026-09-08 · P7 學習單資料標準大改版**：詳見上方階段勾選 P7 條目。摘要：新規範 `學習單資料與提交規範.md` 定案識別列（年級/班級/學號，數字）＋題型標註（score/experience/open）＋資料契約＋即時同儕動態；`student-submit.js`／`demo-worksheet.html`／`firestore.rules`／`teacher.html` 全面對齊並實測（瀏覽器端到端跑過 identity→collect→confirm→write 全流程，唯一失敗點是預期中的 permission-denied）；L01 依規範改版並**已推送 GitHub**（`73f07b6`）；**評分平台 `git init` 完成初始 commit，尚未有遠端可推**（此問題已詢問教師一次，未獲回覆，故不擅自建立 repo）。過程中修了兩個真實 bug：(1) `autoCollect` 對「data-qid 在外層 div、內層才是 input/textarea」的情況會誤抓 `textContent`；(2) 未作答的 checkbox/radio 給 Firestore 寫入 JS `undefined` 會直接丟例外（Firestore 不接受 undefined，需轉 null）——兩者都已修正並在瀏覽器實測驗證。
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
1. **P6 工作台整合**：工作台成品階段一鍵「登錄為學習單」（把 06_成品 網址/標題/分類寫進評分平台的 worksheets）。
2. **P5 Scratch 評分（擱置中，教師指示暫緩）**：之後要做的話，後端 `/api/grade-scratch` 已在工作台實作測通，只需搬到評分平台自己的 server.py（比照這輪搬 AI/Classroom 的做法）＋接前端上傳 UI。
3. **其他既有學習單依 P7 規範改版**（L01 已完成，之後每份新學習單都直接照《學習單資料與提交規範》做，不必再問）。
4. 待教師：**部署 firestore.rules**（唯一真正阻擋端到端測試的事）＋**在 Google Cloud Console 把 `http://127.0.0.1:8780/oauth/callback` 加進 OAuth 用戶端的重新導向 URI**（獨立運作後 redirect 從 8770 換成 8780，需要這一步）＋**指定評分平台的遠端 repo**（名稱/URL，我才能 push；已本機 commit 隨時可推）。

## 已知限制（見 SPEC §9）
- 新身分模型（年級/班級/學號）無姓名時，Classroom 回寫的自動姓名比對對新式提交無法自動配對，只能在 modal 手動指定；**有 classroomUserId 的班級（從 Classroom 匯入）已可精準比對，不受此限**。

## 注意
- 評分平台**已獨立運作**：AI Key／Google client_secret／token 存在 `評分平台/config.json`（已加進 `.gitignore`，確認未進 git 歷史）；`teacher.html` 只放 public firebaseConfig（Firebase Web API Key 本來就不是密鑰，官方文件說明存取控制交給 Security Rules）。工作台仍保有相同功能的 API，`WORKBENCH` 常數可切換要打哪邊。
- 教師端讀 submissions 需 Email/密碼登入（isTeacher）；學生匿名只能 create 自己那筆。
- 每完成一個可視成果，用 SendUserFile 給教師看方向。
