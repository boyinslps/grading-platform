# 評分平台 · 規格書（SPEC）

> 學生繳交互動學習單 → 資料庫 → 教師端以班級為單位進行 AI／標準答案評分與成績管理。
> 本檔是**契約**；每次施工前先讀這裡與 `PROGRESS.md`，完成後更新 `PROGRESS.md`。

## 0. 目標與原則
- **目的**：協助教師「精準、快速」進行課堂評量與成績管理。
- **對象**：教師（管理端）＋ 學生（作答繳交端）。
- **介面**：教師端是**專業工具**——乾淨、資訊密度高、**不使用 emoji**（emoji 只屬於給小學生的互動教材）。學生端沿用既有互動教材風格。
- **獨立運作（2026-09-08 教師指定）**：評分平台**自帶**一份 AI 評分後端與 Google Classroom OAuth 授權（見 `評分平台/server.py`），設定存在**本專案自己的** `評分平台/config.json`，不依賴「工作台」（8770）也能完整運作。教師端「設定」面板同時管兩者。
- **仍可選擇串聯工作台**：`teacher.html` 的 `WORKBENCH` 常數留了切換點——預設 `""`（同源，打自己 8780 後端）；若想改成集中用工作台管理設定，改成 `"http://127.0.0.1:8770"` 即可（工作台那邊的對應 API 仍在，見 `工作台/server.py`）。
- **設計脈絡**：學生端只負責「把答案完整送進資料庫」；所有評分與成績邏輯集中在教師端＋server，避免答案／評分規則落在學生看得到的地方。

## 1. 系統架構
```
學生互動 HTML（materials/…/index.html）
   └─(繳交)→ Firestore  submissions/{wsId}__{grade}-{className}-{studentId}
                         ▲                         │
教師管理端 評分平台/teacher.html ─────────────────┘ (讀 submissions、寫回 score/feedback)
   └─(AI評分 / Classroom匯入匯出/回寫)→ 評分平台/server.py 自己的 API（8780，持自己的 config.json）
      （WORKBENCH 常數可切換改打工作台 8770，非必要）
```
- **Firestore**：唯一的繳交／成績資料庫（client SDK，student 匿名、teacher Email/密碼）。
- **teacher.html**：讀 Firestore 呈現＋批改；特權動作打同源（8780）的 API，預設不需要工作台。
- **評分平台/server.py**：AI 評分（`/api/grade`）、Google OAuth（`/api/google/*`、`/oauth/callback`）、Classroom（`/api/classroom/*`）、`/api/fetch-title`；設定讀寫 `/api/settings`（存本專案自己的 `config.json`，內含 `google_client_secret`／`grade_key`，**已加進 `.gitignore`，絕不上傳**）。

## 2. Firestore 資料模型
> **權威定義在 `../引導規範/學習單資料與提交規範.md`**——識別欄（年級/班級/學號）、題型標註（score/experience/open）、`submissions` 文件的完整欄位形狀都在那份規範。這裡只列集合總覽，避免兩處定義漂移。

```
submissions/{wsId}__{grade}-{className}-{studentId}   學生繳交（見學習單資料規範 §3 完整欄位）
worksheets/{wsId}                        學習單設定（老師管理） { title, category, url, summary?, scoring?, questions?（開放題題目規格，見 §7-j）,
                                            verdicts?（條件查核判定紀錄，見 §7-j）, rubric?（舊式整份規準，儲存新設定時移除）, answerKey?（舊式，見 §7 分數計算） }
courses/{grade}-c{className}             班級名單（老師管理） { grade, className, name:"{grade}年{className}班", source:'manual'|'classroom',
                                            gradingAnchors?:{wsId:{qid:{"4","2","1"}}}（班級相對分級的錨點，見 §7-j）,
                                            students/{seatNo}:{seatNo, name, classroomUserId?} }  // classroomUserId 有值時，Classroom 回寫可精準比對，不必猜姓名
feeds/{wsId}/messages/{autoId}           開放題即時同儕動態（見學習單資料規範 §4） { qid, text, tag, at }
quizzes/{wsId}                           （L01 沿用）老師控制的「公布/還原」即時同步，與 submissions 是兩個獨立機制，見《互動教材進階規範》§2
```
- **為何扁平**：Firestore 的 collection 查詢**不會回傳「只有子集合、本身不存在」的幽靈父文件**；若把繳交放 `worksheets/{ws}/submissions`，教師端就列不出還沒被老師建過設定的學習單。改用扁平 `submissions`＋`worksheetId` 欄位，教師端由繳交資料直接推出學習單清單。
- **doc id**＝`{worksheetId}__{grade}-{className}-{studentId}`：同一人重繳覆蓋自己那筆。三個識別欄皆為數字，不採「班級＋座號＋姓名」——見資料規範 §1 的理由。
- **評分兩路（兩個獨立計算系統，不是一步流程）**：`score`／`experience` 題由頁面自己逐題算出 `isCorrect`（客觀正解，見資料規範 §3 `scoreAnswers`/`experienceAnswers`）；`open` 題送 AI 得 `aiScore`＋`aiFeedback`（走 `/api/grade`）。**沒有開放題時教師端完全不呼叫 AI**。兩路的分數怎麼合成 `totalScore`，由教師在「學習單設定」的**分數計算**設定決定，見 §7-d。
- **規則**：見同層 `firestore.rules`（含 L01 quizzes、submissions、worksheets、courses、feeds）。

## 3. Firestore 安全規則
> **完整內容見同層 `firestore.rules`**（可直接複製貼到 Firebase Console 發布），涵蓋：`quizzes`（L01 揭曉同步）、`submissions`（學生繳交，本人可寫、老師可讀寫）、`worksheets`（老師管理）、`courses`（名單）、`feeds`（同儕留言，本人可寫自己的、老師可刪）。
- `isTeacher()`＝`request.auth.token.email == "boyin0304@slps.tn.edu.tw"`（沿用 L01）。

## 4. API（評分平台/server.py，8780，自己的 config.json）
| 路由 | 功能 |
|---|---|
| GET/POST `/api/settings` | 讀寫本專案設定：`grade_provider/endpoint/key/model`（AI）、`google_client_id/secret`、`google_token`（授權後自動存） |
| POST `/api/grade` | 單筆（批改抽屜）：收 {answers, answerKey?, questions, bonusQids, openQids, overview, verdicts, anchors, rubric?(舊)} → 回 {aiScore, aiMax, scores, bonusScore, bonusScores, aiFeedback, details, flags, verdicts, perItem[]}。與批次共用評分引擎（§7-j） |
| POST `/api/grade-batch` | **老師按一次評完整班**：收 {items:[{key,answers}], questions, bonusQids, openQids, overview, verdicts, anchors} → 回 {results:{key:{score,scores,aiMax,bonusScore,bonusScores,feedback,details,flags}}, missing, verdicts, anchors, error}。後端逐題組 prompt（同一題全班作答一起評）、各題平行呼叫，見 §7-j |
| GET `/api/grading-spec` | 讀學習單網頁內嵌的評分設定（`id="grading-spec"` 的 JSON，見《學習單資料與提交規範》§2-e）→ 回 {questions, summary, scoring} |
| POST `/api/gen-grading-spec` | **AI 讀學習單產生開放題評分設定**：收 {url, title, summary, questions:[{qid, bonus, prompt, points, samples}]} → 讀網頁（去掉 head／style／svg，題目附近文字另外擷取）→ 回 {questions（同 §7-j 題目規格）, summary, missing}。見 §7-k |
| GET `/api/grade-models` | 列 AI 可用模型 |
| GET `/api/fetch-title` | 讀某網址 `<title>`（新增學習單時自動帶標題） |
| GET `/api/google/auth-url` | 產生 Google 授權連結（redirect 指向本專案 `:8780/oauth/callback`） |
| GET `/oauth/callback` | 換 token、存進 config.json |
| POST `/api/google/logout` | 清除已存的 Google token |
| GET `/api/google/courses` | 列教師的 Classroom 課程 |
| GET `/api/classroom/coursework` | 列某 Classroom 課程的作業 |
| GET `/api/classroom/students` | 列某 Classroom 課程名單（需 `classroom.rosters.readonly` scope） |
| POST `/api/classroom/coursework` | **依標題確保作業存在**：先找同名作業，找不到才建立（PUBLISHED、全班指派、附學習單連結）→ 回 {id, created} |
| POST `/api/classroom/announce` | 在 Classroom 課程訊息串發公告 {courseId, text}（繳交紀錄的缺交名單；需 `classroom.announcements` 權限）|
| POST `/api/classroom/grades` | 回寫分數到指定 courseWork（patch draft+assigned 後 `:return`）；讀不到 studentSubmissions 時等 2 秒重讀一次（剛建立的作業有生成延遲） |
| GET `/api/diagnostics` | AI／Google 連線狀態快覽 |
| GET `/api/timetable` | 讀課表（節次時間、星期×節次→班級、每班本週學習單）；沒有檔案時回一份預設節次時間 |
| POST `/api/timetable` | 寫課表到本專案的 `timetable.json`（格式不對的節次／格子會被丟掉，不會寫進去）|
- 名單匯入（CSV/貼上/XLSX）與成績 CSV 匯出**純前端**處理（見 `teacher.html`），不走 server。
- `/api/grade-scratch`（Scratch 盤點）與 `/api/git-publish`（發布網站）**只存在工作台/server.py**，評分平台目前不需要這兩個（P5 Scratch 評分擱置中）。

## 5. 學生端「繳交」模組（可重用）
- 規格詳見 `../引導規範/學習單資料與提交規範.md`；實作在 `student-submit.js`（`StudentSubmit.init()` 自動注入識別列＋繳交鈕）。
- 頁面最上方先填年級/班級/學號（數字限制，存 localStorage）；完成題目 → 按「繳交學習單」→ 跳確認對話框 → 寫入 `submissions/{wsId}__{grade}-{className}-{studentId}`。
- 題目收集：`[data-qid]`＋`[data-qtype]`（score/experience/open）自動掃描分類；客製頁面（如 L01）可手刻，只要輸出形狀符合規範。
- 繳交後鎖定、顯示「已繳交」；重繳覆蓋同一份文件。
- **答案是否附在學生端**：`score`／`experience` 題的正解由頁面自己知道（用來即時給回饋＋算 accuracyRate/experienceCompletion）；`open` 題原文送出交教師/AI 事後判斷。

## 6. 分階段實作（每輪推進，更新 PROGRESS）
- **P0 專案骨架**：SPEC、PROGRESS、teacher.html 設計骨架（無 emoji、專業）、Firestore 資料模型定案。
- **P1 學生繳交**：可重用 `submit` 模組 + `collectAnswers()`；在 L01 示範 → 真的寫進 Firestore。
- **P2 教師端讀取**：班級/學習單選單 → submissions 表格（座號/姓名/繳交時間/狀態/分數）；空狀態、載入。
- **P3 評分**：server `/api/grade`（標準答案核對＋AI 開放題）；教師端逐筆/批次評、可改分、寫回 totalScore。
- **P4 名單/匯出/Classroom**：CSV 名單匯入、成績 CSV 匯出、Classroom 名單匯入＋成績回寫。
- **P5 Scratch 評分**：上傳 .sb3 → 解析 project.json → 依規則/AI 評分。
- **P6 與工作台整合**：工作台成品階段一鍵「綁定為學習單/開評分台」；rubric 編輯器。

## 7. UI 準則（教師端）
- 專業、無 emoji；圖示用 inline SVG 或文字標籤。
- 版面：左窄欄（班級/學習單）＋主區（繳交表格＋批改面板）。
- 字體：Inter / Noto Sans TC；中性色（slate/indigo），表格為主體，卡片輔助。
- **深色模式（2026-09-10 已完成）**：所有顏色一律走 CSS 變數（`:root` 定義淺色，`@media (prefers-color-scheme:dark):root:not([data-theme="light"])` 與 `:root[data-theme="dark"]` 兩處覆寫深色——沒手動選過跟系統，選過用 `data-theme` 蓋過去），**JS 產生的內嵌 style 也一律用 `var(--xxx)`，不寫死 hex**（批量匯入例外列的橘底、正確/錯誤的邊框色都是這樣做的，否則深色模式下會冒出一塊刺眼的淺色）。頁首「深色/淺色模式」按鈕即時切換（純 CSS 變數重算，不用重整），選擇存 `localStorage`（key `wk_theme`）；`<head>` 最前面有一段同步小 script 先讀存好的偏好設定 `data-theme`，避免翻頁先閃一下淺色才變暗（FOUC）。`input/select/textarea` 額外加了 `background/color` 的全域規則，否則瀏覽器原生表單元件底色不跟著變。
- **篩選順序：先選班級、再選學習單**：左欄「班級」可點選（`curCourse`），固定多一個「其他」項專放 grade/className 對不到任何已匯入班級的繳交；選定班級後才看到該班在目前學習單下的繳交表格。批次操作（AI 批次評分／匯出 CSV／回寫 Classroom）都只作用在**目前篩選出的班級**，不是整份學習單的全部繳交。
- **名單匯入分兩個子分頁**（2026-09-18 教師指定合併：原本「貼上/上傳」「批量匯入名冊檔案」「Classroom 單班」「批量匯入全部班級」四個分頁，功能重疊就不該分開開新分頁，合併成兩個）：
  - **「貼上／上傳名單」**：貼上文字（座號,姓名，套用上面填的年級/班級）／上傳檔案（`.csv`／`.xlsx`／`.xls`，**`<input multiple>` 可一次選取多個檔案**——Windows 檔案總管框選或 Ctrl／Shift 點選）。**多檔上傳時每個檔案各自獨立判斷班級**，不受頂部年級/班級欄位影響：`classCodeFromFilename()` 優先抓檔名裡緊跟在「上」或「下」後面的三碼數字（例如校務系統匯出的「`115_上406彈性(電腦).XLS`」→四年6班），抓不到才退而在整段檔名找任一段 `[1-6]xx`（這條備案較弱，靠下一步的預覽表格核對）；**只選了一個檔案、又判斷不出班級時，退回沿用頂部填的年級/班級**（延續舊版單檔上傳的操作習慣）。多檔的結果進一張預覽表格：檔名／年級／班級／學生數／略過勾選——偵測不到或錯的直接在表格輸入框改，不想匯入的勾略過，**不會因為一個檔案沒偵測到班級就擋住其他檔案匯入**。按「匯入」把「貼上文字」（若有填）與所有可用檔案一次組成 set 操作，走 `commitChunked()`（見下）分段寫入。
    - **檔案解析共用邏輯**（`readFileRows()`＋`rowsToRoster()`）：`.csv` 直接讀文字逐行分欄；`.xlsx`／`.xls` 都丟給 SheetJS（`xlsx.full.min.js`，cdnjs 載入，含舊版 BIFF `.xls` 二進位格式，用到才動態載入）讀第一個工作表轉成陣列。`rowsToRoster()` 只取**第 1 欄當座號、第 2 欄當姓名**，其餘欄位一律忽略——校務系統匯出的「成績記錄表」常常座號/姓名後面還跟著一大串成績、平均、階段等欄位，早期版本用 `.slice(1).join(' ')` 把姓名之後所有欄位都併進姓名字串，遇到這種檔案姓名後面會黏一串數字（已修正為只取索引 1）。座號非純數字的列（多半是標題列／小計列）自動跳過，不必老師手動去頭。
  - **「Classroom 匯入」**：預設是單班流程（選課程→自動讀名字→核對→匯入，見下），分頁下方一顆「🔍 自動掃描全部班級」按鈕，按了才展開＋觸發較重的**批量掃描教師名下所有課程**（第一次點才自動跑，之後靠「重新掃描」，同一個 `cbScan()`／`_cbScanned` 邏輯，只是不再是獨立分頁、改成同分頁往下展開的區塊）。
    - **單班**：選課程後自動讀取學生名字；若名字是「`510 01 王小明`」這種「年班 座號 姓名」格式，自動拆出年級/班級/座號，可再檢查調整。
    - **批量掃描**：逐課讀名單、用同一套「年班 座號 姓名」規則拆班，**成功的自動歸班、失敗的不擋流程**——集中列成「例外清單」（每列顯示課程／原始名稱／失敗原因，並給年級/班級/座號/姓名輸入格與「略過」勾選）讓教師當場補齊。補好的即時併回上方「將建立／更新的班級」摘要，補不齊的按匯入時自動跳過。
      - **命名解析（依真實名單統計定案）**：先全形轉半形，再依序試 A「`506 03陳小明`／`506 03 陳小明`」（年班 座號 姓名，座號與姓名間空白可有可無——**校內最常見**）、B「`陳小明 506 13`」（姓名在前）、C「`年605 20 陳小明`」（去掉非數字前綴後套 A）。三者皆不中且**課程名稱末尾帶三碼班級**（如「彈-成功自造機 406」）時，從課程推出年級/班級預填進例外列，只留座號給教師補。
      - **例外的三種來源**：①姓名與課程名稱都推不出年班座號；②**同班座號撞號且姓名不同**（同座號同名＝同一人出現在多門課，靜靜合併不算例外）；③整個課程讀取失敗或沒有學生（以課程為單位列在掃描結果那行，不進表格）。
  - **分段寫入**：Firestore 單一 batch 上限 500 筆，全校名單／多檔案批量匯入都可能超過，故 `commitChunked(ops, onProgress)` 以 450 筆為一段依序送出並回報進度——「貼上／上傳名單」的多檔匯入與「Classroom 匯入」的批量掃描共用這個函式。這是「批次寫入應分批而非一次全做」原則（見 §9）的實作。
- **設定面板（教師指定改版）**：頁首「設定」按鈕（原「AI 設定」）打開單一 modal，內部用**分頁**分三塊——「AI 評分」「Google Classroom」「名單匯入」；「名單匯入」下再分**兩個**子分頁（貼上／上傳名單、Classroom 匯入），管道都收進這裡，工具列不再各放一顆按鈕。子分頁切換時才懶載入（切到「Classroom 匯入」重抓單班課程清單；批量掃描只有第一次點「自動掃描全部班級」才觸發，之後靠「重新掃描」，避免每次切分頁都打一輪 22 門課的 API）。
- **學習單設定面板改版**：原本逐題手填「標準答案」的表格已移除——**標準答案統一在學習單自己的 `#admin` 設定**，這裡只留一顆「開啟學習單 Admin」連結；面板改放**分數計算**（見 §7-d）與**評分規準**（AI 開放題用，不變）。

### 7-d. 分數計算（學習單設定，教師指定）
> 動機：教師要能自訂「答錯扣多少」「開放題佔多少比重」「個別題目能不能配不同分數」，不是寫死的公式。

- **資料**：`worksheets/{ws}.scoring = { base, deduction, openWeight, itemPoints }`——`base` 總分（預設 100）、`deduction` 每題預設扣分（預設 1）、`openWeight` 開放題（AI）保留分數（預設 10，**只在這份學習單有開放題時才生效**）、`itemPoints` 逐題扣分覆寫（`{qid: 分數}`，留空的題目用 `deduction`）。未設定過就等同全預設值。
- **算法**（`teacher.html` 的 `calcScore(sub, cfg, aiScore)`）：
  1. 把 `scoreAnswers` 與 `experienceAnswers` 併成一份逐題 `isCorrect` 清單（`open` 題不在裡面）。
  2. `basePool = base − (有開放題 ? openWeight : 0)`——沒有開放題時非開放題滿分就是 `base`；有開放題時讓出 `openWeight` 給 AI。
  3. 每題 `isCorrect===false` 扣 `itemPoints[qid] ?? deduction`，`objective = max(0, basePool − 扣分總和)`。
  4. 有開放題時 `openPoints = round(aiScore/100 × openWeight)`；`total = round(objective + openPoints)`。
  5. **邊界**：完全沒有非開放題（`scoreAnswers`/`experienceAnswers` 皆空）時，開放題吃下整個 `base`；如果連開放題都沒有（這份什麼可判斷的題目都沒有），`total = null`，教師必須手動輸入。
- **範例**（呼應教師原話）：8 題體驗全對、無開放題 → 100 分；答錯 1 題 → 99 分；同一份若加一題開放題（AI 給 80）→ 非開放題滿分降為 90、答錯 2 題扣 2 分 → 88 分，AI 部分 80%×10=8 分，合計 96 分。
- **UI**：`renderScoring()` 顯示總分／預設扣分／開放題保留分數三個輸入框，下面列出這份學習單目前出現過的**非開放題題號**（掃 `subsCache` 的 `scoreAnswers`/`experienceAnswers` 鍵，`nonOpenQids()`），逐題可覆寫扣分（留空＝用預設）。批改抽屜按「計算分數」時用 `renderCalcBox()` 顯示分解（非開放題幾分、扣了哪幾題、AI 開放題幾分＋回饋），最終分仍可手動覆寫再存。
- **相容**：`/api/grade` 的 `answerKey` 參數與逐題 `perItem` 顯示保留給舊資料（早期用手填標準答案存過 `worksheets.answerKey` 的學習單），新學習單一律不再寫這個欄位。
- **2026-09-23 更新**：
  - `scoring.openFromPoints`（預設 true）：每一題主要開放題都有填配分時，`openWeight` 直接＝配分加總（各題配分就是最終成績裡的真實分數）；有任何一題沒填就退回手動 `openWeight` 換算。
  - `hasOpen` 只看**主要**開放題：開放題全是加分題時不再保留 `openWeight`（以前會讓這種學習單的學生平白少掉保留分數）。
  - 加分題（`bonusQids`）若是 `score`／`experience` 型：**不進扣分池，答對才加** `itemPoints[qid] ?? deduction`（對齊《學習單資料與提交規範》§2-b；以前會被當一般題扣分）。
- **2026-09-29 更新（教師指定）**：
  - **體驗題沒有正解＝看有沒有作答**：`itemPassed(rec,isExp)`——`isCorrect` 為 true 就過；體驗題 `correct` 為空（沒設答案、或老師還沒公布）且作答是文字或數字時，有寫就算過。陣列／物件作答是學習單自訂元件，完成條件由學習單自己判，不放寬。
  - **起跳分數 `scoring.floor`（預設 80）＋依題數自動配分**：`base − floor` 平均分給全部主要題（非開放題寫 `itemPoints`、開放題寫卡片配分，除不盡時開放題先多拿 1 分；分不成整數才用 0.5／0.25…），全空白最低分＝起跳分數，加分題另外加（非開放加分題預填同一份額）。`floor` 不是硬性下限，只是配分目標；面板即時顯示「配分合計 X → 全空白最低 100−X」，不等於起跳分數時提醒。
  - **何時預填**：打開學習單設定時，有空白的主要題配分就依題數補上（只填空白格；「依題數自動配分」按鈕才會覆蓋全部，檢核點題目的配分由檢核點決定不動）。都要老師按「儲存設定」才生效。
  - **逐題配分改成網格**（`renderScGrid()`，每格 題號＋題型＋輸入框，`auto-fill minmax(150px)`）：非開放題與開放題都在同一張網格，開放題那格和下方卡片的配分雙向同步。
  - **題號清單只看近期繳交**（`currentQtypes()`）：最新一份往前 3 天內、出現在 ≥30% 繳交的題號才算，題型取最新的；`nonOpenQids()`、`mainOpenQids()` 都改用它，避免改版前的舊題號混進配分與開放題滿分。
  - **完成度**：列表與 CSV 顯示整份學習單完成度（`completionOf()`：`qtypes` 全部題目扣掉加分題，有作答的比例；空字串、空陣列、false、計數 0 算沒寫）。
- **原「未來方向」（2026-09-15 提出，已由 §7-j 實作）**：`itemPoints` 目前只覆寫非開放題（`score`／`experience`）的逐題扣分；開放題只有一個整份共用的 `openWeight`，加分題是統一的 0～3 等級疊加，都不是「每一題各自一個可自訂配分」。之後新建立的學習單要讓每一題（含開放題、加分題）都能個別設定配分，細節見 `../引導規範/學習單資料與提交規範.md` §2-c 與 `../引導規範/AI評分規範.md` §7——這會連動 AI 逐題評分（見下方 §7-h 的未來方向），目前僅記錄方向，程式碼未變動。

### 7-e. AI 批次評分：整班一次呼叫，不逐筆問 AI（2026-09-10 教師指定）
> 動機：一筆一筆呼叫 AI 既慢又貴，而且班上人數一多，AI 額度/速率限制容易先撞到；同一班一次呼叫也讓 AI 看得到同一題的其他人怎麼寫，評分尺度更一致。

- **後端** `POST /api/grade-batch`（見 §4）：`_ai_grade_batch()` 把整班所有「有開放題」的學生一次組進同一個 prompt（每人一段，用短代號 `k0`/`k1`… 當區隔，不是把 Firestore doc id 直接塞進 prompt），要求 AI 回一個**以代號為鍵**的 JSON 物件，每人一個 `{score, feedback?}`。伺服器收到後把代號換回原本的 `key`（學生的 submission id）逐一比對——**這是「回傳格式能不能準確對應到學生」的關鍵設計**：鍵名由伺服器指定、範圍固定，AI 只要照抄鍵名，就不會有「回傳順序跟送出順序不一致」或「AI 自己編了個名字」這類對不上的問題。
  - AI 漏答某個代號、或該代號的 `score` 不是合法數字 → 那位學生歸進 `missing`，**不會**補一個假分數；分數會被 clamp 在 0–100（例如 AI 回 "105" 或 -20 都會被夾住，不是照單全收）。
  - 超過 40 人會分段送出（`CHUNK=40`），但每段仍是「一次呼叫評多人」，不是退化成一人一次；每段各自的成功/失敗互不影響（某段失敗只讓那段的人進 `missing`，其他段照常）。
- **前端** `batchGrade()`：先把目前篩選班級的繳交分成「有開放題」/「沒有開放題」兩組——沒有開放題的完全不進這次 AI 呼叫、本地直接用 `calcScore()` 算完；有開放題的**這個班級只打一次** `/api/grade-batch`。AI 沒回應的學生保持未評分（不寫 `totalScore`、`status` 不變成 `graded`），批次結果的訊息會明講「X 位 AI 沒有回應，可再跑一次或手動評」，教師不會誤以為全部批改完成。最後所有更新用 Firestore **一次 `batch()` 寫入**（超過 450 筆才分段，見既有 `commitChunked` 慣例），不是逐筆 `.update()`。
- **附評語（教師指定）**：AI 批次評分按鈕旁一個「附評語」勾選框，勾了才在 prompt 裡多要求 `feedback` 欄位（省 token、也省 AI 生成時間）；收到的 `feedback` 存進 `submissions/{id}.aiFeedback`（既有欄位，只是現在批次評分真的會填它），教師端繳交表格 AI 分數旁新增「評語」欄顯示（過長用 `title` 提示完整內容，滑鼠移過去看）。
  - **目前的「附給該學生」範圍**：評語寫進該學生自己的 `submissions` 文件、教師端看得到——**還沒有**推到 Google Classroom（Classroom API 沒有可寫入的「私訊評語」欄位，只能寫數字分數，這點是平台限制不是本工具沒做，跟 §8「Classroom 回寫」的 `PUBLISHED` 一定發動態時報是同一類誠實限制）；如果要讓**學生自己在學習單頁面上看到評語**，需要之後在《學習單資料與提交規範》裡定一個「查看評語」的介面契約並讓 `student-submit.js`／各學習單一起改，屬於後續擴充，本輪未做。
- **驗證（伺服器端 `_ai_grade_batch` 直接跑 Python，不需真的 AI Key）**：mock `grade_call` 測過——全部成功＋評語正確對應、AI 漏一位時該位進 `missing` 不冒充分數、AI 回傳非法 JSON 時整批 `ok:false` 並附錯誤訊息、分數異常值（字串"105"／負數／非數字）分別被 clamp 或判定失敗、85 人自動分成 40/40/5 三段且每段仍是整批呼叫。前端 `batchGrade()` 用假 `fetch` 測過三種情境（全部成功／AI 漏一人／整批 AI 失敗），皆正確只送「有開放題」的人、正確依 key 寫回、AI 失敗或漏答時對應學生維持未評分、無開放題的學生完全不受 AI 結果影響。

### 7-f. 加分題：AI 依內容評等級、老師可覆蓋，分數疊加在總分之上（2026-09-15 教師指定；2026-09-16 改成「標記」而非題型；2026-09-16 改成 AI 也評）
> 動機：有些開放題（例如「你是怎麼判斷的？」）是鼓勵反思用的加分題，不該拉低完成度統計，但**只要是開放題就該送 AI**（教師定案：不分是不是加分題），分數要能疊加、教師仍可事後覆蓋。

- **加分題不是一種題型，是標記**（2026-09-16 收斂）：題型只有 `score`／`experience`／`open` 三種，加分題仍屬其中之一，只是另外被列進 `bonusQids`。詳見《學習單資料與提交規範》§2-b。
- **加分題一樣送 AI，但分開算分**：伺服器收到 `bonusQids` 參數後，把每位學生的開放題答案拆成「主要」與「加分」兩組（`_split_open()`），分別出現在同一個 prompt 裡的不同區塊，AI 一次回傳兩個分數：`score`（主要開放題，依評分規準，上限＝規準總分）與 `bonusScore`（加分題，獨立的 0～3 尺規，依內容完整度：0 沒寫或不相關／1 簡短籠統／2 完整合理／3 具體有例子）。兩者互不影響，**加分題答錯或寫得普通不扣主要開放題的分**。
- **資料**（學習單提交端，見《學習單資料與提交規範》§2-b/§3）：`qtypes.{qid}` 照樣是三種題型之一，另加 `bonusQids: [qid,...]`；加分題答案要**同時**放進 `openAnswers`（送 AI）與 `bonusAnswers = { {qid}: {given, completed} }`（`completed` 供學生端顯示完成提示，**不含分數**）。
- **不進 `experienceCompletion`**：分母/分子都不算加分題，避免「要不要寫加分題」影響到體驗完成度這個統計數字。
- **教師端**（`teacher.html`）：
  - 批改抽屜 `openDrawer()` 偵測 `s.bonusAnswers` 有內容時，每個 bonus qid 顯示一個下拉選單（`BONUS_TIER_LABEL`：0 未加分／1 簡短／2 普通／3 詳細）；按「計算分數」呼叫 `/api/grade` 時一併帶 `bonusQids`，AI 回傳的 `bonusScore` 會**自動回填**這個下拉選單（教師仍可手動改，改完的值以手動為準，因為 `currentBonusScore()` 讀的是下拉選單當下的值，不是 AI 原始值）。
  - `calcScore(sub, cfg, aiScore, bonusScore, aiMax)` 第 4 參數 `bonusScore` 未傳入時退回 `sub.bonusScore||0`；`total = round(objective + openPoints + bonusScore)`，**不夾在 0–100 之間**，故意讓加分題可以把總分推超過 100。
  - **維持這個設計，只是說明用語（2026-09-15 教師確認）**：概念上「正確率/測驗＋開放題」兩者的滿分設計目標是合起來 100 分（`base` 減 `openWeight` 再加開放題換算），**加分題是疊在這 100 分之上的額外鼓勵分**，不是三塊分數各自固定佔比、合計硬性等於 100。也就是說「沒拿到加分題」的理想情況總分大約落在 100 上下，但**不強制封頂**——教師已明確表示維持疊加制，這裡只是把用語講清楚，避免跟「三塊固定配比」的另一種設計搞混。
  - **批次評分**（§7-e）現在也會處理加分題：`/api/grade-batch` 帶 `bonusQids`（`batchBonusQids()` 取所有繳交的聯集），回傳的 `results[key].bonusScore` 直接寫進 `submissions/{id}.bonusScore` 與 `bonusTiers`（每個 bonus qid 都設成同一個值——目前一份學習單只有一題加分題，先不做逐題分開儲存），**不需要老師逐筆進批改抽屜手動評**。
- **學生端提示**：學習單頁面上該加分題旁邊顯示一個小標籤（例如「🎁 加分題：已完成／尚未完成」），純粹告知「有沒有寫」，不顯示、也不能自己看到會加幾分。
- **範例**：g5 L01「你是怎麼判斷的？」，`qtypes.reason='open'` 且列進 `bonusQids`；學生寫了就 `openAnswers.reason` 有內容、`bonusAnswers.reason.completed=true`；批次評分時 AI 同時評出 `essay`（主要）與 `reason`（加分，例如 2 分），該生 `totalScore` 就是主要開放題換算分數（含非開放題）再加 2 分。
- **列表可見度**：繳交列表「最終」欄，有 `bonusScore` 就在分數旁加一個小徽章（🎁+N，`renderSubs()`），不用點進批改抽屜才看得到有沒有加分；`exportCSV()` 的匯出表頭也多一欄「加分」。

### 7-g. 「啟用AI」開關＋API Key 壞字元防呆（2026-09-15 教師回報「按了沒反應」查出的根因修正）
> 根因：`config.json` 的 `grade_key` 曾被誤存成一段含中文的錯誤訊息（不是真的 API Key）。`_llm_call()`/`_llm_models()` 把它塞進 HTTP header（`Authorization: Bearer <key>`）送出時，Python 的 `http.client` 對 header 值做 latin-1 編碼，中文字元編不進去直接丟 `UnicodeEncodeError`，訊息長得像「'latin-1' codec can't encode characters in position 10-14」——教師端只看得到「按了沒反應」，看不出哪裡壞了（違反 `../引導規範/學習單資料與提交規範.md` §5-4 的「不對使用者洩漏技術訊息」原則，這裡補上）。
- **防呆**：`_bad_header_chars()` 在送出前先檢查 `key`/`model` 是否含 `ord(c)>=256` 的字元，有就直接回一句看得懂的錯誤（「API Key 或模型名稱含不支援的字元…請重新貼上」），不會再讓例外炸到 `http.client` 深處。
- **`啟用AI` 勾選框**（原「附評語」，教師指定改名兼改功能）：`teacher.html` 頂欄「批次評分」按鈕旁的 `#aiEnableChk`，預設勾選。**勾選**＝跟以前一樣：有開放題的學生一次 AI 呼叫評完、順便附評語；**取消勾選**＝完全不呼叫 AI，`withOpen`（有開放題）的學生維持未評分狀態（不寫入假分數），訊息會明講「請到批改抽屜手動評」——`batchGrade()` 判斷式是 `if(!withOpen.length||!aiEnabled){writeAndFinish('');return;}`。這個開關只影響「批次評分」；批改抽屜逐筆按「計算分數」仍然一律呼叫 AI（那裡沒有對應開關，見 §7-d）。
- 按鈕文字順帶從「AI 批次評分」改成「批次評分」——這顆按鈕本來就不是只有 AI 在做事（沒有開放題的學生本地算分、不叫 AI），舊名字容易讓人誤會「沒有開放題也要等 AI」。

### 7-h. AI 評分總則＋規準分制（2026-09-16 教師指定；**2026-09-23 已由 §7-j 取代**，下文保留作歷史記錄）
> 動機：AI 評分以前是「0–100 分、每個人都給差不多」，既看不出高下，也沒有一條可以一次改到全部評分的總規則。教師要的是：**一份最上級的評分準則、每次呼叫都先插進去**，而且**給分上限由自己填的規準決定**。

- **完整規範文件** → `../引導規範/AI評分規範.md`（評分總則原文、哪些題型會送 AI、三條伺服器強制規則、尺規換算、為什麼相對比較只在批次成立）。這裡只記評分平台這側的實作重點。
- **只有 `openAnswers` 送 AI**：`scoreAnswers`／`experienceAnswers` 一律不送（它們有標準答案、學習單已判好 `isCorrect`）；加分題**也送**（2026-09-16 改），因為它的答案也放在 `openAnswers` 裡，伺服器再依 `bonusQids` 拆成主要／加分兩組分開評分、分開回傳（見 §7-f）。
- **評分規準前面先列開放題編號**（`_open_qid_note()`，2026-09-16 教師指定）：組 prompt 時在「評分總則」之後、「評分規準」之前，插一行「本次開放題編號：主要開放題＝…；加分題＝…」，讓 AI 在看規準之前就先知道這次要分辨哪幾個 qid、各屬於哪一類。單筆用這位學生自己的 qid；批次評分用整批「出現過」的 qid 聯集（規準是整份學習單共用的）。
- **開放題逐題各自打分**（2026-09-16 教師指定，已實作，見 `../引導規範/AI評分規範.md` §7）：AI 回傳從單一 `score`／`bonusScore` 改成逐題的 `scores:{qid:分數}`／`bonusScores:{qid:分數}`（每題主要開放題各 0～`aiMax`、每題加分題各 0～3）。伺服器彙總成既有的 group 總分欄位——主要開放題 `score`＝各題**平均**（維持 `aiMax` 是「單題最高水準」的語意，§7-d／本節的 `openPoints` 公式不變）；加分題 `bonusScore`＝各題**相加**（維持 §7-f 的疊加式加分）。逐題分數額外存進 `submissions/{id}.aiScores`；加分題逐題分數沿用既有的 `bonusTiers` 欄位（原本每題都填同一個值，現在是 AI 給的各自真實值）。批次評分時若 AI 漏答某個必要 qid，**整位學生**歸進 `missing`，不補假分數。
- **評分總則（`grade_master_rubric`）**：全域一份，存在 `config.json`；`master_rubric(ai_max)` 取值（空字串＝用 `server.py` 的 `DEFAULT_MASTER_RUBRIC`），把 `{max}` 換成本次上限後，插在**每一次** AI 呼叫（`_ai_grade` 單筆、`_ai_grade_batch` 批次）的 prompt 最前面，再接該學習單的評分規準。
  - **UI 在「學習單設定 → 📋 評分總則」**（跟評分規準放一起），彈窗可預覽／編輯／還原預設。按「還原預設」再儲存會存成空字串，代表**永遠跟著程式預設走**，之後預設更新也會自動套用。
  - `GET /api/settings` 會多回一個唯讀欄位 `_default_master_rubric` 給 UI 顯示；`POST /api/settings` 會**丟掉所有 `_` 開頭的 key**，不讓唯讀欄位被寫回 config。
- **給分上限＝評分規準各項配分總和**（`_rubric_total()`，沒填規準時退回 100）。AI 回傳的是**規準分**不是百分制：
  - 伺服器端 `max(0, min(ai_max, round(score)))` 強制夾住，AI 回 999 也只會拿到上限。
  - 前端 `calcScore(s,cfg,aiScore,bonusScore,aiMax)` 換算 `openPoints = round(aiScore/aiMax × openWeight)`；`aiMax` 沒傳就退回 `s.aiMax` 再退回 100，**舊的百分制資料換算結果完全不變**。
  - `aiMax` 跟著成績寫進 `submissions/{id}`，列表 AI 欄顯示成 `8 / 10`，避免被誤讀成「只考 8 分」。
- **沒作答＝0 分，而且不送進 prompt**：`_is_blank()`（去掉空白與標點後為空即視為沒寫）在組 prompt 前就把這些人挑掉直接給 0——省 token，也避免一堆空白作答拉低 AI 對「這批平均水準」的判斷，影響總則第 2 點的相對比較。
- **「依標準差／相對突出程度給分」只有批次評分成立**：批次是整班一次呼叫，AI 看得到全班分佈；批改抽屜的單筆評分只看得到一位，沒有母體可比，此時退化成依規準的絕對評分（見 §7-e 與《AI評分規範》§5）。

### 7-j. 通用評分引擎：逐題規格、AI 只判斷、分數由系統算（2026-09-23 教師指定）
> 動機：G4 L02「找出符合條件的景點」全班都答對，AI 卻因景點不同給不同分數。根因是舊總則要求所有題目「和同儕比、拉開分數」，
> 加上規準是整份共用、每題都以整份上限評分再平均。教師要求：題幹、標準、配分寫在一起給 AI；每題不得超過自己的配分；做成之後每份學習單都適用的通用系統。

- **完整規則** → `../引導規範/AI評分規範.md`（三種評分方式、班級相對錨點、判定紀錄、Firestore 欄位）。這裡只記實作位置。
- **後端**（`server.py`）：`build_spec()` 補齊題目規格（舊格式相容）；`_grade_engine()` 依題目分組、正規化去重、各題平行呼叫
  `_grade_condition()`／`_grade_checklist()`／`_grade_levels()`，再組回每位學生；`_ask_for()` 統一「問 AI → 逐代號驗證 → 缺的再問一次」。
  `/api/grade-batch`、`/api/grade` 共用引擎，多收 `openQids`（決定開放題滿分）、`verdicts`、`anchors`，多回 `details`、`flags`、`verdicts`、`anchors`。
  新增 `GET /api/grading-spec?url=`：讀學習單內嵌的 `<script type="application/json" id="grading-spec">`（見提交規範 §2-e）。
- **前端**（`teacher.html`）：
  - 學習單設定的「開放題評分設定」：一題一張卡片（題號、評分方式、配分、題幹＋該方式的標準），自動補上繳交中出現的開放題、
    題幹自動帶入 `qtexts`；條件查核卡片顯示判定紀錄（點一下改判、立即存檔）；分級卡片顯示本班錨點（可重設）。
    儲存時：條件改了→清該題判定紀錄；題幹／標準／方式改了→清各班該題錨點；移除舊的整份 `rubric`。
  - 批改抽屜：已評過的直接顯示逐題結果（項目✓✗、檢核點與證據、等級、評語），主要開放題分數可直接改（夾在 0～配分），
    加分題用下拉選單（範圍＝該題配分）。儲存＝老師已確認，清空 `aiFlags`。
  - 列表：AI 欄有 `aiFlags` 時顯示「待確認」；AI 評語與學生作答一律 `esc()`（以前是直接塞 HTML）。匯出 CSV 多一欄「開放題逐題」。
- **學生端模組**（`student-submit.js`）：開放題元素的 `data-qtext` 自動收集成 `qtexts` 一起送出。
- **驗證**：見《AI評分規範》§8（mock 31 項＋實際呼叫 gemini-3-flash-preview）；前端在瀏覽器以假 Firestore／假後端回應測過設定儲存與失效清除、
  判定改判、錨點顯示、批次評分分數組合（含只有加分題、非開放加分題）、抽屜改分與儲存、XSS 字串顯示為純文字。

### 7-k. 評分設定從哪來：備課時內嵌 → 自動讀入；沒有就 AI 讀學習單產生（2026-09-29 教師指定）
- **備課平台產出互動 HTML 時就寫好**：學習單內嵌 `grading-spec`（開放題規格＋`scoring`，見《學習單資料與提交規範》§2-e）；工作台交接包提醒 Claude Code 照做。
- **第一次打開學習單設定**（`worksheets/{id}` 還沒有 `questions` 也沒有 `scoring`）時自動 `fetchGradingSpec()`→`applyGradingSpec()` 填進畫面，再把還空的配分依題數補齊；老師檢查後按儲存。之後以平台存的為準，要重新帶入按「從學習單讀取」。
- **學習單沒有內嵌設定**：「AI 讀學習單產生」→ `/api/gen-grading-spec`。配分沿用目前卡片配分（已依題數配好）當指定配分，AI 只寫題幹／評分方式／標準，checklist 檢核點由伺服器等比例調成加總＝配分；已有標準的卡片會先確認才覆蓋。
- **綁學習單、不綁班級**：存在 `worksheets/{id}.questions`／`scoring`，切換班級沿用同一套；只有 `levels` 班級相對的錨點依班級記在 `courses/{班級}.gradingAnchors`（原設計不變）。

### 7-l. 繳交狀況（原「即時繳交」按鈕）與讀取量原則（2026-09-29 教師指定）
- **讀取量原則：只讀目前這個班**。Firestore 免費額度每天 5 萬次讀取，全校一學期約 9,000 份繳交；任何「每次開頁面就讀全部繳交」的做法到學期末都會爆。因此：
  - 學習單下拉選單**不讀 submissions、不顯示份數**，只列 `worksheets.json`＋`worksheets` 集合；某班交過但還沒登錄的學習單，在打開那班的繳交紀錄時補進選單（`window._wsExtra`）。
  - 主清單 `loadSubs()` 查 `worksheetId＋grade＋className`（三個等式，不需要複合索引）；換班級才重讀。只有「其他（未匹配）」讀整份學習單。
  - `live-submit.html` 的監聽與「清除繳交紀錄」同樣加上年級＋班級條件，別班繳交不觸發讀取。
- **「繳交紀錄」面板**（原「繳交狀況」，2026-10-05 拿掉嵌入的即時繳交分頁，改由綠色圓鈕開置頂小視窗，見 §7-n），右上可切班級。
  - **繳交紀錄**：打開某班才讀（該班全部繳交＋名單＋請假紀錄，約 50 筆）。每份學習單一張卡：已交 N／名單人數，下面列缺交座號（照課次 L01、L02 排）。點座號 →「刪除這個號碼（這份免交）」或「這份學習單整份忽略」；免交與忽略都能還原。
  - **永久記住放哪**：免交＝`courses/{班}/absences/{學習單}`（跟即時繳交視窗的「請假」是同一份，兩邊互通）；整份忽略＝`courses/{班}.ignoredWs`；都在既有規則範圍內，不必改 `firestore.rules`。沒有另建「繳交彙總」快取：每次打開讀一個班約 50 筆，比維護一份彙總（還要處理刪除、重繳同步）單純，讀取量也夠低。
  - **發布缺交名單到 Classroom**：組好公告文字（班級＋每份學習單缺交座號，可編輯）→ 選 Classroom 課程（第一次依課程名稱裡的三碼班級代號預選，之後記在 `courses/{班}.classroomCourseId`）→ 確認後 `POST /api/classroom/announce` 發到訊息串。需要 `classroom.announcements` 權限：舊授權要在「設定 → Google Classroom」重新授權一次，缺權限時會明講。
- **設定 → 更新**分頁：手動「檢查更新」／「立即更新」，跟頁首自動提示共用 `/api/update/check`、`/api/update/apply`。


### 7-n. 即時繳交：綠色圓鈕＋置頂小視窗（2026-10-05 教師指定）
> 教師回報：9/29 改成嵌在「繳交狀況」面板裡的 iframe 很難看、要按好幾下才能釘選。要「綠色圓圈，點了就跳出視窗，視窗預設置頂」。
- **入口**：主畫面右下角固定的綠色圓鈕（`#liveFab`，登入後出現）。沒選班級／學習單時半透明，點了在圓鈕上方冒提示，不跳 alert。
- **點了做什麼**：用 Document Picture-in-Picture 開一個**浮在所有視窗最上層**的小視窗（460×400，可拖可縮），裡面放 `live-submit.html?cid&ws&pip=1`。瀏覽器不支援（Chrome／Edge 116 以前、Firefox、Safari）或被拒，才退回一般彈出視窗。再按一次圓鈕＝關掉；開著時圓鈕顯示「已交／應交」，有人剛交就往外擴散一圈；按住 Shift 再按＝換成目前畫面那班／那份。
- **「上課」按鈕**也改開置頂小視窗，而且**最先開**：置頂小視窗需要「剛點擊」的使用者動作，先開 Admin 視窗可能把這個動作用掉。
- **限制**：小視窗屬於主畫面這個分頁，主畫面分頁關掉或重新整理，小視窗也會關。要投到教室螢幕放大時，按小視窗底下「投影用大視窗」換成一般視窗（可拖到投影幕）。
- **`live-submit.html` 改版**：
  - 座號改成圓圈：已交＝實心綠、還沒交＝白底灰框、請假＝虛線加「假」。圓圈大小依視窗尺寸與人數自動算（試每種欄數，挑最大又全部塞得下的），任何大小都不用捲動。
  - 頂端：班級＋學習單標題、大字「已交／應交」（應交＝名單－請假）、綠色進度條；全部交齊顯示「全部交齊」。
  - 底下列出還沒交的座號（**只列號碼、不列姓名**：這個視窗常被投到教室前面）；姓名只放在滑鼠停留提示裡給老師看。
  - 剛交進來的座號會彈一下＋擴散綠圈；點已交的座號只提示「已經交了」，不會誤標請假。
  - 深色模式跟主畫面同一個偏好（`localStorage.wk_theme`）。
  - 置頂小視窗裡不放「清除繳交紀錄」（視窗小、上課中常點座號，誤觸代價太高），只在一般視窗出現，且改成底部的文字連結。
  - 一般視窗的「釘選在最上層」也改成開置頂版的自己，並**暫停大視窗自己的監聽**，同一份資料不讀兩次；小視窗關掉再接回。
  - 每次人數變動用 `postMessage({type:'liveCount',cid,ws,got,need,done,fresh})` 回報給開它的主畫面（同源限定），主畫面不另外讀 Firestore。

### 7-m. 沒寫的學生不能比寫了的高；後台補登學生（2026-09-30 教師指定）
- **起因與複查（4年6班 g4-L02，94 分那位其實是 17 號）**：複查後那筆分數符合規則（開放題全空白，但 8 題檢測／體驗只錯 1 題：96 − 2 ＋ 0 ＝ 94；其他人開放題有寫，卻漏做較多 2～3 分的小題），不是漏洞；下面這個漏洞是查的過程中發現的，該班資料不受影響：`calcScore` 用「這位學生有沒有開放題作答」決定要不要保留 `openWeight`。沒有開放題作答（欄位不存在，或整份沒交出去的題目）時 `hasOpen=false`，`basePool` 變成整個 `base`——等於白送開放題滿分（分數＝起跳分數＋開放題配分），比寫得普通的人還高。
- **修正**：
  - `wsHasMainOpen(s)`：**看整份學習單**有沒有主要開放題（任一份繳交出現、或 `worksheets.questions` 有非加分題），有就保留 `openWeight`；沒寫的學生開放題得 0，不再多出那一塊。
  - `calcScore`：這份學習單有的非開放題（`nonOpenQids()`），這位學生繳交裡沒有該題＝沒作答，照樣扣分。
  - 沒有任何作答的最低分＝起跳分數（`floor`），不會超過寫過的人。
- **補登學生**（頁首「補登學生」，選好班級與學習單後可用）：讀該班名單，列出這份學習單**還沒有繳交紀錄**的學生（打開時先向伺服器重讀一次繳交，避免蓋掉剛交的），勾選後寫入 `submissions/{學習單}__{年}-{班}-{座號}`。
  - 欄位：`manual:true`、作答欄位皆空、`status:'submitted'`；視窗內可填「統一分數」，有填就直接 `totalScore`＋`status:'graded'`＋`manualScore:true`。
  - 補登紀錄列表顯示「補登」標籤；批改抽屜可輸入分數，儲存時補上 `manualScore:true`。**`manualScore` 的紀錄批次評分不重算**（老師給的分數不被蓋掉）；沒給分的補登紀錄，批次評分會依規則算成「沒寫」的最低分。
  - `currentQtypes()` 忽略補登紀錄，避免空紀錄稀釋題號判斷。即時繳交畫面也會把補登的學生算成已交。不需要改 `firestore.rules`（老師本來就能寫 submissions）。

### 7-i. 課表與一鍵「上課」（2026-09-17 教師指定）
> 動機：上課前的固定動作是「想一下這節是哪一班 → 找到那班這週的學習單 → 開它的 `#admin` → 再開即時繳交視窗」。這四步每節都重複一次，課表既然是固定的，就讓它自己算出來。

- **資料存哪**：`評分平台/timetable.json`（走 `GET/POST /api/timetable`），**不進 Firestore**——課表是這台電腦上這位教師自己的排課，沒有任何學生資料，放本機檔就不必為它動 `firestore.rules`。檔案已加進 `.gitignore`（不含金鑰，但屬個別教師的本機資料）。
- **資料形狀**：
  ```
  { periods:[{no, start:"HH:MM", end:"HH:MM"}],      // 節次時間＝「現在是第幾節」的判斷依據
    slots:{ "{星期1-5}-{節次}": "{班級id}" },          // 班級id 就是 courses 的 g{年級}-c{班級}
    currentWs:{ "{班級id}": "{學習單id}" },            // 每班「本週學習單」指標（教師指定：每週切一次，不是每格各綁一份）
    updatedAt }
  ```
- **現在這節（`renderNow()`，每 30 秒重算）**：`nextSlot()` 先找**今天正在上的那節**（現在時間落在 start–end 之間），沒有就找**今天接下來的第一節**，今天沒了就往後找第一個有課的日子（週末自然跳過，因為課表只排星期一～五）。卡片顯示星期／節次／時間／進行中或還有幾分鐘、班級名、本週學習單，右邊一個可直接改「本週學習單」的下拉（改了立刻存回課表）與「上課」鈕；下面一排是今日各節的 chip，點任一節就上那一節（補開或提前開都用這個）。
- **「上課」做三件事**（`startClass(cid, wsId)`）：①主畫面切到該班級與該份學習單（等於幫教師按完左欄班級＋右上角學習單）；②開該學習單的 **Admin**＝登錄網址加 `#admin`（見 §7 學習單設定面板）；③開 **即時繳交偵測視窗** `live-submit.html?cid=…&ws=…`。三種擋下來的情況都會明講而不是默默不動：班級不在名單裡（要先匯名單）、沒指定本週學習單、學習單沒登錄網址（只開即時繳交，並說 Admin 為何沒開）；`window.open` 回 `null`（被瀏覽器擋彈出視窗）也會如實說。**Admin 視窗若還開著不會重開**（`wsAdminWindows` 記住視窗參考，`isWinOpen()` 檢查），避免每節課都把老師可能正在設定的 Admin 分頁搶回最上層或重整；視窗被關掉之後再上課才會重新開。
- **課表怎麼填（教師指定：格子編輯＋貼上，2026-09-17 改版合併成一個畫面）**：頁首「課表」modal 只有兩個分頁——
  - **課表格子**（唯一的編輯畫面）：星期一～五 × 節次的表格，**每節同一列直接編輯節次編號／上課／下課時間**（不再另外分「節次時間」分頁），旁邊才是當節五個班級的下拉（來源 `courses`）；列尾「刪除本節」、表格下方「＋新增節次」。課表上有、名單裡卻還沒建立的班級會保留成「（名單缺）」選項，不會一開編輯器就被靜靜清掉。存檔（`collectTtSlots()`）時**直接讀 DOM**——用「這一列目前的節次編號」＋「選單在該列的第幾個（對應星期一～五）」組 key，不依賴渲染當下就定死的字串，所以改節次編號、新增/刪除節次都不會讓已選好的班級跑到別的節次或消失（這是合併前「節次時間」與「課表格子」分兩個分頁、要按存檔才互相同步時，可能存在的落差來源）。存檔前檢查：時間格式（HH:MM，下課晚於上課）、**節次編號不可重複**（重複的話同編號會互相蓋掉班級選擇，直接擋下來列出重複的編號）。
  - **貼上匯入**（收在「課表格子」分頁裡一顆可收合的按鈕，不用切分頁；2026-09-18 教師指定拿掉 AI 呼叫，只留這一種）：**簡單解析**（免 API Key，純前端 regex），一行一節課，**順序不拘**（逐 token 判斷）。接受兩種寫法、可混用：
    - `一 09:35-10:15 2 401`（星期／上課-下課時間／節次編號／班級——**推薦格式**，這節課的上課／下課時間會直接寫回課表格子，同節次被多行提到以最後一次為準）
    - `一 3 五年2班`（沒有時間，只有節次編號，比照原本的寫法）
    星期收 `一～五`／`1～5`／`週一`／`星期一`／`禮拜一`；時間收 `HH:MM` 用 `- ~ 至 到` 其中一種分隔（`ttTimeRange()`，單位數小時如 `9:35` 自動補成 `09:35`，下課須晚於上課，否則整個 token 判定不是時間、falls through 到班級解析，通常會讓那一行判定成「看不出班級」進例外清單）；節次收 `3`／`第3節`；班級收 `五年2班`／`502`／`5-2`／`g5-c2`（全形自動轉半形，沿用名單匯入的 `halfWidth()`）。**對不上的行集中列成例外清單**，跟名單批量匯入同一套「成功的自動歸位、失敗的不擋流程」原則。解析出來的節次編號若目前課表沒有，自動補一列（`ttEnsurePeriodRow()`）；那一行若帶了時間，直接用 `ttSetPeriodTime()` 填上該節次的上課／下課時間，不用再手動補。
  - **課表照片轉文字提示詞**（`<details>` 收合區塊，`TT_IMPORT_PROMPT` 常數＋「複製提示詞」按鈕）：**不是本站呼叫 AI**，是給老師複製去貼給任何看得懂圖片的外部 AI（ChatGPT／Gemini／Claude 網頁版等，上傳課表照片＋貼這段提示詞），要求它輸出的格式剛好符合上面「簡單解析」推薦格式（`星期 上課-下課 節次 班級`，例：`一 09:35-10:15 2 401`），回覆的文字直接貼回來解析即可。複製用 `navigator.clipboard.writeText`，不支援或失敗時退回 `execCommand('copy')` 再退回提示手動選取。
  - **本週學習單**：課表上出現過的每個班級各一個學習單下拉（分類分組同主畫面），跟「課表格子」分開一個分頁（這個不需要每節編輯，維持獨立分頁）。
- **表格版面**：`.ttTable` 用 `table-layout:fixed`＋`<colgroup>`（節次欄固定 150px、五個星期欄平分剩餘寬度）並外包一層 `overflow-x:auto`，避免舊版「欄位靠內容自動撐寬、比 modal 還寬又沒有明顯的水平捲軸」而看起來像沒有正確渲染的問題；modal 寬度也放寬到 `min(980px,100%)`。

## 8. 已決策（原「待確認」，教師已定案）
- **繳交對應學生**：年級／班級／學號（三個數字），不用姓名、不需登入。見學習單資料規範 §1。
- **評分粒度**：`score`／`experience` 題逐題核對 `isCorrect`（用於扣分，不是各自獨立算一個百分比）；`open` 題送 AI。`totalScore` 由 §7-d 的分數計算規則合成，教師存最終分前仍可手動調整。
- **Classroom 回寫**：選課程即可，**作業不必先在 Classroom 開好**。比對作業採**兩層優先序**（`teacher.html` 的 `weekOf()`＋`ccCourse` change handler）：
  1. **依週次比對（優先）**：`weekOf()` 從 `curWsCfg.url`（`.../g5/L01/`）或學習單 id（`g5-L01`）抓出 `L` 後面的數字當週次，找該課程裡標題以「第X週」開頭的作業——即《教案工作臺》用「問題」模板發布的**每週簽到題**（見同專案外的工作台 `web/index.html` §發布到 Classroom）。找到就直接把這份學習單的成績寫進**那份週次簽到題**，同一週的所有學習單共用同一份 Classroom 作業，不會每份學習單各自長出一份作業。
  2. **依標題比對（退回）**：抓不到週次，或該週還沒有對應的簽到題時，退回舊式邏輯——正規化比對學習單自己的標題（`curWsCfg.title`），找到就選、找不到就預選「建立新作業：{學習單標題}」（此時會提示教師「建議先到工作台發布本週的簽到問題」）。
  - **建立新作業**：按下「回寫成績」時才真的建立（`workType:ASSIGNMENT`、`state:PUBLISHED`、`maxPoints` 可在 UI 改、`materials` 附上學習單網址）；後端 `classroom_create_coursework` 建立前會再找一次同名作業，找到就直接沿用（前端清單過期或連按兩次都安全）。教師也可隨時從下拉改選任一現有作業。
  - 學生對應：優先用名單裡的 `classroomUserId` 精準比對，退化為姓名比對，對不到可手動指定或設「不回寫」。

## 9. 已知限制與後續強化
- ~~新識別模型無姓名無法自動配對 Classroom~~ → **已解決**：從 Classroom 匯入名單時（教師端「從 Classroom 匯入」）會保留 `classroomUserId`，回寫時用「年級+班級+學號 → 名單 → classroomUserId」精準比對；手動匯入（CSV/貼上/xlsx）的班級仍只能靠姓名猜或手動指定。
- Classroom 學生姓名的自動解析已涵蓋校內三種實際寫法（見 §7），無法解析時匯入表格會標橘色請老師手動填年級/班級/座號。**批量匯入**同樣不因此中斷——把這些人集中到例外清單一次處理完（見 §7）。
- Firestore 免費（Spark）方案：1GiB 儲存、50K 讀/日、20K 寫/日、20K 刪/日、10GiB 傳輸/月（[官方頁面](https://firebase.google.com/pricing)）。單一學校規模（數百學生×每年數十份學習單）遠低於此上限；唯一要注意的情境是**一次性批次評分/寫入全校成千上萬筆**，那種操作應分批而非一次全做。
