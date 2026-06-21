# Plan: task-selection-category-filter-dropdown

## 實作步驟

### Step 1：修改 HTML — filter-bar 控制項

檔案：`app/static/selection.html`

移除（第 69 行附近）：
```html
<input type="text" id="filter-category" placeholder="分類/議題..." oninput="applyFilter()" style="width:120px">
```

替換為：
```html
<label id="label-category" style="display:none">分類：</label>
<select id="filter-category" onchange="applyFilter()" style="display:none"><option value="">全部</option></select>
<label id="label-policy-topic" style="display:none">議題：</label>
<select id="filter-policy-topic" onchange="applyFilter()" style="display:none"><option value="">全部</option></select>
```

位置：維持在 `filter-age` 之後、`filter-min-price` 之前，與現有排列一致。

### Step 2：修改 `populateDynamicSelects()`

現況（第 135–155 行附近）：

```js
populate('filter-book-type', allBooks.map(b => b.book_type));
populate('filter-age', allBooks.map(b => b.age_range));

const hasBookType = ...
// show/hide label-book-type + filter-book-type

const hasCategoryData = allBooks.some(...);
document.getElementById('filter-category').style.display = hasCategoryData ? '' : 'none';
```

修改後：

```js
populate('filter-book-type', allBooks.map(b => b.book_type));
populate('filter-age', allBooks.map(b => b.age_range));
populate('filter-category', allBooks.map(b => b.category));
populate('filter-policy-topic', allBooks.map(b => b.policy_topic));

const hasBookType = document.getElementById('filter-book-type').options.length > 1;
document.getElementById('label-book-type').style.display = hasBookType ? '' : 'none';
document.getElementById('filter-book-type').style.display = hasBookType ? '' : 'none';

const hasCategory = document.getElementById('filter-category').options.length > 1;
document.getElementById('label-category').style.display = hasCategory ? '' : 'none';
document.getElementById('filter-category').style.display = hasCategory ? '' : 'none';

const hasTopic = document.getElementById('filter-policy-topic').options.length > 1;
document.getElementById('label-policy-topic').style.display = hasTopic ? '' : 'none';
document.getElementById('filter-policy-topic').style.display = hasTopic ? '' : 'none';
```

移除舊的 `hasCategoryData` 區塊。

### Step 3：修改 `applyFilter()` — category / policy_topic 篩選邏輯

現況（第 220、231–235 行附近）：

```js
const category = document.getElementById('filter-category').value.trim();
...
if (category) {
  const kc = normalizeText(category);
  filtered = filtered.filter(b =>
    normalizeText(b.category).includes(kc) || normalizeText(b.policy_topic).includes(kc)
  );
}
```

修改後：

```js
const category = document.getElementById('filter-category').value;
const policyTopic = document.getElementById('filter-policy-topic').value;
...
if (category) filtered = filtered.filter(b => (b.category || '') === category);
if (policyTopic) filtered = filtered.filter(b => (b.policy_topic || '') === policyTopic);
```

**注意事項：**
- 舊的 `.trim()` 可移除（select.value 無前後空白）
- 改為 exact match，與 `filter-book-type` / `filter-age` 一致
- `includesKeyword()` 不動，關鍵字搜尋仍可搜尋 `category` + `policy_topic`

### Step 4：修改 `resetFilters()`

現況（第 252–258 行附近）：

```js
['filter-match', 'filter-comp', 'filter-book-type', 'filter-age', 'filter-sort']
  .forEach(id => { const s = document.getElementById(id); s.value = s.options[0].value; });
['filter-category', 'filter-min-price', 'filter-max-price', 'filter-text']
  .forEach(id => { document.getElementById(id).value = ''; });
```

修改後：

```js
['filter-match', 'filter-comp', 'filter-book-type', 'filter-age', 'filter-category', 'filter-policy-topic', 'filter-sort']
  .forEach(id => { const s = document.getElementById(id); s.value = s.options[0].value; });
['filter-min-price', 'filter-max-price', 'filter-text']
  .forEach(id => { document.getElementById(id).value = ''; });
```

`filter-category` 從文字輸入群組移到 select 群組，新增 `filter-policy-topic`。

---

## 風險與注意事項

1. **`oninput` → `onchange`**：`<input>` 用 `oninput` 即時觸發，`<select>` 用 `onchange`。HTML 修改時已替換，applyFilter() 無需額外改動。

2. **`resetFilters()` 群組轉移**：`filter-category` 從 `.value = ''` 移到 `.options[0].value` 群組。`select.value = ''` 雖也能運作（選到空值的第一個 option），但移到 select 群組更一致，避免日後混淆。

3. **category 值含空白**：`populate()` 內已有 `trim()` 與 `filter(Boolean)` 處理，去重排序無問題。applyFilter() 的 exact match 對比的是已 trim 後的 option value，不需額外處理。

4. **policy_topic 目前 0 筆**：`populate()` 呼叫後 `filter-policy-topic` 只有「全部」一個 option，`options.length > 1` 為 false，`label-policy-topic` 與 `filter-policy-topic` 保持隱藏，不會產生空下拉。

5. **applyFilter() 讀取順序**：新增 `policyTopic` 讀取必須在 `filterred = allBooks` 之後、sort 之前，與其他篩選條件同層。確認插入位置正確。

---

## 預計影響範圍

| 檔案 | 變動類型 |
|------|---------|
| `app/static/selection.html` | 修改（HTML + JS，約 4 處） |

無後端修改、無 migration、無其他檔案。

---

## 驗證指令

### lint / format
- lint: `python -m compileall app`（HTML/JS 無法直接 compile，此步驟確認無 Python 誤改）
- format: 無既有設定

### typecheck / test
- 無既有自動化測試

### build
- 不適用

### 手動驗證步驟（依序）

**A. compileall：**
```
python -m compileall app
```

**B. 啟動伺服器，開啟 selection.html：**
- 確認「分類」下拉顯示（category 670 筆有值）
- 確認「議題」下拉不顯示（policy_topic 0 筆）
- 確認「類型」、「年齡」下拉仍正常

**C. 分類篩選測試：**
- 選擇任一分類（例如「語言類」）
- 確認書卡數量縮減為僅該分類書目
- 確認選到不同分類，結果不同

**D. 重設篩選：**
- 選擇分類後，點「重設篩選」
- 確認分類下拉回到「全部」，書卡恢復全部筆數

**E. 關鍵字搜尋仍可找到分類文字：**
- 在關鍵字欄輸入分類名稱，確認可搜尋到

**F. 既有篩選不受影響：**
- 測試比對狀態、完整度、類型、年齡、價格篩選仍正常

---

## 成果報告

- result_report_mode: none
- 適用情境：純 UI 修改，以手動目視確認為主
