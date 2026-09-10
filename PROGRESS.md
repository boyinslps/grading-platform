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
  - [x] **P4-d 批量匯入全部班級**：一次掃全部 Classroom 課程 → 自動分班 ＋ 例外清單（可當場補齊/略過）→ 分段 batch 寫入（見下方第 12 輪）。
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
- **2026-09-10 · AI 批次評分改成整班一次呼叫＋新增評語欄（教師指定）**：教師發現「已評分」標籤最後一字被擠到下一行，順手確認 AI 批次評分是不是逐筆呼叫 AI——**答案是：舊版真的是逐筆**（`batchGrade()` 對每筆繳交各自呼叫一次 `gradeOne()`→`/api/grade`），這輪整個換掉：
  - **UI 小修**：`.tag{white-space:nowrap}`——這一個屬性就解決了「已評分」擠斷行。
  - **新後端 `POST /api/grade-batch`**（`_ai_grade_batch()`＋`grade_batch()`）：整班「有開放題」的學生一次組進同一個 prompt，每人一段用短代號 `k0`/`k1`… 標記（不把 Firestore doc id 直接塞進 prompt），要求 AI 回一個以代號為鍵的 JSON 物件；伺服器收到後把代號換回真正的 submission id 逐一比對——**這是確保「回傳格式能準確對應到學生」的關鍵**：鍵名範圍固定由伺服器決定，AI 只要照抄，就不會有对不上的問題。AI 漏答或分數不是合法數字的學生歸進 `missing`（不補假分數），分數會 clamp 在 0–100。超過 40 人自動分段送出，但每段仍是整批呼叫，不會退化成一人一次。
  - **前端 `batchGrade()` 整個重寫**：先分成「有開放題」／「無開放題」兩組，無開放題的完全不進 AI 呼叫、本地 `calcScore()` 直接算完；有開放題的**整個班級只打一次** `/api/grade-batch`。AI 沒回應的學生保持未評分（不寫分數、狀態不變 `graded`），結果訊息會明講「X 位 AI 沒有回應，可再跑一次或手動評」。所有更新最後用 Firestore **一次 `batch()` 寫入**（不是逐筆 `.update()`，450 筆一段沿用既有 `commitChunked` 慣例）。
  - **新增「附評語」勾選框**（AI 批次評分按鈕旁）：勾了才在 prompt 多要求 `feedback`（省 token 也省時間），回來的評語存進既有的 `submissions.aiFeedback` 欄位；教師端表格新增「評語」欄（AI 分數旁），過長用 `title` 顯示完整內容。**目前評語只到教師端＋該學生自己的 Firestore 文件**，還沒有推到 Google Classroom（API 沒有可寫的私訊評語欄位，只能寫數字分數——平台限制，跟先前「Classroom 一定發動態時報」是同一類誠實說明）；要讓學生在學習單頁面本身看到評語，需要另外擴充資料契約，本輪未做，已寫進 SPEC §7-e 留給下一輪判斷要不要做。
  - **驗證**：伺服器端直接 `import server` 跑 `_ai_grade_batch`（不需真的 AI Key，mock `grade_call`）——全部成功＋評語正確對應、AI 漏一位時該位進 `missing` 不冒充分數、AI 回傳非 JSON 時整批 `ok:false` 附錯誤訊息、分數異常值（字串"105"／負數／非數字）分別被 clamp 或判定失敗、85 人自動分成 40/40/5 三段且每段仍是整批呼叫（用假 `grade_call` 數了每次呼叫涵蓋的人數）。前端用假 `fetch`＋假 `db` 測過三種情境（全部成功／AI 漏一人／整批 AI 失敗），確認只送「有開放題」的人給 AI、正確依 key 寫回分數與評語、AI 失敗或漏答時對應學生維持未評分不受影響、無開放題的學生完全繞過 AI。真實瀏覽器截圖確認「評語」欄與「附評語」勾選框正確顯示、`title` 提示完整評語文字、無 console error。
  - **意外發現**：目前 `config.json` 的 AI 金鑰仍是先前回報的 401 invalid key 狀態（尚未修復），所以這輪驗證全部用 mock 繞過真實 AI 呼叫；等教師換好金鑰後，建議先用一個小班實際跑一次「AI 批次評分」確認真實回應格式跟 mock 假設的一致。
- **2026-09-10 · 新增深色模式**：`teacher.html` 加頁首「深色/淺色模式」切換鈕。做法：
  - 把散落在 CSS 與 JS 產生字串裡的**全部**寫死 hex 顏色（表格表頭底色、批量匯入例外列橘底、正確/錯誤邊框、最終分數框邊框等，共約 20 處）改成 CSS 變數引用；新增 `--surface2`／`--accent-border`／`--ok-border`／`--warn-border`／`--score-border`／`--exc-bg`／`--shadow`／`--drawer-shadow` 幾個之前沒有對應變數的 token。
  - 深色調色盤透過 `@media (prefers-color-scheme:dark):root:not([data-theme="light"])` 與 `:root[data-theme="dark"]` 兩處定義（沒手動選過跟系統、選過的話手動優先），按鈕點擊即時切換（純變數重算，不需重整）並存 `localStorage`（key `wk_theme`）。`<head>` 最前面加一段同步小 script 先讀存好的偏好設定，避免翻頁閃一下淺色再變暗。
  - 額外補了 `input,select,textarea{background:var(--surface);color:var(--ink)}` 全域規則——很多表單元件是 JS 內嵌 style 只設了 border 沒設底色，深色模式下不補這條會維持瀏覽器預設白底格格不入。
  - **驗證**：瀏覽器內直接切換測試——登入畫面、學習單設定（含分數計算的三個輸入框與逐題配分表）、繳交表格（含「已評分」綠色標籤）、批改抽屜的分數分解框、批量匯入的例外橘底列，深色模式下全部正確換色、對比清楚；即時切換不需重整；重整後偏好正確保留（無 FOUC）；來回切換兩次無 console error。
  - 剩下的 hex 只留在 `:root` 的變數定義本身（淺色一組、深色兩處各一組，每個顏色恰好各出現一次），沒有任何寫死顏色散落在規則或 JS 字串裡了。
- **2026-09-10 · 把這幾輪的決策與踩過的坑寫回引導規範（教師指定）**：程式改完但規範沒跟上＝下一份學習單還是會重犯，所以把本輪所有變更整理成**通則**寫進 `../引導規範/`（那個資料夾不在版本控制內，這裡留紀錄）：
  - **《學習單資料與提交規範》§2**：補一段「**『不計分』是指不進正確率，不是不影響成績**」——`accuracyRate` 的分母確實只有 `score` 題，但評分平台的最終分把 `score`＋`experience` 合在一起扣分，所以體驗題答錯照樣扣分（L01 就是全 experience 卻要「全對 100、錯一題 99」）。這個語意落差很容易讓之後標題型時判斷錯，特別寫清楚。
  - **《學習單資料與提交規範》§3**：把 `isCorrect` 從「參考欄位」升級成**硬性契約**——它是教師端逐題扣分的唯一依據，所以沒作答也要輸出該題且判成 `false`（省略＝空著不扣分）、多選題要自己定義「怎樣算對」不要把判斷推給教師端、`given` 沒值要寫 `null`（Firestore 不接受 `undefined`）。
  - **《學習單資料與提交規範》§4**：加「**複合查詢要先建索引，否則留言牆是靜默壞的**」——`where('qid','==').orderBy('at')` 缺索引會回 `failed-precondition`，但依規範學生只看得到友善文案，畫面上分不出「還沒人留言」與「查詢失敗」；驗收時要自己送一則測試留言。這是本輪實測 L01 時從 console 抓到的既有問題。
  - **《學習單資料與提交規範》§5**：整節改寫成四條——①「預覽學生模式」＝**真的清快取＋去 `#admin` 重載**（含為什麼：只藏工具列會看到老師測試到一半的畫面，驗收不到學生第一次進來的樣子）；②**登入一次就好、且不可被匿名登入蓋掉**（兩條一起才有效）；③**標準答案只有一個來源＝學習單自己**，評分平台不再重複維護；④原本的「不對學生洩漏技術資訊」順延為第 4 條（§7 自檢的交叉引用一併改成 §5.4）。
  - **《互動教材進階規範》新增 §2.6「登入狀態：一個瀏覽器只有一個 currentUser」**：把這輪的根因寫成通則——`signInAnonymously()` 不是「補一個匿名身分」而是**取代 currentUser 並覆寫持久化 session**；判斷登入狀態一律用 `onAuthStateChanged`（剛 `firebase.auth()` 後同步讀 `currentUser` 必為 `null`）；登入成功後要做的事抽成共用函式，讓「沿用既有 session」與「重新登入」兩條路徑共用收尾。附兩段可直接抄的程式碼。
  - **《工作流程規範》§2**：新增硬性契約「**`L##` 的編號＝第幾週**」——工作台簽到題模板與評分平台回寫比對都直接依賴它，並說明跳週/補課時「兩邊一致就不會錯，會錯的是各編各的」。
  - **《工作流程規範》新增 S10-b「發布本週的 Classroom 簽到題」**：一週只開一份簽到問題、該週所有學習單成績都回寫到那一份的完整流程，含順序建議與**平台限制的誠實說明**（Classroom `PUBLISHED` 一定會發動態時報通知，API 與 Classroom 自己的介面都沒有安靜發布；`DRAFT` 雖然不通知但學生也看不到分數，等於失去回寫意義；同一份簽到題只會建立一次，所以每週最多洗版一次）。
  - 兩份規範的**自檢清單**都補上對應項目（isCorrect 是否每題都有、預覽是否真的清快取、學生分支有沒有無條件匿名登入、登入過還會不會跳密碼框、留言牆有沒有實際送過測試留言、`L##` 是否對得上週次）。
- **2026-09-10 · 修正 L01「返回教師模式」仍要求登入的根因**：教師實測回報上一輪的登入持久化修正沒生效。追出真正原因——`boot()` 的非 admin 分支一律呼叫 `auth.signInAnonymously()`，而這正是「預覽學生模式」重整後會走的路徑；`signInAnonymously()` 會把已登入帳號直接換成匿名使用者，等於蓋掉 Firebase 本機持久化的教師 session，「返回教師模式」當然只看得到剛蓋掉之後的匿名狀態。改成該分支也先用 `onAuthStateChanged` 確認真的沒登入過才簽名匿名；已有登入狀態（教師帳號或先前的匿名 session）就直接沿用不動它。已用本機臨時伺服器確認整段 IIFE 仍正常解析執行（signInAnonymously 路徑本身照常運作，feed 讀取失敗是既有、無關的 Firestore 複合索引問題，不是本次改動造成）。已同步發布並推送（`2478be9`）。
- **2026-09-10 · Classroom 回寫改依「週次」比對（教師指定，跨兩個專案）**：教師想法——每週在 Classroom 開一份「簽到」單選題（工作台發布），之後這週不管有幾份學習單，回寫成績都寫進同一份簽到題，不要每份學習單各自長一份作業。
  - **工作台**（`工作台/web/index.html`＋`server.py`，這個專案本身沒有版本控制，不進 git）：「發布到 Classroom」的 `#pubType` 新增「問題」選項（`MULTIPLE_CHOICE_QUESTION`）。切到這個類型會自動套模板：標題＝`第{X}週 {單元名稱}`（X 從節次資料夾 `L0X` 推出，`weekNumOf()`）、選項預設「簽到」（沿用原本的「內容文字」欄位，切成問題類型時 label 換成「選項（每行一個）」）。後端 `classroom_publish()` 加 `question` 分支：把文字方塊每行拆成一個選項，組 `multipleChoiceQuestion.choices` 送出。已用真實 TREE 資料實測：選 L01_假消息與目的辨識、切換問題類型 → 標題自動變「第1週 假消息與目的辨識」、選項欄變「簽到」、下方提示文字正確顯示；無 console error。
  - **評分平台**（`teacher.html`）：新增 `weekOf()`——從 `curWsCfg.url`（`.../g5/L01/`）或學習單 id（`g5-L01`）抓 `L` 後面數字當週次。`ccCourse` 的 change handler 改成兩層比對：**先**找該課程裡標題以「第X週」開頭的作業（工作台發布的週次簽到題）命中就直接選定＋提示「已依第X週比對到…」；沒週次或找不到才**退回**舊式的學習單標題比對；兩者都沒有才預選「建立新作業」，且提示文字會建議教師「先到工作台發布本週的簽到問題」而不是直接默默建一份不相關的新作業。
    - **驗證**：合成假課程清單（`第1週`／`第10週`／舊式同名標題三種作業）直接呼叫比對邏輯——確認 week=1 只命中「第1週」不會誤命中「第10週」（`^第0*1週` 正則不會前綴誤配）、week=10 正確命中「第10週」、抓不到週次時正確退回標題比對。`weekOf()` 對 `curWsCfg.url` 含 `L01` 與學習單 id 含 `L2` 都正確抓到週次。無 console error。
  - **L01 學習單登入持久化（教師指定）**：`materials/五年級上學期/L01_假消息與目的辨識/06_成品.html`（已同步發布到 `工作台/.pub_repo/g5/L01/index.html` 並 push）——原本 `teacherOnline()` 每次都跳兩個 `prompt()` 要教師重輸帳密，即使 Firebase 本機其實已經有登入過的 session。改成先 `auth.onAuthStateChanged` 等一次目前狀態，是**非匿名且有 email** 的使用者（代表本機已持久化登入過）就直接沿用、跳過兩個 prompt；沒有才照舊詢問帳密。抽出共用的 `wireTeacherUI(email)`，兩條路徑（沿用既有 session／重新登入成功）都呼叫它接上上傳答案/公布/還原/即時統計等按鈕，避免重複程式碼。
    - **驗證**：本機起了一個臨時靜態伺服器直接跑這份 HTML；已確認整段 IIFE（含新程式碼）解析執行無誤（`previewModeBtn`／`backToTeacher` 等既有功能仍正常）；自動化瀏覽器不支援真的 `prompt()`，所以「已登入直接略過」這條分支沒有用真帳密端到端跑過，但邏輯與《評分平台/teacher.html》既有的 `onAuthStateChanged` 模式一致（那邊已驗證多輪）。**待教師實機確認**：登入一次後，重新整理或按「返回教師模式」不會再跳出帳密視窗。
  - **預覽學生模式（上一輪已改）**：本輪追加確認——L01 已同步推上 GitHub（`2ef786d`），此處不重複記錄。
- **2026-09-09 · 分數計算＋設定面板整合（教師指定）**：兩件事都在 `teacher.html`。
  - **分數計算**：學習單設定原本逐題手填「標準答案」的表格**整段刪掉**——標準答案統一在學習單自己的 `#admin`（面板只留一顆連結）。取而代之是可調的分數公式：`worksheets/{ws}.scoring={base,deduction,openWeight,itemPoints}`，預設總分 100、每題答錯扣 1 分、有開放題時保留 10 分給 AI（其餘才是非開放題滿分）；`itemPoints` 可逐題覆寫扣分。新函式 `calcScore(sub,cfg,aiScore)` 把 `scoreAnswers`+`experienceAnswers` 併成一份 `isCorrect` 清單去算扣分，`gradeOne()`／`batchGrade()` 全面改用它（原本是簡單的「正確率與 AI 分數平均」，教師沒有調整空間）。批改抽屜的 `renderCalcBox()` 顯示分解：非開放題幾分＋扣了哪幾題、AI 開放題幾分＋回饋。
    - **驗證（純函式，直接在瀏覽器 console 呼叫，不需登入）**：對照教師原話造測資——8 題體驗全對、無開放題 → 100；錯 1 題 → 99；同一份加開放題（AI 給 80）→ 90 分非開放題池、錯 2 題扣 2 分 → 88，AI 88 部分 8 分 → 合計 96。三個都算對。另測四個邊界：逐題覆寫（v3 扣 5 分 → 100−5=95 正確）、全開放題（AI 拿走整個 100 分）、完全無題目（`total=null`，交給老師手動輸入）、扣分超過總分應 clamp 在 0（8 題全錯×20分扣分 → 0 分不是負的）。全部符合預期。
  - **設定面板整合**：頁首「AI 設定」按鈕改名「設定」；`aiModal` 內加分頁（AI 評分／Google Classroom／名單匯入），「名單匯入」下再分三個子分頁（貼上／上傳、Classroom 單班、批量匯入全部班級）——原本工具列三顆獨立按鈕（`importRoster`/`importClassroom`/`importClassroomAll`）連同各自的 `.gate` modal 全部拆掉，內容原封不動搬進分頁，只拿掉各自多餘的「取消」按鈕（用 modal 共用的「關閉」即可）。子分頁懶載入：切到「Classroom 單班」才重抓課程清單，切到「批量匯入」只有第一次自動掃描（`_cbScanned` 旗標），之後靠「重新掃描」按鈕，避免每次切分頁都對 22 門課打一輪 API。
    - **驗證**：`showSetTab`/`showImpSubTab` 直接呼叫測過分頁顯示/隱藏狀態正確；`showImpSubTab('classroomAll')` 觸發真實掃描（讀到 219 位/12 班，與批量匯入功能上一輪的結果一致，證明搬遷後邏輯沒壞）；`openClassroomImport()` 觸發後 22 門課正確載入下拉。冷啟動整頁重新整理無 console error。
    - **意外發現並修正（非本輪引入）**：測試過程發現 `config.json` 的 `grade_endpoint` 又被瀏覽器自動填成教師 email（`autocomplete="off"` 沒能完全擋住），是上一輪修過的同一個 bug 復發——已用 `/api/settings` 改回正確值 `https://gcli.ggchan.dev/v1`；改完後 `/api/grade-models` 回 401 invalid API key，這是金鑰本身的問題（不是端點問題），需要教師自行確認金鑰是否過期/更換，本輪未處理。
- **2026-09-09 · 回寫 Classroom 免先建作業（教師指定）**：原本流程卡在「作業下拉只列現有作業，此課程沒有作業就走不下去」，教師必須先去 Classroom 手動開一份。改成**以學習單標題自動對應／自動建立**：
  - 後端新增 `classroom_create_coursework()`＋`POST /api/classroom/coursework`：先 `classroom_find_coursework()` 用正規化標題（去空白、忽略大小寫）找同名作業，**找到就沿用**、找不到才建（`workType:ASSIGNMENT`、`state:PUBLISHED`、`maxPoints` 由 UI 給、`materials` 附學習單網址）。建前再找一次是刻意的——前端清單過期或連按兩次都不會重複建立。
  - `classroom_grades()` 加重讀：剛建立的作業，Classroom 生成每位學生的 studentSubmission 有短暫延遲，讀到空的就等 2 秒重讀一次，否則會整批回報「找不到該生的繳交」。
  - 前端 `ccModal`：選課程後自動比對學習單標題 → 對到就選那份並帶入其滿分（綠字提示）；對不到則預選「建立新作業：{標題}」（灰字說明送出時才會建立）。新增「滿分」欄（預設 100）。按「回寫成績」時若是建立模式，先 POST 建作業拿 id 再回寫，完成後自動重整作業清單（下次就對得到同名那份）。
  - **順手修掉一個既有 race**：`ccCourse` 的 change 同時平行抓「作業」與「名單」，`buildCCMap()` 可能在 `CC.students` 還沒回來時就跑，導致自動對應顯示 0 / N。改成 `Promise.all([作業, 名單])` 後才建對應表。
  - **驗證（唯讀，未在真實 Classroom 建立任何作業）**：對真實課程「彈-成功自造機 405」實測——標題 `電腦課秩序規則小測驗` → 自動選中該作業（id 872782270145）、滿分帶入 100、綠字提示正確；標題多加空白 `  電腦課秩序 規則小測驗 ` → 仍正確對到（驗證正規化比對）；標題 `假消息與目的辨識` → 預選 `__create__`、下拉同時列出兩份現有作業可改選、名單 23 位正確載入。後端空參數回 `{"ok":false,"error":"缺 courseId 或作業標題"}` 不炸。無 console error。
  - **另修**：又發現 8780 上有 3 個殘留 python 行程（4924/12860/16120），已全部 taskkill 後只留一個乾淨行程（2480）。這是第二次踩到，netstat 檢查已成慣例。
- **2026-09-09 · 批量匯入全部班級（P4-d，教師指定）**：teacher.html 工具列加「批量匯入全部班級」→ `cbModal`。`cbScan()` 打 `/api/google/courses` 取全部課程，**逐課依序**（不併發，避免打爆 Classroom 配額）打 `/api/classroom/students`，用既有 `parseClassroomName()` 拆「年班 座號 姓名」，邊掃邊顯示「讀取名單 3 / 12：五年級電腦」。結果分兩區呈現：上方「將建立／更新的班級」摘要（班級／人數／來源課程），下方**例外清單**（課程／原始名稱／原因／可編輯的年級·班級·座號·姓名／略過勾選）。
  - **例外三來源**：①姓名不合命名格式；②同班座號撞號（`seen[cid#seat]`，後者標成例外並指出被誰佔用）；③整個課程讀取失敗或沒學生（以課程為單位顯示在掃描結果那行）。
  - **即時回饋**：例外列一改就 `cbRecalc()`——補齊的立刻併進上方班級摘要、匯入鈕文字同步變成「匯入 N 位（M 班）」、標頭顯示「待補齊 x、已略過 y、已補好 z」；勾略過的列淡出。撞號時 `#cbNote` 出橘字警告。補不齊的按匯入時自動跳過（不擋流程）。
  - **分段寫入**：新增 `commitChunked(ops,onProgress)`，因 Firestore 單一 batch 上限 500 筆，全校名單必超過；以 450 筆為一段依序 commit 並回報「匯入中… 900 / 1350」。
  - **對真實名單做 dry run 後修正解析器（重要）**：實際掃過 22 門課才發現校內 Classroom 命名**多數沒有在座號和姓名之間留空白**（`506 03陳小明`），舊 regex 一律判為例外。改成分層解析：A `506 03陳小明`／`506 03 陳小明`、B `陳小明 506 13`（姓名在前）、C `年605 20 陳小明`（去掉非數字前綴後套 A），並先做全形數字/空白轉半形。**實測成效：自動解析 158 → 219 位、10 → 12 班。**
  - **課程名稱補班級**：名字完全沒帶學號時（社團課多是「陳同學」），從課程名稱末尾的三碼班級（「彈-成功自造機 406」→ 4年6班）預填年級/班級，例外列只剩座號要補。真實資料 21 筆例外全部都被預填到只差座號。
  - **同人多課不算衝突**：同一學生同時在電腦課與社團課出現，座號鍵會撞到；規則改為「同座號且姓名相同 → 靜靜合併，不進例外」，只有**同座號不同名**才列例外，避免例外清單被重複名單灌爆。
  - **驗證**：瀏覽器實測——注入 6 筆合成名單（含 1 筆格式不符、1 筆撞號）驗出分組 `g5-c10:2 / g5-c1:2 / g6-c3:1`、例外原因文字正確；再模擬教師操作（把「陳大同」補成 5年1班20號 → 併回摘要、匯入數 5→6；把撞號的張三勾略過 → 回到 5、警告消失、該列 opacity .45）。版面在 1280px 下量測：面板 900、表格 850、每列單行 40px 不擠壓，窄視窗改橫向捲動（表格 `min-width`）。無 console error。
  - **真實資料端到端驗證（唯讀，未按匯入）**：瀏覽器直接跑 `cbScan()` 掃 22 門真實課程 → 「匯入 219 位（12 班）」、例外 21 筆（全部已預填年班、只差座號）、11 門課因「課程內沒有學生」列在課程層級異常。與 Python 端獨立 dry run 的數字完全一致。解析器單元驗證：A/B/C 三種寫法＋全形＋原本的 `510 01 黃博胤` 皆正確，`陳同學`／`4050 07段硯翔` 正確回 null。無 console error。
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
