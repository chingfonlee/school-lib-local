# Spec: task-export-policy-topic-delimiter

## 目標

匯出一般圖書採購 Excel 時，`policy_topic`（議題）欄位若有多個值，將分隔符由半形分號 `;` 或全形分號 `；` 正規化為頓號 `、`，讓匯出結果符合中文閱讀習慣。

## 問題描述與範例

DB 或匯入資料中，`policy_topic` 多值以分號分隔儲存，例如：

| DB 原始值 | 目前匯出 | 修正後匯出 |
|---|---|---|
| `SDGs;SEL` | `SDGs;SEL` | `SDGs、SEL` |
| `SDGs；SEL` | `SDGs；SEL` | `SDGs、SEL` |
| `SDGs; SEL` | `SDGs; SEL` | `SDGs、SEL` |
| `SDGs;SEL;品德` | `SDGs;SEL;品德` | `SDGs、SEL、品德` |
| `A;;B` | `A;;B` | `A、B`（空片段跳過，不產生 `A、、B`） |
| `SDGs` | `SDGs` | `SDGs`（單一值不變） |
| `""` / `None` | `""` / `None` | `""` / `None`（空值不變） |

## 技術判斷

- 只在匯出層格式化：在 `export_service.py` 的 `export_general_books()` 寫入 `policy_topic` 欄位前，以 helper 轉換字串。
- DB 原始資料不變：不執行 migration，不修改已儲存資料。
- 匯入流程不變：`policy_topic` 匯入時仍按原有邏輯處理（不在此 task 範圍內）。

## 適用範圍

- `export_general_books()`：同時用於國小一般圖書（`general_books`）與國中一般圖書（`general_books_jh`）匯出，修正一次即同時生效。
- `_format_policy_topic_for_export(value: str | None) -> str | None`：新增於 `export_service.py`，僅在 `export_general_books()` 的 `policy_topic` 欄位寫入時呼叫。

## 不做的事

- 不修改 DB 既有資料或 migration。
- 不修改匯入流程（`import_service.py`）。
- 不修改選書頁 UI 顯示。
- 不修改本土文化匯出（`export_local_culture()`，目前無 `policy_topic` 欄位）。
- 不更改其他欄位的分隔符（`recommendation_source`、`award_notes`、`notes` 等）。
- 不修改 Excel 範本檔。
- 不建立新版 release（由後續 task close 後使用者決定）。

## 驗收條件

1. 匯出 Excel 的 `policy_topic` 欄位：
   - 半形分號 `;` → 頓號 `、`
   - 全形分號 `；` → 頓號 `、`
   - 分隔符前後空白去除（`SDGs; SEL` → `SDGs、SEL`）
   - 連續或重複分號（`A;;B`）→ 空片段跳過（`A、B`）
   - 單一值不受影響
   - 空值（`None`、空字串）仍輸出 `None`
2. 國小與國中一般圖書匯出均通過驗收（共用 `export_general_books()`）。
3. 本土文化匯出不受影響（無 `policy_topic` 欄位，不呼叫 helper）。
4. `pytest tests/test_export_service.py -q`：所有測試 pass。
5. `pytest tests/ -q`：全部測試 pass，無 regression。
