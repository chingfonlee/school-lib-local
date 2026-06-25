# 貢獻指南

感謝您對本專案的興趣。

## 開發環境建立

```bash
git clone <repo-url>
cd school-lib-local

# 建立虛擬環境（建議 Python 3.11 或 3.12）
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt

# 建立本機設定檔
copy config.example.yaml config.yaml   # Windows
# cp config.example.yaml config.yaml   # macOS / Linux
# 編輯 config.yaml，設定 default_admin_password 與 session_secret_key
```

## 執行測試

```bash
.venv\Scripts\python.exe -m pytest -q   # Windows
# python -m pytest -q                   # macOS / Linux
```

PR 提交前須確認測試全部通過。

## Branch 與 Commit 命名

**Branch 格式：**

```
feat/{task-id}   — 新功能
fix/{task-id}    — 錯誤修正
chore/{task-id}  — 設定、文件、流程調整
```

**Commit 格式：**

```
{type}({task-id}): {短描述}
```

範例：`feat(task-web-auth): add login page`

## 不要提交的內容

以下項目已列入 `.gitignore`，請勿強制提交：

| 項目 | 說明 |
|------|------|
| `config.yaml` | 含密碼的本機設定 |
| `data/` | 資料庫與館藏記錄 |
| `exports/` | 匯出的採購書單 |
| `00_source/` | 書商 Excel 原始書單 |
| `tmp/` | 暫存檔案 |
| `*.db`、`*.log` | 執行期資料 |

## PR 前檢查清單

- [ ] `pytest` 全部通過
- [ ] 未包含 `config.yaml`、`data/`、`exports/`、`00_source/`、`tmp/`
- [ ] 未包含真實學校資料或個人資料
- [ ] commit message 格式符合規範
