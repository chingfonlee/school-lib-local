# Plan: task-import-award-normalization

## 實作步驟

### 步驟 1：新增 migration `migrations/008_award_normalization_rules.sql`

建立 `award_normalization_rules` 表並 seed 內建規則（依 `docs/reports/award-normalization-import-feature-evaluation.md` 的「A 欄與 R 欄的關聯」與「衝突」章節）：

```sql
CREATE TABLE award_normalization_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_type TEXT NOT NULL DEFAULT 'general_books',
    match_type TEXT NOT NULL CHECK (match_type IN ('exact', 'contains')),
    raw_pattern TEXT NOT NULL,
    normalized_award TEXT NOT NULL,
    eligibility_label TEXT NOT NULL,
    award_notes_mode TEXT NOT NULL DEFAULT 'empty' CHECK (award_notes_mode IN ('empty', 'raw_award')),
    priority INTEGER NOT NULL,
    confidence REAL NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO award_normalization_rules
    (project_type, match_type, raw_pattern, normalized_award, eligibility_label, award_notes_mode, priority, confidence, enabled, created_at, updated_at)
VALUES
    ('general_books', 'exact', '自選', '學校自選(請備註原因)', '自選', 'empty', 10, 0.95, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '金鼎獎', '金鼎獎', '推薦', 'empty', 20, 0.9, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '好書大家讀', '好書大家讀', '推薦', 'empty', 20, 0.9, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '喜閱網', '喜閱網', '推薦', 'empty', 20, 0.9, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '文化部第', '文化部中小學生優良課外讀物選介', '推薦', 'empty', 20, 0.85, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '國教署', '國民中小學新生閱讀推動活動入選書單', '推薦', 'empty', 20, 0.85, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '國民中小學新生', '國民中小學新生閱讀推動活動入選書單', '推薦', 'empty', 20, 0.85, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', '新生閱讀入選', '國民中小學新生閱讀推動活動入選書單', '推薦', 'empty', 20, 0.85, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', 'SEL', '圖書分級推薦書目、臺灣歷史文化分級推薦書目', '推薦', 'raw_award', 30, 0.5, 1, datetime('now'), datetime('now')),
    ('general_books', 'contains', 'SDGS', '圖書分級推薦書目、臺灣歷史文化分級推薦書目', '推薦', 'raw_award', 30, 0.5, 1, datetime('now'), datetime('now'));
```

`priority` 數字越小越優先；同層內以 `raw_pattern` 命中順序為 SQL 回傳順序（`ORDER BY priority ASC, id ASC`）。實際 migration 編號需在實作時執行 `git log --oneline -- migrations/` 確認 007 之後是否已有其他 task 佔用 008，若有衝突則遞補下一個可用編號。

### 步驟 2：新增 `app/services/award_normalization_service.py`

```python
DEFAULT_UNRECOGNIZED_AWARD = "其他國內外具公信力單位辦理之獎項(請備註獎項名稱)"

def _load_rules(conn, project_type: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM award_normalization_rules WHERE project_type = ? AND enabled = 1 "
        "ORDER BY priority ASC, id ASC",
        (project_type,),
    ).fetchall()
    return [dict(r) for r in rows]

def normalize_award(raw_award: str, project_type: str = "general_books", conn=None) -> dict:
    """回傳 recommendation_source / eligibility_label / award_notes / confidence / needs_review / matched_rule"""
    ...

def group_normalize(rows: list[dict], project_type: str = "general_books") -> list[dict]:
    """rows: [{"award_item": str, "title": str}, ...]
    回傳依 award_item（strip 後）分組的建議清單，含 count、sample_titles（最多 3 筆）、status。
    """
    ...
```

規則比對邏輯：

1. `raw_award` 為空/None → 直接回傳 `needs_review=False`, `recommendation_source=None`（不建議，交由老師手動判斷；分組時歸類到獨立的「（無獲獎項目）」組，不強制套用預設值）。
2. 依 `_load_rules()` 取得規則，逐條比對：`exact` 需 strip 後完全相等；`contains` 需 `raw_pattern in raw_award`。
3. 第一條命中的規則決定 `recommendation_source` / `eligibility_label`；`award_notes` 依 `award_notes_mode`（`raw_award` 則帶入原始文字，`empty` 則為 `None`）。
4. `confidence >= 0.8` 且未命中 `SEL` / `SDGS` 等已知衝突規則 → `needs_review = False`（狀態 `auto`）；`confidence < 0.8` → `needs_review = True`（狀態 `needs_review`）。
5. 完全未命中任何規則 → `recommendation_source = DEFAULT_UNRECOGNIZED_AWARD`、`eligibility_label = "推薦"`、`award_notes = raw_award`、`confidence = 0.3`、`needs_review = True`、狀態 `unrecognized`。

`group_normalize()` 對輸入 rows 依 `award_item.strip()` 分組（空字串與 None 視為同一組「未填寫」），每組呼叫一次 `normalize_award()`，附加 `count`、`sample_titles`（依原始列順序取前 3 個非空書名）。

### 步驟 3：`app/services/import_service.py` 新增預覽用讀取函式

新增 `preview_award_groups(file_bytes, filename, sheet_name, header_row, mappings) -> list[dict]`：

- 讀取邏輯比照 `confirm_import()`（第 218–225 行）的 `pd.read_excel(..., dtype=str)`，但只需要 `mappings["award_item"]`、`mappings["title"]` 兩欄，若 `mappings` 未含 `award_item` 直接 raise `ValueError("尚未對應獲獎項目欄位")`（由 router 轉為 400）。
- 逐列取出 `award_item`、`title`（沿用既有 `_is_blank_or_total_row` 略過空白/合計列邏輯，維持與 `confirm_import()` 一致的略過規則，避免分組結果與實際匯入結果筆數對不上）。
- 呼叫 `award_normalization_service.group_normalize(rows, project_type=...)`；`project_type` 由呼叫端（router）查 `procurement_projects` 傳入，若查不到則預設 `general_books`。

### 步驟 4：`app/services/import_service.py` 的 `confirm_import()` 新增 `award_overrides` 參數

- 函式簽名新增 `award_overrides: dict | None = None`（第 195–202 行參數列附近）。
- 在組成 `book` dict 前（第 276–285 行），若 `award_overrides` 非 None 且 `get_field("award_item")`（strip 後）存在於 `award_overrides`：
  ```python
  raw_award = (get_field("award_item") or "").strip()
  override = (award_overrides or {}).get(raw_award)
  recommendation_source = override["recommendation_source"] if override else get_field("recommendation_source")
  eligibility_label = override["eligibility_label"] if override else get_field("eligibility_label")
  award_notes = override["award_notes"] if override else get_field("award_notes")
  ```
  取代原本直接呼叫 `get_field("recommendation_source")` 等三處（第 284、319–322、541–544 行三段重複邏輯只需修改 `confirm_import()` 這一份；`import_vendor_books()`（legacy 單步驟函式，第 433 行起）不在本 task 範圍，不修改）。
- 未帶 `award_overrides` 或該筆 `award_item` 未命中時，行為與現行完全一致（既有測試不受影響）。

### 步驟 5：`app/routers/imports.py` 新增與修改 endpoint

新增：

```python
@router.post("/vendor-books/normalize-awards")
async def normalize_vendor_book_awards(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(None),
    header_row: int = Form(...),
    mappings: str = Form(...),
    project_id: int | None = Form(None),
    user_id: int = Depends(require_auth),
):
    content = await file.read()
    try:
        mappings_dict = json.loads(mappings)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"mappings JSON 格式錯誤：{e}")
    project_type = "general_books"
    if project_id is not None:
        conn = get_connection()
        project_type = _resolve_project_type(conn, project_id)
        conn.close()
    try:
        groups = preview_award_groups(content, file.filename, sheet_name, header_row, mappings_dict, project_type)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"groups": groups}
```

修改 `confirm_vendor_books()`（第 55–115 行）：新增 `award_overrides: str = Form("{}")` 參數，`json.loads` 後傳入 `confirm_import(..., award_overrides=award_overrides_dict)`。

`import_service` import 列（第 8–15 行）加入 `preview_award_groups`。

### 步驟 6：`app/static/import.html` 前端整理步驟

**stepper 導覽**（第 73–77 行）：在 `ws-D` 與 `ws-E` 之間新增：
```html
<div class="wstep" id="ws-award">整&nbsp;整理獲獎</div>
```

**步驟內容**（第 129–139 行 `step-D` 與第 141 行 `step-E` 之間）新增 `step-award` 區塊：分組表格（`<table id="award-groups-table">`）、每組一列，含原始文字、筆數、範例書名、官方名稱下拉（沿用 `H_ALLOWED` 清單，於 import.html 內新增同值常數，與 `selection.html` 第 148–158 行維持一致）、必選/推薦/自選下拉、備註輸入、狀態標籤；上方顯示「整理書單」按鈕與「尚有 N 組需確認」提示。

**JS 邏輯**：
- `order` 陣列（第 305 行）改為 `['A','B','C','D','award','E']`。
- `goToStep()`（第 304–316 行）新增 `if (step === 'award') renderAwardStep();`。
- `step-D` 的「下一步」按鈕（第 137 行）由 `goToStep('E')` 改為 `goToStep('award')`；`step-award` 新增「← 上一步」回 `D`、「下一步 →」到 `E`；`step-E` 的「← 上一步」（第 158 行）改為 `goToStep('award')`。
- 新增全域 `let awardOverrides = {};`（沿用 `wizardFile`/`previewData` 同一區塊，第 200–202 行附近）。
- 新增 `renderAwardStep()`：若 `getMappings().award_item` 為空，顯示提示文字並隱藏表格；否則顯示「整理書單」按鈕。
- 新增 `async function runAwardNormalize()`：組 `FormData`（`file`、`sheet_name`、`header_row`、`mappings`、`project_id`）呼叫 `/api/imports/vendor-books/normalize-awards`，結果存入 `let awardGroups = []`，呼叫 `renderAwardGroupsTable()`。
- 新增 `renderAwardGroupsTable()`：依 `awardGroups` 渲染表格列，下拉/輸入框 `onchange` 呼叫 `updateAwardOverride(rawAward, field, value)`，寫入 `awardOverrides[rawAward]` 並將該列狀態改為「老師已覆寫」。
- `doConfirmImport()`（第 448 行起）在建立 `fd` 時新增 `fd.append('award_overrides', JSON.stringify(awardOverrides));`。

### 步驟 7：新增/擴充測試

- 新增 `tests/test_award_normalization_service.py`：涵蓋 spec「驗證與測試標準」列出的規則情境（自選、金鼎獎/好書大家讀/喜閱網/文化部/新生閱讀關鍵字、`SEL`/`SDGS` 衝突、完全陌生文字、`group_normalize` 分組筆數與範例書名上限）。
- 擴充 `tests/test_confirm_import.py`：新增測試驗證 `award_overrides` 命中/未命中兩種情況下 `vendor_books.recommendation_source`/`eligibility_label`/`award_notes` 的寫入結果；確認未帶 `award_overrides` 時既有測試全數通過（回歸測試）。
- 若 `tests/test_import_service_helpers.py` 有共用 fixture（測試 DB、範例 DataFrame），沿用既有 fixture，不重複建立。

### 步驟 8：手動驗證

1. 以 `00_source/必選推薦-欄位調整-topic-summary-v6-final.xlsx` 建立 `general_books` 測試專案並跑一次完整精靈流程：上傳 → 對應欄位（含 `award_item`）→ 整理書單 → 檢視分組（預期約 386 組）→ 抽查「自選」「金鼎獎」「SEL情緒」三組的建議與狀態 → 確認匯入。
2. 匯入後於資料庫或選書頁確認：`award_item` 保留原始文字；`recommendation_source`/`eligibility_label`/`award_notes` 依整理結果寫入；`SEL情緒`、`SDGS/...` 對應書目的 `recommendation_source` 為老師實際看過的建議值（未被靜默覆蓋）。
3. 於選書頁（`selection.html`）確認單本覆寫功能正常，不受本 task 影響。
4. 匯出一般圖書採購書單，確認官方獲獎欄位只使用 `recommendation_source`。
5. 未對應 `award_item` 欄位的另一次匯入（不同檔案），確認精靈直接略過整理步驟，行為與 task 實作前一致。

### 步驟 9：Commit

依變更性質分次 commit，例如：

```
feat(task-import-award-normalization): add award normalization rules migration
feat(task-import-award-normalization): add award normalization service
feat(task-import-award-normalization): add normalize-awards preview API and award_overrides in confirm
feat(task-import-award-normalization): add award normalization step to import wizard
test(task-import-award-normalization): add award normalization service and confirm_import override tests
```

---

## 風險與注意事項

- **規則覆蓋率有限**：內建規則只涵蓋報告中列出的關鍵字，真實書商資料可能出現報告未涵蓋的新原始文字；此類文字會落入「無法辨識」狀態，交由老師人工判斷，不視為 bug。
- **`confirm_import()` 三處重複的欄位讀取邏輯**：目前 `award_item`/`recommendation_source`/`eligibility_label`/`award_notes` 在 `confirm_import()` 內有兩處（`book` dict 與 SQL 參數列）分別呼叫 `get_field()`，修改時需同步兩處，否則會出現 `book` dict 用於 `compute_completeness()` 的值與實際寫入 DB 的值不一致。
- **`import_vendor_books()`（legacy 單步驟匯入）不支援整理書單**：若之後發現仍有使用者走舊版單步驟上傳（`POST /api/imports/vendor-books`），本 task 不處理，需另開 task 評估是否需要對齊。
- **`award_notes_mode = raw_award` 的規則會覆蓋既有備註對應欄位**：若書商欄位本身有對應 `award_notes`（透過 `mappings.award_notes`），而該筆同時命中整理建議，覆寫邏輯以整理結果為準（見步驟 4），需在 spec 驗收與測試中明確覆蓋此情境，避免行為出乎老師預期。
- **前端分組表格效能**：386 組（非 6,750 筆逐列）應可直接渲染，不需分頁；若未來遇到書商原始文字種類遠高於此量級（例如上千種），需另評估是否加分頁或虛擬捲動，本 task 不預先實作。
- **stepper 新增一格後版面**：需確認 `.wstep` 樣式在 6 個步驟下不跑版（現有 CSS 用 flex，理論上可直接容納，需手動檢查）。

## 預計影響範圍

| 路徑 | 說明 |
|---|---|
| `migrations/008_award_normalization_rules.sql`（新增，實際編號依當時最新序號確認） | 新增規則表與 seed 資料 |
| `app/services/award_normalization_service.py`（新增） | 規則比對與分組邏輯 |
| `app/services/import_service.py` | 新增 `preview_award_groups()`；`confirm_import()` 新增 `award_overrides` 參數與覆寫邏輯 |
| `app/routers/imports.py` | 新增 `POST /api/imports/vendor-books/normalize-awards`；`confirm_vendor_books()` 新增 `award_overrides` 表單欄位 |
| `app/static/import.html` | 新增 `step-award` 精靈步驟、`ws-award` stepper 項目、對應 JS 邏輯 |
| `tests/test_award_normalization_service.py`（新增） | 規則比對與分組單元測試 |
| `tests/test_confirm_import.py` | 新增 `award_overrides` 相關測試案例 |

不影響：`app/static/selection.html`、`app/services/export_service.py`、`app/services/validation_service.py`、`app/services/import_service.py` 中的 `import_vendor_books()` / `import_library_holdings()`。

## 驗證指令

- lint: 待確認（專案未設定獨立 lint 指令，沿用 `python -m compileall app` 作為語法檢查）
- format: 無法執行（專案未設定 formatter，不在本 task 引入）
- typecheck: 無法執行（專案未使用型別檢查工具，不在本 task 引入）
- test: `python -m pytest -q`（與 `.github/workflows/ci.yml` 一致）
- build: 無適用（本專案無獨立 build 步驟；`build-portable.yml` 屬於發版流程，不在本 task 驗證範圍）

## 成果報告

- result_report_mode: none
- 適用情境：無（沿用專案內其他 task 慣例，不產生成果報告；以 spec 驗收條件與測試結果作為完成依據）
- 報告路徑（若 mode 非 none）：`docs/reports/task-import-award-normalization/`
