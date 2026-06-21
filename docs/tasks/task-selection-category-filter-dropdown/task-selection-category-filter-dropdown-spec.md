# Spec: task-selection-category-filter-dropdown

## 目標

將 selection.html 的「分類/議題」自由文字輸入框，改為動態下拉選單，讓使用者可直接選擇可用分類或議題，不需猜測輸入內容。

## 問題說明

### 現況調查結果

**HTML（filter-bar）：**

| 控制項 | element | 目前行為 |
|--------|---------|---------|
| 比對狀態 | `<select>` | 靜態選項，正常 |
| 完整度 | `<select>` | 靜態選項，正常 |
| 類型 | `<select id="filter-book-type">` | `populateDynamicSelects()` 動態填入，正常 |
| 年齡 | `<select id="filter-age">` | `populateDynamicSelects()` 動態填入，正常 |
| 分類/議題 | `<input type="text" id="filter-category" placeholder="分類/議題...">` | 自由輸入，使用者不知道有哪些選項 |
| 分類/議題 label | 無 id，無獨立 label 元素 | 顯示控制只能靠 input 本身的 display |

**`populateDynamicSelects()` 現況：**

```js
populate('filter-book-type', allBooks.map(b => b.book_type));
populate('filter-age', allBooks.map(b => b.age_range));

const hasBookType = document.getElementById('filter-book-type').options.length > 1;
// 顯示/隱藏 label-book-type + filter-book-type

const hasCategoryData = allBooks.some(b => (b.category || '').trim() || (b.policy_topic || '').trim());
document.getElementById('filter-category').style.display = hasCategoryData ? '' : 'none';
// ↑ category 與 policy_topic 合用一個 input，動態選項未填入
```

問題：`category` 與 `policy_topic` 共用同一個 `<input>`，且未呼叫 `populate()`，使用者看到的只有輸入框而無選項清單。

**`applyFilter()` 現況（category 部分）：**

```js
const category = document.getElementById('filter-category').value.trim();
if (category) {
  const kc = normalizeText(category);
  filtered = filtered.filter(b =>
    normalizeText(b.category).includes(kc) || normalizeText(b.policy_topic).includes(kc)
  );
}
```

問題：
- `includes()` 子字串比對，適合 text input，但改成下拉後應為 exact match
- `category` 與 `policy_topic` 耦合在同一個篩選邏輯，改成獨立下拉後需分開

**`resetFilters()` 現況：**

```js
['filter-match', 'filter-comp', 'filter-book-type', 'filter-age', 'filter-sort']
  .forEach(id => { const s = document.getElementById(id); s.value = s.options[0].value; });
['filter-category', 'filter-min-price', 'filter-max-price', 'filter-text']
  .forEach(id => { document.getElementById(id).value = ''; });
```

`filter-category` 目前在「文字輸入」群組，改為 `<select>` 後需移到「select 群組」。

### 根本問題

`task-vendor-classification-fields` 完成後，`vendor_books.category` 已有正規化資料（670 筆全有值）。但 UI 仍是自由文字輸入框：使用者不知道有哪些分類可選，無法有效利用篩選功能。

## 需求範圍

### 1. HTML 修改（filter-bar）

移除現有的 `<input type="text" id="filter-category">` 及其 placeholder "分類/議題..."。

替換為兩個獨立控制項：

**分類下拉：**
```html
<label id="label-category" style="display:none">分類：</label>
<select id="filter-category" onchange="applyFilter()" style="display:none">
  <option value="">全部</option>
</select>
```

**議題下拉（新增）：**
```html
<label id="label-policy-topic" style="display:none">議題：</label>
<select id="filter-policy-topic" onchange="applyFilter()" style="display:none">
  <option value="">全部</option>
</select>
```

兩者預設隱藏，由 `populateDynamicSelects()` 判斷有無資料後決定是否顯示。

### 2. `populateDynamicSelects()` 修改

- 呼叫 `populate('filter-category', allBooks.map(b => b.category))`
- 呼叫 `populate('filter-policy-topic', allBooks.map(b => b.policy_topic))`
- 依 `filter-category.options.length > 1` 決定是否顯示 `label-category` + `filter-category`
- 依 `filter-policy-topic.options.length > 1` 決定是否顯示 `label-policy-topic` + `filter-policy-topic`
- 移除舊的 `hasCategoryData` + `filter-category` input 顯示/隱藏邏輯

### 3. `applyFilter()` 修改

- `filter-category` 改為 exact match（只比對 `b.category`）：
  ```js
  const category = document.getElementById('filter-category').value;
  if (category) filtered = filtered.filter(b => (b.category || '') === category);
  ```
- 新增 `filter-policy-topic` exact match（只比對 `b.policy_topic`）：
  ```js
  const policyTopic = document.getElementById('filter-policy-topic').value;
  if (policyTopic) filtered = filtered.filter(b => (b.policy_topic || '') === policyTopic);
  ```
- 移除原本 `includes()` + OR 邏輯

關鍵字搜尋（`filter-text` / `includesKeyword()`）仍可搜尋 `category` + `policy_topic`，不改。

### 4. `resetFilters()` 修改

- 將 `filter-category` 從 `.value = ''` 群組移到 `.options[0].value` 群組（與其他 select 一致）
- 新增 `filter-policy-topic` 到 `.options[0].value` 群組

## 不做的事

- 不修改後端 API 或 DB schema
- 不修改匯入流程
- 不處理多選分類
- 不引入第三方 UI 套件或外部依賴
- 不重新設計整個 filter-bar 結構
- 不修改 budget bar、書卡渲染、排序邏輯
- 不修改關鍵字搜尋（`includesKeyword` 不動）
- 不恢復 `extra_fields` 顯示

## 驗收條件

1. `python -m compileall app` pass（純 HTML/JS 修改，確認無誤）
2. 重新匯入有 `category` 的書單後，selection.html 顯示「分類」下拉選單
3. 分類下拉選項包含「全部」與實際分類值（去重、排序）
4. 選擇分類後書卡數量縮小為僅該分類書目
5. 重設篩選後分類回到「全部」，書卡恢復全部
6. `policy_topic` 目前無資料時，議題下拉不顯示
7. 若未來 `policy_topic` 有資料，議題下拉可顯示並做 exact match 篩選
8. `book_type` 與 `age_range` 篩選不受影響，仍正常運作
9. 關鍵字搜尋仍可搜尋 `category` + `policy_topic` 內容
