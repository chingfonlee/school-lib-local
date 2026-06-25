# Spec: task-open-source-readiness

## 背景

本專案（國小圖書館圖書採購輔助系統）為本地端 Python/FastAPI 應用，目前在單一學校內部使用。計畫開源供其他國小安裝使用，目前 repo 中存在以下未處理問題：

- `config.yaml` 已被 git 追蹤，內含 `default_admin_password` 與 `session_secret_key` 的預設佔位值，若其他人直接以此檔案部署，存在憑證誤用風險。
- 無 LICENSE 文件，他人無法合法使用或貢獻。
- README 缺乏開發者安裝流程（非 `start.bat` 的手動方式）與 Python 版本要求說明。
- 無 CI（GitHub Actions），無法驗證 PR 的測試是否通過。
- `app/static/img/library-procurement-bg.webp` 為 AI 生成素材，目前未被 git 追蹤，已確認可納入公開 repo 並以 MIT License 發布。
- `tmp/` 目錄目前未追蹤，`.gitignore` 未明確排除。
- `AGENTS.md`、`CLAUDE.md`、`.claude/`、`docs/tasks/`、`docs/logs/` 等 AI 工作流程文件已決定保留在公開 repo，但需確認其中不含真實密碼、token、個資或不可公開的資料路徑。
- `app/static/img/library-procurement-bg.webp` 目前為未追蹤檔案，若要納入公開 repo 需確認授權來源。

## 目標

讓此 repo 能安全、清楚地公開（public），使他人可從 clean clone 完成安裝、執行測試、正常啟動系統，且不會因複製 `config.yaml` 預設值而產生安全疑慮。

## 需求範圍

1. **設定檔開源化**
   - 將 `config.yaml` 從 git 追蹤中移除（`git rm --cached`），本機檔案保留不刪除
   - 建立 `config.example.yaml`：以明顯無法誤用的 placeholder 取代敏感欄位，例如 `default_admin_password: "<change-me>"`、`session_secret_key: "<generate-a-random-secret>"`；加上清楚警告註解
   - 將 `config.yaml` 加入 `.gitignore`
   - `README.md` 與安裝文件說明：首次使用需將 `config.example.yaml` 複製為 `config.yaml`，並修改密碼與 session secret

2. **基本開源文件**
   - `LICENSE`：使用 MIT License（已確認），填入正確年份與著作權人
   - `README.md`：補充開發者安裝指令（venv + pip）、測試指令、Python 版本建議；標示本專案採用 MIT License
   - `CONTRIBUTING.md`：說明貢獻流程、branch 規則、PR 規範
   - `SECURITY.md`：說明如何回報安全問題

3. **.gitignore 補強**
   - 新增 `config.yaml`
   - 新增 `tmp/`
   - 確認 `*.log` 等 log 型態已涵蓋

4. **CI（GitHub Actions）**
   - 新增 `.github/workflows/ci.yml`
   - 安裝 `requirements.txt`
   - 執行 `pytest`
   - 測試 Python 3.11 與 3.12

5. **靜態資產**
   - `app/static/img/library-procurement-bg.webp` 為 AI 生成素材，已確認可納入公開 repo
   - 將此檔案加入 git 追蹤，與專案一併以 MIT License 發布
   - 若 README 或相關文件有資產授權說明，可標註此圖片為「專案自有 / AI 生成素材，MIT License」

6. **AI 工作流程文件公開確認**
   - `AGENTS.md`、`CLAUDE.md`、`.claude/`、`.gemini/`、`docs/tasks/`、`docs/logs/` 保留在公開 repo，不搬移、不刪除、不加入 `.gitignore`
   - 需執行內容掃描，確認上述路徑中不含真實密碼、token、個資、內部 IP 或不可公開的資料路徑
   - `README.md` 簡短說明 `docs/tasks/` 與 `docs/logs/` 為開發流程記錄，非一般使用者必讀文件

## 不做的事

- 不修改應用程式功能邏輯
- 不更改資料庫結構或 API 介面
- 不建立 Docker/容器化部署方案
- 不建立多學校共用的雲端部署方案
- 不翻譯 UI 為英文
- 不引入 pyproject.toml（保留 requirements.txt 即可）
- 不刪除、不搬移、不加入 `.gitignore`：`AGENTS.md`、`CLAUDE.md`、`.claude/`、`.gemini/`、`docs/tasks/`、`docs/logs/`
- 不自動生成 CHANGELOG（可選，不在本次範圍）

## 開源風險與注意事項

1. **憑證風險（高）**：`config.yaml` 目前被追蹤，含 `default_admin_password: "changeme"` 與 `session_secret_key: "please-change-this-to-a-random-string"`。若直接 clone 並用預設值部署，任何人均可用 `admin/changeme` 登入。`git rm --cached` 後仍需確認 git history 中無更嚴重的真實密碼。

2. **學校特定路徑外洩**：`config.yaml` 與 `config.example.yaml` 中的 `source.local_culture_export_template` 路徑含有「高雄市 115 年度○○區○○國小」字樣，屬佔位值，需確認公開後是否可接受。

3. **靜態資產（已解除）**：`app/static/img/library-procurement-bg.webp` 為 AI 生成素材，已確認可納入公開 repo 並以 MIT License 發布，不再有授權疑慮。

4. **AI 工作流程文件內容審查（低）**：`AGENTS.md`、`CLAUDE.md`、`.claude/`、`docs/tasks/`、`docs/logs/` 已決定保留在公開 repo，不預期含有安全敏感資料，但仍需執行一次內容掃描確認。`README.md` 說明這些為開發流程記錄可降低使用者困惑。

5. **git history 掃描**：本次任務限於移除 `config.yaml` 的現有追蹤，不涉及重寫 git history。若 config.yaml 歷史中有真實密碼，需另行評估 `git filter-repo`。

## 驗收條件

- `config.yaml` 不存在於 `git ls-files` 輸出
- `config.example.yaml` 存在，敏感欄位使用明顯 placeholder（`<change-me>`、`<generate-a-random-secret>`），並有清楚的安全提示註解
- `.gitignore` 明確包含 `config.yaml`、`tmp/`
- `LICENSE` 文件存在於 repo 根目錄
- `README.md` 包含：開發者 venv 安裝步驟、測試指令、Python 版本說明
- `CONTRIBUTING.md` 與 `SECURITY.md` 存在
- `.github/workflows/ci.yml` 存在，在 Python 3.11 / 3.12 執行 pytest
- `app/static/img/library-procurement-bg.webp` 已納入 git 追蹤並 commit（AI 生成素材，MIT License）
- `AGENTS.md`、`.claude/`、`docs/tasks/`、`docs/logs/` 內容掃描完成，確認無真實密碼、token、個資
- `rg` 掃描 `password|secret|token` 無異常明文（`config.yaml` 已排除，已追蹤檔案範圍內）
- `git ls-files` 確認 `data/`、`exports/`、`00_source/`、`tmp/`、`config.yaml` 均未追蹤
- `pytest` 全部通過
- Windows `start.bat` 可正常啟動
