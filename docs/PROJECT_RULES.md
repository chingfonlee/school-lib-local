# PROJECT_RULES.md

本文件是本專案內所有 agent 的共用規則唯一來源（SSOT）。
開始工作前必須讀完本文件與 `docs/STATUS.md`。

---

## 讀取順序

1. 先讀本文件（`docs/PROJECT_RULES.md`）
2. 讀 `docs/STATUS.md`
3. 依 `current_action` 執行本文件對應標題章節（見 `## current_action 對應章節`）
4. 若 `current_action` 為 `executing`，依 `current_task` 指定的 task-id，讀取對應的 `{task-id}-spec.md`、`{task-id}-plan.md`、最新 log

---

## Session 狀態模型

`docs/STATUS.md` frontmatter 必備欄位：

```yaml
session_state: closed
current_action: idle
current_task: ""
planning_task: ""
planning_type: ""
planning_base_branch: ""
last_agent: ""
updated: ""
```

### session_state 值定義

- `open`：本次 session 正在進行，尚未正確收尾
- `closed`：本次 session 已完成交接

### current_action 值定義

- `idle`：尚未決定下一步
- `session-start`：正在開工檢查
- `task-planning`：正在規劃新任務
- `executing`：正在實作既有任務
- `session-end`：正在結束本次 session
- `task-close`：準備收束整個任務

### current_task 值定義

- `""`（空字串）：目前無選定 task
- `task-{name}`（例如 `task-web-auth`）：目前選定的 task

`current_task` 在 `current_action: task-planning` 時為 `""`；`current_action: executing` 時必須指向合法、存在且 status 為 active 的 task。

### planning 暫存欄位定義

`planning_task`、`planning_type`、`planning_base_branch` 僅用於 Task Planning 中斷恢復（task-planning resume）：

- `planning_task`：Task Planning Phase A 已確認的 task-id（格式：`task-{name}`）
- `planning_type`：已確認的 task 性質（`feat` / `fix` / `chore`）
- `planning_base_branch`：使用者確認且已驗證存在的 base branch 名稱

規則：

- `current_action: task-planning` 時，三個欄位必須全部有值（由 Phase A A-14 寫入）
- `current_action` 不為 `task-planning` 時，三個欄位必須全部為空字串
- Phase B B-8 在完成 Active Tasks 寫入後清空三個欄位
- `planning_task` 與 `planning_base_branch` 不存在或格式錯誤時，task-planning resume 停止並回報
- Session End 收尾期間可暫時將 `current_action` 設為 `session-end`；若 planning 尚未完成，收尾結束時必須恢復為 `current_action: task-planning` 並保留三個 planning 欄位

### Active Tasks 必備欄位格式

```yaml
- id: task-web-auth
  status: active
  branch: feat/task-web-auth
  base_branch: develop
  last_log: 2026-04-26-143015.md
  last_agent: codex
```

`status` 建議值：`active`、`paused`、`blocked`、`done`

`base_branch`：建立 task branch 時由使用者確認的基底 branch，由 Task Planning Phase B 寫入。

---

## current_action 對應章節

| current_action | 執行本文件章節 |
|---|---|
| `session-start` | Session Start |
| `task-planning` | Task Planning |
| `executing` | Executing |
| `session-end` | Session End |
| `task-close` | Task Close |
| `idle` | 不額外載入章節，只先讀 `docs/STATUS.md` |

---

## Agent 共同行為

- 不得跳過 spec / plan 直接開始寫碼
- 不得自行建立泛用思考文件：`PLAN.md`、`TODO.md`、`NOTES.md`、`ANALYSIS.md`、`THOUGHTS.md`、`SUMMARY.md`
- 先討論，再實作；未經使用者確認，不得直接建立 task 文件或開始寫碼
- Cross-session 需要保留的資訊，寫入 spec、plan、log 或 `STATUS.md`，不只留在提示詞內
- 不得超出 plan 已涵蓋的範圍自行擴張

---

## Session Start

載入時機：`current_action` 為 `session-start`，或 `idle` 且剛進入專案。

### 執行步驟

1. 讀 `docs/STATUS.md`
2. 檢查 `session_state`；若為 `open`，先提醒上次未正確收工，再決定是否補寫 log
3. 驗證 `current_task`：
   - 若非空：在 `## Active Tasks` 中查找對應 task
   - 若不存在或 `status: done`：向使用者回報不一致；本輪視為尚未選定 task，但暫不寫入 STATUS.md
   - 若存在且有效：顯示 task 資訊（id、status、base_branch、last_agent、last_log）
4. 查看 `## Active Tasks` 中所有 `status` 非 `done` 的 task
5. 若沒有未完成 task：
   - 詢問使用者要建立新 task，或維持 idle
   - 若選擇建立新 task：
     - 不修改 STATUS.md
     - 立即結束 Session Start（不執行後續步驟 8–11）
     - 轉入 Task Planning Phase A
     - 由 Task Planning Phase A 步驟 14 在 git 乾淨檢查後統一寫入 STATUS.md
   - 若選擇維持 idle：
     - 確認 `current_task: ""`、`current_action: idle`、`session_state: closed`
     - 立即結束 Session Start（不執行後續步驟 8–11）
6. 若有多個未完成 task（或 `current_task` 為空且有未完成 task）：
   - 列出所有候選 task（id、status、base_branch、last_agent、last_log）
   - 詢問使用者本次要處理哪一個 task，或建立新 task
   - 等待使用者回覆
   - 若選定已有 task：更新 `current_task` 為選定的 task-id
   - 若選擇建立新 task：
     - 不修改 STATUS.md
     - 立即結束 Session Start（不執行後續步驟 8–11）
     - 轉入 Task Planning Phase A
     - 由 Task Planning Phase A 步驟 14 在 git 乾淨檢查後統一寫入 STATUS.md
7. 若只有 1 個未完成 task 且 `current_task` 已指向該 task：
   - 顯示 task 資訊，詢問是否繼續
   - 若是：確認 `current_task`
   - 若否：詢問是否建立新 task 或維持 idle
     - 若選擇建立新 task：不修改 STATUS.md，立即結束 Session Start（不執行後續步驟 8–11），轉入 Task Planning Phase A
     - 若選擇維持 idle：確認 `current_action: idle`、`session_state: closed`，立即結束 Session Start（不執行後續步驟 8–11）
8. 確認 `current_task` 後，讀取 `docs/logs/{task-id}/` 最新 log
9. 向使用者報告目前任務狀態與上次停留位置
10. 更新 `docs/STATUS.md`：
   - `session_state: open`
   - `last_agent: {agent-name}`
   - `updated: YYYY-MM-DD`
11. 確認下一步動作，更新 `current_action`（`executing` 或進入 Task Planning）

### 注意

- 不得跳過 `docs/STATUS.md` 直接讀其他文件
- Session Start 選擇建立新 task 時，不在此步驟寫入 STATUS.md，立即轉入 Task Planning Phase A；後續步驟 8–11 不再執行
- 沒有未完成 task 且使用者選擇維持 idle 時，不得嘗試讀取不存在的 `{task-id}` log
- `current_task` 指向不存在或 done task 時，先視為尚未選定 task，不立即寫入 STATUS.md；後續由選定既有 task、維持 idle 或 Task Planning Phase A A-14 統一寫入正確值

---

## Task Planning

載入時機：`current_action` 為 `task-planning`，或 Session Start 使用者選擇建立新 task。

**建立新 task 與恢復既有 task 的區別**

| 情境 | 適用流程 |
|------|---------|
| 目標 branch 不存在，task-id 無衝突 | 新 task：本章節 Phase A + Phase B |
| Branch 已存在，task 記錄存在 | 恢復 task：Session Start → 選定 current_task → executing |
| Branch 已存在，task 記錄不存在 | 停止，回報狀態不一致，請使用者確認 |

### Task Planning Resume（task-planning resume 流程）

當 `current_action: task-planning` 時，task-planning resume 從 STATUS.md 的 planning 暫存欄位讀取中斷前的狀態，判斷 Phase B 已完成的步驟，決定從哪個步驟接續。不猜測 task-id，僅從 `planning_task` 欄位讀取。

**準備步驟**

1. 讀取 STATUS.md 的 planning 暫存欄位：`planning_task`、`planning_type`、`planning_base_branch`
2. 驗證 planning 欄位：
   - `planning_task` 格式符合 `task-{name}`
   - `planning_type` 僅允許 `feat` / `fix` / `chore`
   - `planning_base_branch` 非空字串
   - 三者必須全部有值；若任一缺失、格式錯誤或互相不一致：停止，回報，不得猜測，等待使用者
3. 確認 `planning_base_branch` 仍存在（`git show-ref --verify refs/heads/{planning_base_branch}`）；若不存在：停止，回報
4. 定義 `expected_task_branch = {planning_type}/{planning_task}`
5. 執行 `git branch --show-current` 讀取目前所在 branch，依結果進入對應路徑

---

**R-4A：目前位於 `planning_base_branch`（task branch 尚未建立）**

6. 執行 `git status --short`，核對允許組合：
   - `docs/STATUS.md`
   - `docs/tasks/{planning_task}/{planning_task}-spec.md`（若已建立）
   - `docs/tasks/{planning_task}/{planning_task}-plan.md`（若已建立）
   - 含其他變更：停止，列出，等待使用者；不得自行處理
7. 顯示 planning 暫存值與已有文件清單，詢問使用者「繼續」或「放棄」
8. 若繼續：補做尚未完成的 spec / plan 建立與確認；進入 Phase B B-5；後續可正常執行 B-6 建立 branch
9. 若放棄：回報需處理文件與 planning 欄位名稱；等待使用者；不得自行清空、刪除、還原、stash、commit 或 discard

---

**R-4B：目前位於 `expected_task_branch`（B-6 已完成）**

不得重複執行 `git checkout -b`。

6. 執行 `git status --short`，核對允許組合：
   - `docs/STATUS.md`
   - `docs/tasks/{planning_task}/{planning_task}-spec.md`
   - `docs/tasks/{planning_task}/{planning_task}-plan.md`
   - 含其他變更：停止，列出，等待使用者；不得自行處理
7. 驗證 spec 與 plan 均存在；若缺失：停止，回報
8. 檢查 `## Active Tasks` 是否已有 `{planning_task}` 對應項目：

   **情況一：無 `{planning_task}` 項目（中斷發生於 B-6 後、B-7 前）**
   - 顯示 planning 暫存值，詢問使用者是否繼續
   - 若繼續：跳過 B-6，執行 B-7（新增 Active Tasks 項目），執行 B-8
   - 若放棄：同 R-4A 放棄流程

   **情況二：已有項目且與 planning 暫存值一致（中斷發生於 B-7 後、B-8 前）**

   驗證項目須符合：
   - `id: {planning_task}`
   - `status: active`
   - `branch: {expected_task_branch}`
   - `base_branch: {planning_base_branch}`

   若一致：顯示已有項目，詢問使用者是否繼續；若繼續：跳過 B-6、B-7，執行 B-8

   **情況三：已有項目但與 planning 暫存值不一致**
   - 停止，回報不一致的具體欄位
   - 不得自行覆寫或修正
   - 等待使用者決定

---

**R-4C：目前位於其他 branch（既非 `planning_base_branch` 也非 `expected_task_branch`）**

- 停止，回報：current branch、planning_base_branch、expected_task_branch
- 不得自行 checkout 或搬移
- 等待使用者決定

---

**Resume 禁止行為**

- 不重複建立 branch（B-6 已完成時不重跑 `git checkout -b`）
- 不重複新增 Active Tasks 項目（B-7 已完成時不重跑 B-7）
- 不得自行修正或覆寫不一致的 Active Tasks 項目
- 不得自動切換 branch
- 放棄時不得自行清空 planning 欄位、刪除文件、stash 或 discard

### Phase A：建立 task 文件前

Phase A 不向磁碟寫入任何文件。步驟 4 與步驟 7 均要求 working tree 完全乾淨（STATUS.md 在此階段尚未被修改）。

1. 使用者確認要建立新 task
2. 詢問並等待使用者確認 base branch 名稱（不預設 `main`、不預設任何值）
3. 執行 `git branch --show-current` 確認目前所在 branch
4. 執行 `git status --short`；若不乾淨：停止，列出所有變更，等待使用者；不得自動 stash、commit、discard 或搬移
5. 確認 base branch 是否存在（`git show-ref --verify refs/heads/{base}`）；若不存在：停止，回報，請使用者確認正確名稱
6. 若目前不在 base branch：執行 `git checkout {base-branch}`；切換失敗則停止並回報
7. 再次執行 `git status --short`；若不乾淨：停止，列出變更，等待使用者
8. 與使用者確認任務目標、範圍、邊界
9. 確認 task 性質：`feat` / `fix` / `chore`
10. 確認 `task-id`（見本文件 `## 命名規則`）
11. 若任務涉及程式碼，確認專案語言、框架與實際驗證指令：
    - 優先讀既有設定，例如 `package.json`、`pyproject.toml`、`go.mod`、`Makefile`
    - 確認 lint / format / typecheck / test / build 指令
    - 若專案尚未定義指令，先與使用者確認，不自行引入大型工具鏈
    - 若任務涉及大型程式碼庫探索、跨檔案結構分析、AST 查詢或自動化重構，再評估是否需要 Tree-sitter
    - Tree-sitter 為可選分析工具，不預設安裝，也不能取代必要驗證；引入前先說明用途、成本與替代方案並等待使用者確認
12. 確認 task-id、`docs/tasks/{task-id}/`、`docs/logs/{task-id}/`、`docs/STATUS.md` 中的 task 記錄、`git branch -a` 均無衝突；若有衝突：停止，回報，請使用者重新命名
13. 確認目標 branch `{type}/{task-id}` 是否已存在：
    - 若已存在：停止，回報「此為新 task 建立流程，branch 已存在，請透過 Session Start 選定此 task」；不得繼續
    - 若不存在：繼續
14. 寫入 `docs/STATUS.md` frontmatter（一次完成）：
    - `session_state: open`
    - `current_action: task-planning`
    - `current_task: ""`
    - `planning_task: {步驟 10 確認的 task-id}`
    - `planning_type: {步驟 9 確認的 feat / fix / chore}`
    - `planning_base_branch: {步驟 2 確認的 base branch}`
    - `last_agent: {agent-name}`
    - `updated: YYYY-MM-DD`

Phase A 完整執行後（步驟 1–14 全部通過），才進入 Phase B。

### Phase B：建立文件並確認後，執行 branch 建立

Phase B 開始時，working tree 預期狀態：`docs/STATUS.md` 已由 Phase A 步驟 14 修改，其餘無任何變更。

1. 建立 `docs/tasks/{planning_task}/{planning_task}-spec.md`
2. 請使用者確認 spec
3. 建立 `docs/tasks/{planning_task}/{planning_task}-plan.md`
4. 請使用者確認 plan
5. 執行 `git status --short`，核對變更清單：
   - 允許：`docs/STATUS.md`（Phase A 步驟 14 修改）、spec（新增）、plan（新增）
   - 若出現其他非預期變更：停止，列出，等待使用者；不得自動 stash、commit、discard

**B-6、B-7、B-8 必須依序執行。若流程在 B-6 後中斷，下次 session 必須經 Task Planning Resume 判斷已完成的步驟，不得直接重跑 Phase B。**

6. 建立 branch：`git checkout -b {planning_type}/{planning_task}`（使用 planning 暫存值）
7. 更新 `docs/STATUS.md` 的 `## Active Tasks`，新增項目（使用 planning 暫存值）：
   ```yaml
   - id: {planning_task}
     status: active
     branch: {planning_type}/{planning_task}
     base_branch: {planning_base_branch}
     last_log: ""
     last_agent: ""
   ```
8. 更新 `docs/STATUS.md` frontmatter（先完成 B-7 Active Tasks 寫入，再清空 planning 欄位）：
   - `current_task: {planning_task}`
   - `current_action: executing`
   - `planning_task: ""`
   - `planning_type: ""`
   - `planning_base_branch: ""`
   - session_state 維持 `open`（由 A-14 設定，B-8 不重複修改）

### task spec 範本

```markdown
# Spec: {task-id}

## 目標


## 需求範圍


## 不做的事


## 驗收條件
```

### task plan 範本

```markdown
# Plan: {task-id}

## 實作步驟

1.
2.
3.

## 風險與注意事項


## 預計影響範圍


## 驗證指令

- lint:
- format:
- typecheck:
- test:
- build:

## 成果報告

- result_report_mode: none
- 適用情境：
- 報告路徑（若 mode 非 none）：`docs/reports/{task-id}/`
```

### 禁止行為

- 未經使用者確認就直接建立 branch
- 未檢查重名就直接建立 `task-id`
- 跳過 spec / plan 直接開始寫碼
- 任務涉及程式碼時，未確認驗證指令就開始實作
- 未確認 `result_report_mode` 就建立 result report
- 在 executing 階段調整 `result_report_mode` 時，未取得使用者確認就修改
- Phase A git status 不乾淨時繼續建立文件或 branch
- 目標 branch 已存在時繼續 Task Planning 新建流程
- Session Start 選擇新 task 時在 Session Start 寫入 STATUS.md（應由 Task Planning Phase A 步驟 14 統一寫入）
- 使用 `git reset --hard` 或 `git checkout -- .` 處理 dirty tree
- 自動 stash、commit、discard 或搬移既有變更

---

## Executing

載入時機：`current_action` 為 `executing`。

### 前置條件與 current_task 驗證

進入 executing 前，必須逐項驗證（任一失敗即停止）：

| 驗證項目 | 失敗時行為 |
|---------|-----------|
| `current_task` 非空字串 | 停止，回報未選定 task，請使用者確認 |
| `current_task` 格式符合 `task-{name}` | 停止，回報格式不合法，請使用者修正 STATUS.md |
| `current_task` 存在於 Active Tasks | 停止，回報指向不存在的 task |
| 對應 task 的 `branch` 非空字串 | 停止，回報 branch 欄位缺失 |
| 對應 task 的 `base_branch` 非空字串 | 停止，回報 base_branch 欄位缺失 |
| 對應 task 的 `status`（見下表） | 依狀態處理 |
| `git branch --show-current` 實際 branch 等於 Active Tasks 的 `branch` 欄位 | 不一致：停止，回報 current_task、預期 branch、實際 branch；等待使用者決定；不得自動 checkout、stash、commit 或 discard |

**paused / blocked / done 處理**

| status | 行為 |
|--------|------|
| `active` | 通過驗證，進入 executing |
| `paused` | 顯示 task 資訊（id、branch、base_branch、last_log），詢問使用者是否恢復；確認後更新 `status: active`，再進入 executing |
| `blocked` | 顯示 task 資訊與上次 log 的阻塞原因，詢問阻塞是否已解除；僅使用者明確確認解除後，更新 `status: active`，再進入 executing；agent 不得自行解除 blocked |
| `done` | 停止，回報 current_task 指向已完成的 task，不得進入 executing |

驗證通過後：

- 已讀 `docs/STATUS.md`
- 已讀 `docs/tasks/{task-id}/{task-id}-spec.md`
- 已讀 `docs/tasks/{task-id}/{task-id}-plan.md`
- 已讀 `docs/logs/{task-id}/` 最新 log（若有）

### 執行規則

- 只做 `{task-id}-plan.md` 已涵蓋的事
- 每次有意義的變更後 commit
- commit 格式：

```text
{type}({task-id}): {short-description}
```

- 若發現新需求超出 `{task-id}-plan.md`，先停下來與使用者討論

### 測試要求

有程式碼變更的 session，結束前依 `{task-id}-plan.md` 的「驗證指令」執行必要檢查：

1. lint / format
2. typecheck / test
3. build

若無法執行，必須在 log 說明原因與風險。

### 結束動作

完成本次工作後，根據狀態選擇路徑：

**路徑 A：本次 session 完成部分工作，任務尚未結束**

1. 向使用者說明本次進度
2. 執行本文件 `## Session End` 章節的收工流程

**路徑 B：實作與驗證完成，準備收束整個任務**

1. 讀取 `{task-id}-plan.md` 的 `result_report_mode`
   - 若 `result_report_mode` 非 `none`，依本文件 `## Result Report 規範` 章節建立並驗證 result report
     - 將 report commit 至 task branch（report 屬於 task 變更，必須 commit 後 working tree 才乾淨）
     - 向使用者回報 report 路徑與驗證結果
2. 向使用者報告完成情況與驗證結果
3. 等待使用者明確確認任務完成（使用者可在此時檢查 report）
4. 詢問並等待使用者確認 merge 目標 branch 名稱（不預設為 `main`）；可提示 Active Tasks 中對應 task 的 `base_branch` 作為參考，但 merge 目標仍須使用者明確確認，不得自動採用 `base_branch`
5. 執行 `git status`，確認 working tree 乾淨（無未 commit 的變更）
6. 確認所有 task 變更已 commit
7. 若 `result_report_mode` 非 `none`，再次確認必要 report 已存在且驗證完成：
   - **若 report 已存在且驗證完成**：繼續步驟 8
   - **若 report 缺失或驗證未完成**：
     a. 依本文件 `## Result Report 規範` 補建並驗證 report
     b. 將 report commit 至 task branch
     c. 重新執行 `git status`，確認 working tree 乾淨
     d. 再次確認所有 task 變更已 commit
     e. 確認後繼續步驟 8
8. 更新 `docs/STATUS.md` 的 `current_action: task-close`
9. 執行本文件 `## Task Close` 章節（task-close 自行完成 session 收尾，不再另外執行 Session End）

步驟 4–6 必須在更新 `task-close` 之前完成，以避免 Stop hook 在等待使用者確認 branch 名稱時阻斷回應。

---

## Session End

載入時機：每次 session 結束前（任務尚未完成時）。

### 離開清單

#### 步驟 1：標記收尾狀態

更新前先檢查 planning 暫存欄位：

- 若三個 planning 欄位均有值：記錄本次為「task-planning 未完成」收尾
- 若三個 planning 欄位部分有值、部分為空：停止，回報 STATUS.md 狀態不一致，不自動清空
- 若三個 planning 欄位均為空：依一般 Session End 流程處理

更新 `docs/STATUS.md` frontmatter：

```yaml
current_action: session-end
```

此步驟必須最先執行，以確保收尾中途若 Claude Code 嘗試停止，Stop hook 能正確阻塞。

#### 步驟 2：依 task 狀態分支

**task-planning 未完成時：**

- 不強制建立 log
- 不修改 `current_task` 或三個 planning 欄位
- 若需記錄本次討論摘要，可選擇性補充在 STATUS.md body，不建立新文件
- 跳至步驟 3，使用 task-planning 未完成的 frontmatter 收尾值

**有 active task 時：**

1. 驗證 `current_task`：
   - 必須非空
   - 必須存在於 `## Active Tasks`
   - 對應項目的 `status` 必須為 `active`
   - 若驗證失敗：停止，回報不一致，不猜測 task-id，不自動改選其他 task
2. 使用 `current_task` 作為本次 `{task-id}`，建立當日 log：
   - 檔名格式：`YYYY-MM-DD-HHmmss.md`（PowerShell：`Get-Date -Format "yyyy-MM-dd-HHmmss"`）
   - 路徑：`docs/logs/{current_task}/`
   - 若同秒碰撞，附加序號：`YYYY-MM-DD-HHmmss-01.md`
3. 填寫以下欄位：
   - `## 做了什麼`
   - `## 驗證到哪`
   - `## 未解決的問題`
   - `## 下次繼續`
4. 更新 `docs/STATUS.md` 的 `## Active Tasks` 區塊，只更新 `current_task` 對應的任務：
   - `last_log: {完整 log 檔名，含副檔名}`（例如 `2026-05-30-143015.md`）
   - `last_agent: {agent-name}`
5. 若 `result_report_mode` 非 `none`：
   - 只記錄已存在的 report 路徑於 log 的 `## 驗證到哪` 或 `## 做了什麼`
   - 尚未建立的 report 路徑不得記入已完成成果
   - 若 report 尚未建立但後續仍需完成，寫入 `## 下次繼續`

**無 active task 時（純討論、需求確認等）：**

- 不強制建立 log
- 若需記錄本次討論摘要，可選擇性補充在 STATUS.md body，不建立新文件

#### 步驟 3：更新 STATUS.md frontmatter

**若 task-planning 未完成：**

```yaml
last_agent: {agent-name}
updated: YYYY-MM-DD
current_action: task-planning
session_state: closed
```

保留 `current_task: ""` 與三個 planning 欄位原值。下次載入時依 `current_action: task-planning` 進入 Task Planning Resume。

**其他情境：**

```yaml
last_agent: {agent-name}
updated: YYYY-MM-DD
current_action: idle
session_state: closed
```

### log 範本

```markdown
---
date: YYYY-MM-DD
ended_at: YYYY-MM-DDTHH:mm:ss
task: {task-id}
agent: {agent-name}
---

## 做了什麼


## 驗證到哪


## 未解決的問題


## 下次繼續
```

`date` 為純日期（`YYYY-MM-DD`），`ended_at` 為 ISO 8601 本地時間（`YYYY-MM-DDTHH:mm:ss`），對應 log 檔名的時間戳記。

### 注意

- `下次繼續` 不得空白；若無未解決問題，填 `無`
- `last_log` 屬於 `## Active Tasks` 區塊的任務項目，不是 STATUS.md frontmatter 欄位
- 多個 active task 存在時，只能依已驗證的 `current_task` 建立 log 與更新 Active Tasks，不得猜測或自動切換
- task-planning 未完成時，`session-end` 僅為收尾期間的暫時值；收尾完成後必須恢復 `current_action: task-planning` 並保留 planning 暫存欄位
- 若未完成以上步驟，Claude Code 的 Stop hook 在 `current_action: session-end` 時會阻塞退出

---

## Task Close

載入時機：`current_action` 為 `task-close`，且使用者已明確確認任務完成。

### 前置條件

以下條件均由 `## Executing` 路徑 B 完成，進入本章節時必須已全部滿足：

- 使用者已明確說明任務完成
- merge 目標 branch 已由使用者確認
- `git status` 已執行，working tree 乾淨（無未 commit 的變更）
- 所有 task 變更已 commit
- `current_action` 已更新為 `task-close`（由 Executing 路徑 B 負責更新）
- `{task-id}-plan.md` 的驗證指令已執行，必要的 lint / format / typecheck / test / build 已 pass
- 若 `result_report_mode` 非 `none`，必要 report 已存在且驗證完成（由 Executing 路徑 B 步驟 7 確認傳入）

進入 Task Close 時，必須先驗證 planning 欄位一致性：

- 確認 `planning_task`、`planning_type`、`planning_base_branch` 均為空字串
- 若任一欄位非空：停止，回報「STATUS.md 狀態不一致，planning 欄位仍有值」，不自動清空，等待使用者確認

### 執行步驟

#### 1. Merge

```bash
git checkout {已確認的目標 branch}
git merge {type}/{task-id}
```

**merge 結果判斷**

**若 merge 成功：**
→ 繼續執行步驟 2（Post-merge 收尾）

**若 merge 發生 conflict 或失敗：**
1. 不建立最終 log
2. 不將 task 標記為 done
3. 不刪除 branch
4. 更新 `docs/STATUS.md` frontmatter：`current_action: executing`（保持 `session_state: open`）
5. 回報 merge 結果、衝突檔案清單與建議處理方式
6. 等待使用者決定
7. 若使用者決定中止 merge：取得明確確認後，執行 `git merge --abort`
8. 不得自行使用 `git reset --hard` 或 `checkout -- .` 覆蓋檔案

#### 2. Post-merge（順序不可對調）

2. 建立最終 log：
   - 檔名格式：`YYYY-MM-DD-HHmmss.md`（PowerShell：`Get-Date -Format "yyyy-MM-dd-HHmmss"`）
   - 路徑：`docs/logs/{task-id}/`
   - 若同秒碰撞，附加序號：`YYYY-MM-DD-HHmmss-01.md`
   - 若 `result_report_mode` 非 `none`，將已完成 report 路徑記錄進 log（不建立、不修改 report）
3. 確認 log 檔案存在
4. 更新 `docs/STATUS.md` 的 `## Active Tasks` 區塊，找到對應任務並更新：
   - `status: done`
   - `branch: ""`
   - `last_log: {完整 log 檔名，含副檔名}`（例如 `2026-05-30-143015.md`）
   - `last_agent: {agent-name}`
5. 更新 `docs/STATUS.md` frontmatter：
   - `current_action: idle`
   - `session_state: closed`
   - `last_agent: {agent-name}`
   - `updated: YYYY-MM-DD`
   - 若 `current_task` 等於本次關閉的 task-id：清空 `current_task: ""`；若不等於：保持不變
   - 不自動選擇其他 task
6. commit 最終 log 與 STATUS.md：

```text
chore({task-id}): close task records
```

7. 再次執行 `git status`，確認 working tree 乾淨

#### 3. 詢問 branch 清理

8. 詢問使用者是否刪除本地 task branch（不自動執行）
9. 說明遠端 branch 不會自動刪除，需使用者自行決定

### 最終 log 範本

```markdown
---
date: YYYY-MM-DD
ended_at: YYYY-MM-DDTHH:mm:ss
task: {task-id}
agent: {agent-name}
---

## 做了什麼

任務完成。

## 驗證到哪

依 `{task-id}-plan.md` 驗證指令執行：lint pass、build pass、使用者確認完成。

## 未解決的問題

無

## 下次繼續

已完成
```

### 注意

- `last_log` 屬於 `## Active Tasks` 區塊的任務項目，不是 STATUS.md frontmatter 欄位
- STATUS.md 更新必須在 log 建立並確認存在後才執行，避免 STATUS.md 指向尚未建立的 log
- 收尾 commit 位於 merge 目標 branch 上，不在 task branch 上
- task-close 自行完成所有 session 收尾，不需另外執行 Session End
- 步驟 8（詢問是否刪除 branch）執行時，STATUS.md 已為 `session_state: closed`，不會被 Stop hook 阻塞
- 任務完成後，保留 `docs/tasks/{task-id}/` 與 `docs/logs/{task-id}/` 作為紀錄

---

## 命名規則

引用時機：task-planning 階段，確認 task-id、branch、文件路徑時。

### Task-id

格式：

```text
task-{name}
```

規則：

- 固定以 `task-` 開頭
- 全部小寫，使用 kebab-case
- 預設優先使用具體且可讀的名稱，例如 `task-web-auth`、`task-api-login`
- 建立前必須檢查 `docs/tasks/`、`docs/logs/`、`docs/STATUS.md` 與現有 branch
- 若名稱可能混淆，先補範圍或場景
- 若已足夠具體仍衝突，才在尾端加日期，例如 `task-web-auth-20260426`

### Branch

格式：

```text
{type}/{task-id}
```

只允許：

- `feat/{task-id}`
- `fix/{task-id}`
- `chore/{task-id}`

### 路徑對應

- `docs/tasks/{task-id}/{task-id}-spec.md`
- `docs/tasks/{task-id}/{task-id}-plan.md`
- `docs/logs/{task-id}/YYYY-MM-DD-HHmmss.md`（碰撞時附加 `-01`、`-02`）

三者必須與 branch 對應同一個 `task-id`。

### 禁止模式

不得使用：

```text
new-* / *-new
test-* / *-test
temp-* / *-temp
v2-* / *-v2
copy-* / *-copy
final-* / *-final
```

---

## 文件格式

引用時機：建立 spec、plan、log 時。

### 語言與格式

- 主要使用繁體中文
- 英文技術術語保留原文，例如 `branch`、`commit`、`lint`
- 中文與英文之間加一個空格
- Markdown 使用 UTF-8 without BOM、LF、保留 final newline

### 語氣

- `{task-id}-spec.md`：陳述式，描述系統應有行為
- `{task-id}-plan.md`：指令式，動詞開頭
- session log：過去式，記錄已完成事實
- rules / skills：指令式，直接說明行為

### task spec 必備欄位

- `## 目標`
- `## 需求範圍`
- `## 不做的事`
- `## 驗收條件`

### task plan 必備欄位

- `## 實作步驟`
- `## 風險與注意事項`
- `## 預計影響範圍`
- `## 驗證指令`
- `## 成果報告`

### session log 必備欄位

**frontmatter**

```yaml
---
date: YYYY-MM-DD
ended_at: YYYY-MM-DDTHH:mm:ss
task: {task-id}
agent: {agent-name}
---
```

- `date`：純日期（`YYYY-MM-DD`），人工辨識用
- `ended_at`：ISO 8601 本地時間（`YYYY-MM-DDTHH:mm:ss`），對應 log 檔名時間戳記

**body**

- `## 做了什麼`
- `## 驗證到哪`
- `## 未解決的問題`
- `## 下次繼續`

`下次繼續` 不得空白；若無未解決問題，填 `無`。

---

## Result Report 規範

引用時機：建立 result report、驗證 HTML report 或確認 reporting 規範時。

### 輸出模式

`result_report_mode` 設定於 `{task-id}-plan.md` 的 `## 成果報告` 區塊：

| 模式 | 說明 |
|------|------|
| `none` | 不產生成果報告（預設值） |
| `md` | 僅產生 Markdown 成果報告 |
| `html` | 僅產生 HTML 成果報告 |
| `both` | 同時產生 md 與 html |

預設值為 `none`。若在 executing 階段需要調整，必須取得使用者確認並同步更新 plan。

### 命名規則

| 格式 | 路徑 |
|------|------|
| Markdown | `docs/reports/{task-id}/{task-id}-result-report.md` |
| HTML | `docs/reports/{task-id}/{task-id}-result-report.html` |

### Markdown 報告格式

必備 frontmatter：

```yaml
type: result_report
task: {task-id}
date: YYYY-MM-DD
result_report_mode: md  # 或 both
```

- 編碼：UTF-8 without BOM、LF、final newline
- 不得包含敏感資料（token、密碼、內部 IP 等）

### HTML 報告格式

必須為 standalone HTML（單一檔案，無外部依賴）。

必備結構：

```html
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{task-id} 成果報告</title>
  <style>/* inline CSS */</style>
</head>
<body><!-- 報告內容 --></body>
</html>
```

### 外部資源依賴限制

禁止：外部 CSS、外部 CDN、遠端字型、外部 script（`<script src="...">`）、`<iframe>`、`<embed>`、`<object>`。

預設禁止（例外需在 plan 說明並取得使用者確認）：

- inline `<script>` 區塊
- base64 圖片嵌入

允許：一般超連結 `<a href="...">`。

### HTML 驗證掃描項目

產生 HTML report 後逐項掃描：

| 掃描項目 | 處理方式 |
|---------|---------|
| `<script src` | 禁止 |
| `<link` | 人工確認；外部 CSS、字型、CDN 禁止 |
| `@import` | 禁止 |
| `url(` | 人工確認括號內無遠端或相對路徑資源 |
| `http://` | 人工確認為一般超連結，非資源依賴 |
| `https://` | 人工確認為一般超連結，非資源依賴 |
| `src=` | 人工確認；禁止相對路徑（如 `./image.png`）或外部資源；若為已取得使用者確認的 inline base64，依 base64 規則處理 |
| `srcset=` | 人工確認；禁止相對路徑或外部資源 |
| `poster=` | 人工確認；禁止相對路徑或外部資源 |
| `base64` | 預設禁止；例外需 plan 已說明且使用者已確認 |
| `<script` | 預設禁止 inline JS；例外需 plan 已說明且使用者已確認 |

允許：一般超連結 `<a href="...">` 可以存在；不全面禁止 `href=`。

驗證步驟：

1. 確認必備 HTML 結構存在（DOCTYPE、lang、charset、viewport、title）
2. 依掃描表逐項搜尋
3. 人工確認 `src=`、`srcset=`、`poster=` 無相對路徑或外部資源
4. 以本地瀏覽器開啟，確認中文顯示正常、無亂碼

### Report 生命週期

- report 在 executing 階段完成，進入 task-close 前必須已存在並 commit
- Task Close 章節不建立、不修改 report；以「report 已存在且驗證完成」作為前置條件
- post-merge 只將 report 路徑寫入最終 log

### Log 與 STATUS.md 記錄邊界

- log 只記錄已存在的 report 路徑
- 尚未建立的 report 路徑寫入 log 的 `## 下次繼續`
- report 路徑不寫入 `docs/STATUS.md`

---

## Git 規則

- 每個 task 使用獨立 branch
- branch 格式只用 `feat/{task-id}`、`fix/{task-id}`、`chore/{task-id}`
- commit message 使用 `{type}({task-id}): {short-description}`
- type 必須與 branch 前綴一致：`feat` branch 用 `feat(...)` type；`fix` branch 用 `fix(...)` type；`chore` branch 用 `chore(...)` type
- merge 前確認 working tree 乾淨（`git status` 無未 commit 的變更）
- 建立 `task-id` 前先做重名檢查；若可能混淆，先改成更具體名稱，必要時再加日期尾碼

---

## 驗證責任

### 決策流程

```text
開始 task-planning
↓
讀既有設定（package.json、pyproject.toml、go.mod、Makefile 等）
↓
有既有指令？
  → 是：沿用既有（3.1）
  → 否：
      語言有主流慣例 + 侵入程度低 + 六項條件全部成立？
        → 是：提出建議，等待使用者確認（3.2）
        → 否：
            有爭議或不確定？
              → 是：詢問使用者（3.3）
              → 否：標記無法執行，記錄原因（3.4）
```

### 3.1 沿用既有

條件：專案已有 lint / format / typecheck / test / build 指令（package.json scripts、Makefile target、CI yml 步驟等）

行為：
- 直接使用既有指令，不換工具，不修改設定
- 在 `{task-id}-plan.md` 驗證指令欄位填入實際指令

### 3.2 建議新工具（需使用者確認）

下列六個條件**全部成立**，才可向使用者提出建議：

1. 專案尚無既有 lint / formatter 設定
2. 該語言或框架有明確主流慣例
3. 工具侵入程度低
4. 安裝與維護成本可控
5. 不會為了單一 task 引入大型工具鏈
6. 已清楚列出替代方案、風險與驗證方式

提出建議時必須包含：
- 建議理由
- 替代方案列表
- 若不引入的影響說明

提出建議後必須：
- 等待使用者明確確認後才執行
- 不得提前建立設定文件或安裝 dependencies

### 3.3 詢問使用者

下列任一條件成立，必須停下詢問，不得自行假設：

- 工具選擇有爭議（多種主流方案並存，無明確社群共識）
- 侵入程度高（需新增 devDependencies、修改 lock file）
- 現有設定衝突（多份設定文件互相矛盾）
- 不確定現有工具是否仍在使用

### 3.4 不得自行引入

下列任一條件成立，不得執行工具引入：

- 使用者尚未確認
- 為完成單一 task 需引入大型工具鏈
- 需修改與當前 task 無直接關係的設定
- 使用者明確說明不引入新工具

行為：
- 說明現況與風險
- 在 log 記錄未能執行驗證的原因與建議的下次驗證方式

### task plan 驗證指令欄位

`{task-id}-plan.md` 的驗證指令欄位必須填入以下其中之一：

| 情況 | 填入方式 |
|------|---------|
| 有既有指令 | 填入實際指令，例如 `npm run lint`、`go test ./...` |
| 尚未確認工具 | 填入「待確認」，並說明原因 |
| 無法執行 | 填入「無法執行」，並說明原因與風險 |

不得留空。

### session log 與 task-close log 記錄

每次執行檢查後必須記錄：

- 實際執行的指令
- 結果（pass / fail / 跳過）
- 若跳過或失敗，說明原因與風險

### Tree-sitter 使用邊界

- Tree-sitter 是可選的語法結構分析工具，不屬於 lint / formatter / typecheck / test / build
- 範本不預設安裝 Tree-sitter、bindings 或任何語言 grammar
- 當任務涉及大型程式碼庫探索、跨檔案結構分析、AST 查詢或自動化重構時，可依提示詞評估是否使用
- 引入 Tree-sitter、bindings 或語言 grammar 前，必須說明用途、安裝成本、替代方案與預期收益，並等待使用者確認
- 若現有工具已足以完成分析，不額外引入 Tree-sitter
- Tree-sitter 的分析結果不能取代必要的 lint / formatter / typecheck / test / build 驗證
