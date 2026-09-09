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
worksheets/{wsId}                        學習單設定（老師管理） { title, category, url, answerKey?, rubric?, questions? }
courses/{grade}-c{className}             班級名單（老師管理） { grade, className, name:"{grade}年{className}班", source:'manual'|'classroom',
                                            students/{seatNo}:{seatNo, name, classroomUserId?} }  // classroomUserId 有值時，Classroom 回寫可精準比對，不必猜姓名
feeds/{wsId}/messages/{autoId}           開放題即時同儕動態（見學習單資料規範 §4） { qid, text, tag, at }
quizzes/{wsId}                           （L01 沿用）老師控制的「公布/還原」即時同步，與 submissions 是兩個獨立機制，見《互動教材進階規範》§2
```
- **為何扁平**：Firestore 的 collection 查詢**不會回傳「只有子集合、本身不存在」的幽靈父文件**；若把繳交放 `worksheets/{ws}/submissions`，教師端就列不出還沒被老師建過設定的學習單。改用扁平 `submissions`＋`worksheetId` 欄位，教師端由繳交資料直接推出學習單清單。
- **doc id**＝`{worksheetId}__{grade}-{className}-{studentId}`：同一人重繳覆蓋自己那筆。三個識別欄皆為數字，不採「班級＋座號＋姓名」——見資料規範 §1 的理由。
- **評分兩路（兩個獨立計算系統，不是一步流程）**：`score` 題由頁面自己算出 `accuracyRate`（客觀正解）；`open` 題送 AI 得 `aiScore`＋`aiFeedback`（`totalScore` 為教師確認後的最終分，走 `/api/grade`）。`experience` 題只計入 `experienceCompletion`，不進正確率。**沒有開放題時教師端完全不呼叫 AI**，直接拿 `accuracyRate` 當最終分。
- **規則**：見同層 `firestore.rules`（含 L01 quizzes、submissions、worksheets、courses、feeds）。

## 3. Firestore 安全規則
> **完整內容見同層 `firestore.rules`**（可直接複製貼到 Firebase Console 發布），涵蓋：`quizzes`（L01 揭曉同步）、`submissions`（學生繳交，本人可寫、老師可讀寫）、`worksheets`（老師管理）、`courses`（名單）、`feeds`（同儕留言，本人可寫自己的、老師可刪）。
- `isTeacher()`＝`request.auth.token.email == "boyin0304@slps.tn.edu.tw"`（沿用 L01）。

## 4. API（評分平台/server.py，8780，自己的 config.json）
| 路由 | 功能 |
|---|---|
| GET/POST `/api/settings` | 讀寫本專案設定：`grade_provider/endpoint/key/model`（AI）、`google_client_id/secret`、`google_token`（授權後自動存） |
| POST `/api/grade` | 收 {answers, answerKey?, rubric?, questions?} → 標準答案核對＋開放題丟 AI（見《AI串接窗口設定規範》）→ 回 {autoScore, aiScore, aiFeedback, perItem[]} |
| GET `/api/grade-models` | 列 AI 可用模型 |
| GET `/api/fetch-title` | 讀某網址 `<title>`（新增學習單時自動帶標題） |
| GET `/api/google/auth-url` | 產生 Google 授權連結（redirect 指向本專案 `:8780/oauth/callback`） |
| GET `/oauth/callback` | 換 token、存進 config.json |
| POST `/api/google/logout` | 清除已存的 Google token |
| GET `/api/google/courses` | 列教師的 Classroom 課程 |
| GET `/api/classroom/coursework` | 列某 Classroom 課程的作業 |
| GET `/api/classroom/students` | 列某 Classroom 課程名單（需 `classroom.rosters.readonly` scope） |
| POST `/api/classroom/coursework` | **依標題確保作業存在**：先找同名作業，找不到才建立（PUBLISHED、全班指派、附學習單連結）→ 回 {id, created} |
| POST `/api/classroom/grades` | 回寫分數到指定 courseWork（patch draft+assigned 後 `:return`）；讀不到 studentSubmissions 時等 2 秒重讀一次（剛建立的作業有生成延遲） |
| GET `/api/diagnostics` | AI／Google 連線狀態快覽 |
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
- 深淺色可留待後期；先做淺色專業感。
- **篩選順序：先選班級、再選學習單**：左欄「班級」可點選（`curCourse`），固定多一個「其他」項專放 grade/className 對不到任何已匯入班級的繳交；選定班級後才看到該班在目前學習單下的繳交表格。批次操作（AI 批次評分／匯出 CSV／回寫 Classroom）都只作用在**目前篩選出的班級**，不是整份學習單的全部繳交。
- **名單匯入三管道**：貼上文字（座號,姓名）／上傳 CSV 或 XLSX（XLSX 解析用 cdnjs 的 SheetJS，用到才載入）／從 Classroom 直接匯入（見 §4-c 命名慣例）。三者都寫進同一個 `courses/{grade}-c{className}/students` 結構。
- **名單匯入第四管道「批量匯入全部班級」**：一次掃過教師名下**所有** Classroom 課程，逐課讀名單、用同一套「年班 座號 姓名」規則拆班，**成功的自動歸班、失敗的不擋流程**——集中列成「例外清單」（每列顯示課程／原始名稱／失敗原因，並給年級/班級/座號/姓名輸入格與「略過」勾選）讓教師當場補齊。補好的即時併回上方「將建立／更新的班級」摘要，補不齊的按匯入時自動跳過。
  - **命名解析（依真實名單統計定案）**：先全形轉半形，再依序試 A「`506 03陳小明`／`506 03 陳小明`」（年班 座號 姓名，座號與姓名間空白可有可無——**校內最常見**）、B「`陳小明 506 13`」（姓名在前）、C「`年605 20 陳小明`」（去掉非數字前綴後套 A）。三者皆不中且**課程名稱末尾帶三碼班級**（如「彈-成功自造機 406」）時，從課程推出年級/班級預填進例外列，只留座號給教師補。
  - **例外的三種來源**：①姓名與課程名稱都推不出年班座號；②**同班座號撞號且姓名不同**（同座號同名＝同一人出現在多門課，靜靜合併不算例外）；③整個課程讀取失敗或沒有學生（以課程為單位列在掃描結果那行，不進表格）。
  - **分段寫入**：Firestore 單一 batch 上限 500 筆，全校名單必然超過，故 `commitChunked()` 以 450 筆為一段依序送出並回報進度。這是「批次寫入應分批而非一次全做」原則（見 §9）的實作。

## 8. 已決策（原「待確認」，教師已定案）
- **繳交對應學生**：年級／班級／學號（三個數字），不用姓名、不需登入。見學習單資料規範 §1。
- **評分粒度**：`score` 題自動核對算 `accuracyRate`；`experience` 題只算 `experienceCompletion`（不進正確率）；`open` 題送 AI／教師給 `totalScore`。三軌並存，非二選一。
- **Classroom 回寫**：選課程即可，**作業不必先在 Classroom 開好**——系統以目前學習單的標題（`curWsCfg.title`）正規化比對該課程的既有作業：
  - **找到同名** → 自動選取那一份，滿分欄帶入該作業的 maxPoints，成績寫進去。
  - **找不到** → 作業下拉預選「建立新作業：{學習單標題}」，按下「回寫成績」時才真的建立（`workType:ASSIGNMENT`、`state:PUBLISHED`、`maxPoints` 可在 UI 改、`materials` 附上學習單網址），建完立刻寫成績。
  - **不會重複建立**：後端 `classroom_create_coursework` 在建立前會再找一次同名作業，找到就直接沿用（前端清單過期或連按兩次都安全）。教師也可隨時從下拉改選任一現有作業。
  - 學生對應：優先用名單裡的 `classroomUserId` 精準比對，退化為姓名比對，對不到可手動指定或設「不回寫」。

## 9. 已知限制與後續強化
- ~~新識別模型無姓名無法自動配對 Classroom~~ → **已解決**：從 Classroom 匯入名單時（教師端「從 Classroom 匯入」）會保留 `classroomUserId`，回寫時用「年級+班級+學號 → 名單 → classroomUserId」精準比對；手動匯入（CSV/貼上/xlsx）的班級仍只能靠姓名猜或手動指定。
- Classroom 學生姓名的自動解析已涵蓋校內三種實際寫法（見 §7），無法解析時匯入表格會標橘色請老師手動填年級/班級/座號。**批量匯入**同樣不因此中斷——把這些人集中到例外清單一次處理完（見 §7）。
- Firestore 免費（Spark）方案：1GiB 儲存、50K 讀/日、20K 寫/日、20K 刪/日、10GiB 傳輸/月（[官方頁面](https://firebase.google.com/pricing)）。單一學校規模（數百學生×每年數十份學習單）遠低於此上限；唯一要注意的情境是**一次性批次評分/寫入全校成千上萬筆**，那種操作應分批而非一次全做。
