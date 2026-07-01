# Plan: task-export-policy-topic-delimiter

## 實作步驟

### 步驟 1：確認 `policy_topic` 寫入位置

- 確認 `app/services/export_service.py` 第 431–432 行：
  ```python
  if "policy_topic" in col_map:
      ws.cell(row=row, column=col("policy_topic")).value = _resolve_field(book, "policy_topic") or None
  ```
- 確認此為唯一寫入點（`export_general_books()` 內）。

### 步驟 2：新增 helper `_format_policy_topic_for_export`

在 `app/services/export_service.py` 適當位置（private helper 區段）新增：

```python
def _format_policy_topic_for_export(value: str | None) -> str | None:
    if not value:
        return None
    parts = [p.strip() for p in re.split(r"[;；]", value)]
    parts = [p for p in parts if p]
    return "、".join(parts) if parts else None
```

邊界規則：
- `None` 或空字串 → `None`
- 以 `re.split(r"[;；]", value)` 同時分割半形與全形分號
- 各片段 `strip()` 去除前後空白
- 過濾空片段（處理連續分號如 `A;;B`、全為空白如 `" ; ；"`）
- 以 `、` 重新 join；若所有片段 strip 後均為空（如 `" ; ；"` → 全片段為 `""`），回傳 `None`
- 回傳型別明確為 `str | None`，與 Excel 空白欄位行為一致

`re` 模組已在 Python 標準函式庫，不引入新 dependency。

### 步驟 3：套用 helper 至 `policy_topic` 欄位寫入

將原本：

```python
if "policy_topic" in col_map:
    ws.cell(row=row, column=col("policy_topic")).value = _resolve_field(book, "policy_topic") or None
```

改為：

```python
if "policy_topic" in col_map:
    ws.cell(row=row, column=col("policy_topic")).value = _format_policy_topic_for_export(
        _resolve_field(book, "policy_topic")
    )
```

注意：`_format_policy_topic_for_export` 已在空值時回傳 `None`，因此不需外層再加 `or None`。

### 步驟 4：確認 `re` 已 import

檢查 `export_service.py` 最上方 import 區。若已有 `import re` 則略過；若無，在標準函式庫 import 區段加入。

### 步驟 5：補充測試

在 `tests/test_export_service.py` 新增針對 `_format_policy_topic_for_export` 的單元測試（或新建 `tests/test_export_policy_topic.py`，依現有測試結構決定）：

| 測試情境 | 輸入 | 預期輸出 |
|---|---|---|
| 半形分號 | `"SDGs;SEL"` | `"SDGs、SEL"` |
| 全形分號 | `"SDGs；SEL"` | `"SDGs、SEL"` |
| 分號前後空白 | `"SDGs; SEL"` | `"SDGs、SEL"` |
| 連續分號 / 空片段 | `"A;;B"` | `"A、B"` |
| 三個值 | `"SDGs;SEL;品德"` | `"SDGs、SEL、品德"` |
| 單一值（不含分號） | `"SDGs"` | `"SDGs"` |
| 空字串 | `""` | `None` |
| None | `None` | `None` |
| 全空白片段 | `" ; ；"` | `None`（所有片段 strip 後均為空） |

若現有 `test_export_service.py` 已有 `export_general_books()` integration 測試且結構允許低成本加入，可直接在該檔補測；否則建 `tests/test_export_policy_topic.py`。

### 步驟 6：執行驗證指令

1. `pytest tests/test_export_service.py -q`
2. `pytest tests/ -q`（確認無 regression）

## 風險與注意事項

- `re` 標準函式庫，無 dependency 風險。
- helper 只在 `policy_topic` 欄位被呼叫，不影響其他欄位。
- 若 `_resolve_field(book, "policy_topic")` 已回傳 `None`，`_format_policy_topic_for_export(None)` 直接回傳 `None`，與原有 `or None` 行為一致。
- 連續分號（如 `A;;B`）的空片段過濾行為在 spec 已明確定義，測試必須涵蓋。

## 預計影響範圍

- `app/services/export_service.py`：新增 1 個 private helper，修改 1 行（`policy_topic` 欄位寫入）；可能加入 `import re`。
- `tests/test_export_service.py`（或新建 `tests/test_export_policy_topic.py`）：新增 8 個測試 case。
- 不影響其他 service、route、model、template 或 migration。

## 驗證指令

- lint: 無（專案現無 lint 設定）
- format: 無（專案現無 formatter 設定）
- typecheck: 無（專案現無 typecheck 設定）
- test: `pytest tests/test_export_service.py -q` 再跑 `pytest tests/ -q`
- build: 無

## 成果報告

- result_report_mode: none
- 適用情境：fix task，無需產生成果報告
