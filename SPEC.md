# 評分平台 · 規格書（SPEC）

> 學生繳交互動學習單 → 資料庫 → 教師端以班級為單位進行 AI／標準答案評分與成績管理。
> 本檔是**契約**；每次施工前先讀這裡與 `PROGRESS.md`，完成後更新 `PROGRESS.md`。

## 0. 目標與原則
- **目的**：協助教師「精準、快速」進行課堂評量與成績管理。
- **對象**：教師（管理端）＋ 學生（作答繳交端）。
- **介面**：教師端是**專業工具**——乾淨、資訊密度高、**不使用 emoji**（emoji 只屬於給小學生的互動教材）。學生端沿用既有互動教材風格。
- **串聯既有系統**：後端特權操作（AI 評分、Google Classroom 成績回寫、金鑰）一律走既有 `工作台/server.py`（新增 API），不另存金鑰。資料庫沿用既有 Firebase 專案 `pcclass-94300`（Firestore）。
- **設計脈絡**：學生端只負責「把答案完整送進資料庫」；所有評分與成績邏輯集中在教師端＋server，避免答案／評分規則落在學生看得到的地方。

## 1. 系統架構
```
學生互動 HTML（materials/…/index.html）
   └─(繳交)→ Firestore  submissions/{wsId}__{grade}-{className}-{studentId}
                         ▲                         │
教師管理端 評分平台/teacher.html ─────────────────┘ (讀 submissions、寫回 score/feedback)
   └─(AI評分 / Classroom回寫 / 匯入匯出)→ 工作台/server.py 新 API（持金鑰）
```
- **Firestore**：唯一的繳交／成績資料庫（client SDK，student 匿名、teacher Email/密碼）。
- **teacher.html**：讀 Firestore 呈現＋批改；特權動作打 `http://127.0.0.1:8770` 的新 API。
- **server.py**：新增評分／Classroom 成績／名單匯入匯出 API（讀 config.json 的 AI key、github、google token）。

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

## 4. server.py 新增 API（已實作）
| 路由 | 功能 |
|---|---|
| POST `/api/grade` | 收 {answers, answerKey?, rubric?, questions?} → 標準答案核對＋開放題丟 AI（`grade_call`，見《AI串接窗口設定規範》）→ 回 {autoScore, aiScore, aiFeedback, perItem[]} |
| POST `/api/grade-scratch` | 收 .sb3（base64）→ 解析 project.json → 回積木/精靈/概念盤點（評分邏輯待接） |
| GET `/api/grade-models` | 列評分 AI 窗口可用模型（未設 grade_key 時回退主 AI） |
| GET `/api/fetch-title` | 讀某網址 `<title>`（新增學習單時自動帶標題） |
| GET `/api/classroom/coursework` | 列某 Classroom 課程的作業 |
| GET `/api/classroom/students` | 列某 Classroom 課程名單（需 `classroom.rosters.readonly` scope） |
| POST `/api/classroom/grades` | 回寫分數到指定 courseWork（patch draft+assigned 後 `:return`） |
| POST `/api/git-publish` | 把某節 `06_成品.html`＋`assets/` 整包 SSH push 到 GitHub Pages |
- 名單匯入（CSV/貼上）與成績 CSV 匯出目前**純前端**處理（見 `teacher.html`），未走 server。

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

## 8. 已決策（原「待確認」，教師已定案）
- **繳交對應學生**：年級／班級／學號（三個數字），不用姓名、不需登入。見學習單資料規範 §1。
- **評分粒度**：`score` 題自動核對算 `accuracyRate`；`experience` 題只算 `experienceCompletion`（不進正確率）；`open` 題送 AI／教師給 `totalScore`。三軌並存，非二選一。
- **Classroom 回寫**：維持半自動——選課程＋作業，系統以姓名比對（新式提交無姓名時退化為手動指定，已知限制，見下）。

## 9. 已知限制與後續強化
- ~~新識別模型無姓名無法自動配對 Classroom~~ → **已解決**：從 Classroom 匯入名單時（教師端「從 Classroom 匯入」）會保留 `classroomUserId`，回寫時用「年級+班級+學號 → 名單 → classroomUserId」精準比對；手動匯入（CSV/貼上/xlsx）的班級仍只能靠姓名猜或手動指定。
- Classroom 學生姓名若沒有照「{年級}{班級2碼} {座號} {姓名}」（如 `510 01 王小明`）的格式命名，自動解析會失敗，匯入表格會標橘色請老師手動填年級/班級/座號。
- Firestore 免費（Spark）方案：1GiB 儲存、50K 讀/日、20K 寫/日、20K 刪/日、10GiB 傳輸/月（[官方頁面](https://firebase.google.com/pricing)）。單一學校規模（數百學生×每年數十份學習單）遠低於此上限；唯一要注意的情境是**一次性批次評分/寫入全校成千上萬筆**，那種操作應分批而非一次全做。
