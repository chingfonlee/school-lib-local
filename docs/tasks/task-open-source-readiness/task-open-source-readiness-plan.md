# Plan: task-open-source-readiness

## 實作步驟

### Phase 1：設定檔開源化

1. 確認 `git ls-files config.yaml` 輸出非空（目前已確認為追蹤中）
2. 執行 `git rm --cached config.yaml`，將 `config.yaml` 從索引移除，本機檔案保留
3. 在 `.gitignore` 新增 `config.yaml` 條目
4. 建立 `config.example.yaml`：以現有 `config.yaml` 為藍本，做以下修改：
   - `auth.default_admin_password` 改為 `"<change-me>"`
   - `auth.session_secret_key` 改為 `"<generate-a-random-secret>"`
   - `source.local_culture_export_template` 保留佔位路徑格式，移除任何實際學校名稱（路徑已含「○○」佔位符，確認後保留）
   - `export_templates` 中的 `template_file_path` 同上處理
   - `default_project.name` 改為通用名稱（例如 `"115年度採購"`)
   - 在文件頂端加上安全警告註解區塊
5. 確認 `git status` 顯示 `config.yaml` 已從追蹤移除（出現於 deleted 或無），`config.example.yaml` 為新增

### Phase 2：.gitignore 補強與工作目錄清理

6. 在 `.gitignore` 新增以下條目（若尚未包含）：
   - `tmp/`
   - `*.log`：新增前先執行 `git ls-files "*.log"` 確認無已追蹤的 `.log` 檔案；`docs/logs/` 下的 session log 副檔名為 `.md`，不受 `*.log` 規則影響；此規則目的為阻止未來 runtime log 被意外提交，不涉及現有 `docs/logs/` 記錄
7. 確認 `git ls-files` 無 `data/`、`exports/`、`00_source/`、`tmp/`、`config.yaml`

### Phase 3：開源基本文件

8. 建立 `LICENSE`（MIT License 已確認，填入正確年份與著作權人）
9. 更新 `README.md`，新增以下段落：
    - **授權**：標示本專案採用 MIT License
    - **開發者安裝**：手動 venv 建立步驟（`python -m venv .venv`、啟動 venv、`pip install -r requirements.txt`）
    - **設定檔初始化**：`cp config.example.yaml config.yaml`（或 Windows `copy`），並提醒修改密碼與 session secret
    - **測試**：`.venv\Scripts\python.exe -m pytest -q`（Windows）
    - **Python 版本**：建議 3.11 / 3.12，不支援 3.14
    - **開發文件說明**：一行說明 `docs/tasks/` 與 `docs/logs/` 為 agent 工作流程記錄，非使用者必讀
11. 更新 `docs/user-guide/install-windows.md`：補充設定檔初始化步驟（從 `config.example.yaml` 建立 `config.yaml`，修改密碼）
12. 建立 `CONTRIBUTING.md`：說明回報問題方式、PR 流程、branch 命名規則
13. 建立 `SECURITY.md`：說明如何回報安全漏洞、回應時程、聯絡方式

### Phase 4：CI（GitHub Actions）

14. 建立 `.github/workflows/ci.yml`，結構如下：
    - trigger：`push`（`main` 與 `chore/**`、`feat/**`、`fix/**`）、`pull_request`
    - matrix：Python 3.11、3.12
    - steps：checkout → setup-python → `pip install -r requirements.txt` → `pytest -q`
    - 不包含 Windows runner（GitHub Actions 預設 ubuntu，可另行評估）
15. 確認 workflow YAML 語法正確（縮排、key 名稱）

### Phase 5：靜態資產

16. `app/static/img/library-procurement-bg.webp` 為 AI 生成素材，已確認可納入公開 repo：
    - 執行 `git add app/static/img/library-procurement-bg.webp` 將檔案加入追蹤
    - 若 README 或文件中有資產授權說明區塊，標註此圖片為「專案自有 / AI 生成素材，MIT License」
17. 確認 `git ls-files app/static/img/` 輸出包含此檔案

### Phase 6：敏感資料與公開內容掃描

18. 執行掃描，對象為 git 追蹤檔案：
    ```
    git grep -n -I -E "password|secret|token|api[_-]?key|changeme|please-change|C:\\|Users\\" -- .
    ```
    （`rg` 在本機 PowerShell PATH 中不可用，以 `git grep` 替代；掃描範圍自動限於已追蹤檔案，無需額外排除 `.venv/`）

19. 人工確認命中結果——**Phase 6 已完成（2026-06-26）**，結論如下：

    **OK（無風險）：**
    - `app/` 原始碼：欄位名稱（`password_hash`、`session_secret_key`）、bcrypt 操作、HTML 表單欄位
    - `config.example.yaml`：`<change-me>`、`<generate-a-random-secret>` placeholder
    - `README.md`、`CONTRIBUTING.md`、`SECURITY.md`、`docs/user-guide/install-windows.md`：操作說明文字，無實際值
    - `start.bat`：使用者提醒訊息
    - `migrations/001_initial_schema.sql`：SQL schema 欄位 `password_hash`
    - `docs/tasks/task-project-budget-summary/...-plan.md`：`session=<token>` 為 curl 測試 placeholder
    - 其餘 `docs/tasks/`、`docs/logs/` 命中：任務描述與規則說明脈絡

    **需確認（已確認可保留）：**
    - `docs/tasks/task-local-cultural-books-mvp/task-local-cultural-books-mvp-plan.md:639-640`：
      歷史設計草稿中含 `default_admin_password: "changeme"` 與 `session_secret_key: "please-change-this-to-a-random-string"`
      → 使用者已確認可保留。理由：已完成任務的歷史記錄，非真實憑證；`config.yaml` 已不追蹤；公開流程已改用 `config.example.yaml`

    **需修正：無**

    **Phase 6 結論：passed。No sensitive secrets requiring remediation.**

### Phase 7：驗證與交付確認

20. 執行以下驗證命令，逐項確認通過：

    **a. Working tree 與 branch 確認**
    ```
    git status --short          # 應無輸出（working tree 乾淨）
    git branch --show-current   # 應為 chore/task-open-source-readiness
    ```

    **b. 追蹤檔案清單確認**
    ```
    git ls-files config.yaml config.example.yaml .gitignore LICENSE README.md \
      CONTRIBUTING.md SECURITY.md .github/workflows/ci.yml \
      app/static/img/library-procurement-bg.webp
    ```
    - `config.yaml` → 無輸出（不追蹤）
    - `config.example.yaml`、`.gitignore`、`LICENSE`、`README.md`、`CONTRIBUTING.md`、`SECURITY.md`、`.github/workflows/ci.yml`、`app/static/img/library-procurement-bg.webp` → 全部有輸出（已追蹤）

    **c. 不追蹤目錄確認**
    ```
    git ls-files data/ exports/ 00_source/ tmp/ config.yaml
    ```
    應無輸出。

    **d. 敏感資料最終掃描**
    ```
    git grep -n -I -E "password|secret|token|api[_-]?key|changeme|please-change|C:\\|Users\\" -- .
    ```
    確認無新增的非預期命中（對照 Phase 6 已確認清單）。

    **e. 測試**
    ```
    .venv\Scripts\python.exe -m pytest -q
    ```
    應全部通過（63 passed 或以上）。

    **f. 文件內容確認（人工）**
    - `README.md` 包含：MIT License 聲明、`config.example.yaml` → `config.yaml` 步驟、安全提醒、`.gitignore` 排除說明
    - `.github/workflows/ci.yml` matrix 使用 Python `"3.11"` 與 `"3.12"`，steps 含 `cp config.example.yaml config.yaml` 與 `pytest -q`

    **g. 手動確認（可選）**
    - Windows `start.bat` 雙擊可啟動，瀏覽器開啟 `http://127.0.0.1:8765`

21. 確認所有變更已 commit，working tree 乾淨
22. 向使用者回報完成情況，等待確認後進入 task-close 流程

## 風險與注意事項

1. **`git rm --cached config.yaml` 風險**：執行後本機 `config.yaml` 不受影響，但若執行 `git checkout` 或 `git restore` 等操作可能意外刪除本機未追蹤的 `config.yaml`。執行前提醒使用者備份或確認本機有效 config。

2. **git history 殘留**：`config.yaml` 被從追蹤移除後，舊版 commit 仍含此檔案。本次任務不重寫 history（不執行 `git filter-repo`）。若 history 中有真實密碼，需另行評估，本次範圍不含此項。

3. **靜態資產（已解除）**：`library-procurement-bg.webp` 為 AI 生成素材，已確認可追蹤並以 MIT License 發布，Phase 5 步驟 16 直接執行 `git add`，不需額外確認。

4. **敏感掃描命中 docs/tasks/ 或 docs/logs/**：若掃描結果顯示 AI 工作流程文件含真實憑證，先停止並回報使用者，不自行大量刪改歷史記錄或重寫 git history。

5. **MIT License 已確認**：授權類型已由使用者確認為 MIT，Phase 3 步驟 8 直接建立 `LICENSE`，不需再詢問。

6. **回滾策略**：
   - Phase 1 若出現問題：`git restore --staged config.yaml` 可恢復索引追蹤狀態（不影響本機檔案）
   - Phase 4 CI 若語法錯誤：直接編輯修正，無需特殊回滾
   - 任何 commit 若需撤銷：在 task branch 上執行 `git revert` 而非 `git reset --hard`

## 預計影響範圍

新增檔案：
- `config.example.yaml`
- `LICENSE`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `.github/workflows/ci.yml`

修改檔案：
- `.gitignore`（新增 `config.yaml`、`tmp/`、`*.log`）
- `README.md`（補充安裝、設定、測試、Python 版本、開發文件說明段落）
- `docs/user-guide/install-windows.md`（補充設定檔初始化步驟）

從 git 索引移除（本機保留）：
- `config.yaml`

新增追蹤（已確認）：
- `app/static/img/library-procurement-bg.webp`（AI 生成素材，MIT License，Phase 5 加入 git 追蹤）

明確不修改：
- 所有 `app/` 下的應用程式原始碼
- `AGENTS.md`、`CLAUDE.md`、`.claude/`、`.gemini/`、`docs/tasks/`、`docs/logs/`（只做內容掃描，不修改、不刪除、不排除）
- `requirements.txt`（保留現有格式）
- `start.bat`（不修改）
- 任何既有 task 的 spec、plan、log 文件

## 驗證指令

- test: `.venv\Scripts\python.exe -m pytest -q`
- lint: 無（本專案未設定 lint 工具）
- format: 無（本專案未設定 format 工具）
- typecheck: 無（本專案未設定 typecheck 工具）
- build: 不適用（無需 build 步驟）
- git 狀態驗證：`git status --short`
- 追蹤清單驗證：`git ls-files`（確認無 `config.yaml`、`data/`、`exports/`、`00_source/`、`tmp/`）
- 敏感掃描：`rg -n "password|secret|token|api[_-]?key|changeme|please-change|C:\\\\|Users\\\\" -S --glob "!.venv" .`
- CI 語法確認：檢視 `.github/workflows/ci.yml` 縮排與 key 名稱
- 手動確認：Windows `start.bat` 雙擊可啟動，瀏覽器開啟 `http://127.0.0.1:8765`

## 成果報告

- result_report_mode: none
- 適用情境：本次為設定、文件、CI 的準備性工作，無需額外成果報告
