# Plan: task-import-flow-guidance

## 盤點（已完成）

### import.html 現有成功訊息

**館藏成功（`uploadHoldings()` L266–271）**

```javascript
el.innerHTML = `
  <div class="alert alert-success">
    ✓ ${replaced}共 <strong>${result.record_count}</strong> 筆
    ${result.unmapped_fields && result.unmapped_fields.length ? `<br>未對應欄位：${result.unmapped_fields.join('、')}` : ''}
    ${sheetInfo}${skippedInfo}${matchInfo}
  </div>`;
showToast('館藏匯入完成');
```

缺口：
- `sheetInfo` 只有在 `sheet_summaries.length > 1` 時才顯示（L251）
- 無下一步連結

**書商書單成功（`doConfirmImport()` L456–463）**

```javascript
document.getElementById('step-E-result').innerHTML = `
  <div class="alert alert-success">
    ✓ 匯入完成：共 <strong>${result.record_count}</strong> 筆...
    ${matchSummary}
  </div>
  <p style="margin-top:8px;font-size:14px"><a href="/match.html">前往比對結果 →</a></p>`;
```

缺口：無「前往選書」連結。

### import.html 現有錯誤訊息

| 位置 | 現有訊息 |
|------|---------|
| 館藏匯入失敗（L274） | `匯入失敗：${e.message}` |
| 書商書單步驟 A 讀取失敗（L305） | `讀取失敗：${e.message}` |
| 書商書單步驟 E 匯入失敗（L467） | `匯入失敗：${e.message}` |

`e.message` 來源：`api()` 從 FastAPI 回傳的 `{"detail": str(e)}` 中取出 `detail`。常見情境：
- pandas 格式錯誤：英文技術訊息（如 `No sheet named ...`）
- ValueError（已中文化，如 `館藏檔案未匯入任何有效資料...`）

### 後端 API 回傳欄位（已足夠，不需新增）

| API | 已回傳欄位 |
|-----|---------|
| POST /api/imports/holdings | `record_count`, `sheet_summaries`, `skipped_sheets`, `unmapped_fields`, `affected_projects`, `match_rerun_error` |
| POST /api/imports/vendor-books/confirm | `record_count`, `skipped_count`, `match_stats` (available / already_owned), `match_rerun_error` |

---

## 實作步驟

### 步驟 1：修改 `uploadHoldings()` 成功訊息（館藏）

**位置**：import.html L251–271（`uploadHoldings()` 函式的 try 成功段落）

**修改 sheetInfo 邏輯**

原本：
```javascript
if (result.sheet_summaries && result.sheet_summaries.length > 1) {
  sheetInfo = '<br>各工作表：' + result.sheet_summaries
    .map(s => `${s.sheet_name}（${s.record_count} 筆）`).join('、');
}
```

改為：**移除 `> 1` 限制**，改為 `>= 1`，讓單一工作表也顯示。

**新增下一步連結**

在 `el.innerHTML` 的 `alert-success` div 後，加入：
```html
<p style="margin-top:10px;font-size:14px">
  <a href="/match.html">前往比對結果 →</a>
</p>
```

若已有比對（`result.affected_projects.length > 0`），連結措辭可更積極；若館藏無對應書商書單，保持「前往比對結果」即可。

### 步驟 2：修改 `doConfirmImport()` 成功訊息（書商書單）

**位置**：import.html L456–463（`doConfirmImport()` 函式的 try 成功段落）

**在現有 `<p>` 連結旁加入「前往選書」連結**

原本：
```html
<p style="margin-top:8px;font-size:14px"><a href="/match.html">前往比對結果 →</a></p>
```

改為：
```html
<p style="margin-top:10px;font-size:14px;display:flex;gap:16px;flex-wrap:wrap">
  <a href="/match.html">前往比對結果 →</a>
  <a href="/selection.html">前往選書 →</a>
</p>
```

### 步驟 3：新增 `formatImportError()` helper 並套用

**新增兩個 helper function**（放在 `<script>` 區段靠前位置）：

```javascript
const TECHNICAL_KEYWORDS = [
  'Traceback', 'Exception', 'Error', 'KeyError', 'ValueError',
  'TypeError', 'IndexError', 'No sheet named', 'Worksheet named',
];

function isFriendlyChineseMessage(message) {
  if (!message || message.length > 160) return false;
  if (!/[一-鿿]/.test(message)) return false;
  if (TECHNICAL_KEYWORDS.some(kw => message.includes(kw))) return false;
  return true;
}

function formatImportError(message, context) {
  if (isFriendlyChineseMessage(message)) return message;
  if (context === 'holdings') {
    return '匯入失敗。請確認 Excel 格式正確、欄位含有 ISBN 或書名，再重新上傳。';
  }
  if (context === 'vendor-preview') {
    return '無法讀取檔案，請確認為有效的 .xlsx 格式。';
  }
  return '匯入失敗。請確認欄位對應正確，書名、ISBN 欄位有資料，再重試。';
}
```

**套用位置**（共四處）：

| 位置 | 原本 | 修改後 |
|------|------|-------|
| `uploadHoldings()` catch（L274） | `匯入失敗：${e.message}` | `formatImportError(e.message, 'holdings')` |
| `handleFileUpload()` catch（L305） | `讀取失敗：${e.message}` | `formatImportError(e.message, 'vendor-preview')` |
| `refreshPreview()` catch（L335） | `更新失敗：${e.message}` | `formatImportError(e.message, 'vendor-preview')` |
| `doConfirmImport()` catch（L467） | `匯入失敗：${e.message}` | `formatImportError(e.message, 'vendor-confirm')` |

### 步驟 4：驗證

**自動驗證**
```
python -m compileall app
python -m pytest -v
```

（本 task 僅改 import.html，compileall 與 pytest 主要確認 app 無損）

**手動驗證清單**

| 情境 | 預期 |
|------|------|
| 館藏匯入成功（單一 sheet） | 顯示 sheet 名與筆數、顯示「前往比對結果」連結 |
| 館藏匯入成功（多 sheet） | 顯示各 sheet 筆數、顯示「前往比對結果」連結 |
| 館藏匯入失敗（格式錯誤） | 白話中文錯誤訊息，無英文 exception 文字 |
| 書商書單匯入成功 | 顯示「前往比對結果」與「前往選書」兩個連結 |
| 書商書單步驟 A 讀取失敗 | 白話錯誤訊息 |
| 書商書單步驟 B 更新預覽失敗 | 白話錯誤訊息（vendor-preview 同一提示） |
| 書商書單步驟 E 匯入失敗 | 白話錯誤訊息 |
| local_culture 專案正常匯入 | 功能不受影響 |
| general_books 專案正常匯入 | 功能不受影響 |

### 步驟 5：Commit

```
feat(task-import-flow-guidance): improve import result guidance
```

---

## 風險與注意事項

**`isFriendlyChineseMessage()` 的判斷邏輯**

三個條件同時成立才視為「已友善化」：
1. 含中文字（`/[一-鿿]/`，涵蓋 CJK 統一漢字區）
2. 不含 `TECHNICAL_KEYWORDS` 中的技術關鍵字（含 `No sheet named`、`Worksheet named` 等常見 openpyxl / pandas 錯誤）
3. 長度小於 160 字元

邊界案例：後端若回傳中文但包含「Error」（如訊息中提到「錯誤 Error code」），會被視為技術性訊息套用白話替換。目前後端無此案例，若日後出現可調整 TECHNICAL_KEYWORDS 清單。

**保留原始錯誤訊息供偵錯**

`formatImportError()` 僅影響前端顯示，不影響 console.log 或 network tab 中的原始訊息。若日後需要，可考慮在 `<details>` 展開元素中附上原始訊息，但本 task 不實作。

**手動驗證為主要驗收**

本 task 僅修改靜態 HTML / JavaScript，compileall 與 pytest 均不直接驗證 UI 行為。驗收需要手動操作瀏覽器確認各情境。

---

## 預計影響範圍

| 路徑 | 說明 |
|------|------|
| `app/static/import.html` | 修改 `uploadHoldings()` 成功段落、`doConfirmImport()` 成功段落、三處 catch 錯誤訊息；新增 `formatImportError()` helper |

不影響：`app/` 後端程式碼、`migrations/`、其他靜態頁面、tests/。

---

## 驗證指令

```
python -m compileall app
python -m pytest -v
```

手動瀏覽器驗證（見步驟 4 清單）

## 成果報告

- result_report_mode: none
