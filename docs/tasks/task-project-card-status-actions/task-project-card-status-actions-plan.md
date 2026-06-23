# Plan：task-project-card-status-actions

- task-id: task-project-card-status-actions
- base branch: main
- 實作分支: feat/task-project-card-status-actions

---

## 實作步驟

### Step 1：擴充 `GET /api/projects/` 回傳欄位

**檔案**: `app/routers/projects.py`  
**函式**: `list_projects()`（第 40–51 行）

將查詢字串從目前的 2 個 subquery 擴充為 6 個。  
將 `conn.execute(...)` 中的 SQL 字串替換為：

```python
rows = conn.execute(
    "SELECT p.*, "
    "(SELECT COUNT(*) FROM selection_items si WHERE si.project_id = p.id) as selection_count, "
    "(SELECT exported_at FROM export_jobs ej WHERE ej.project_id = p.id "
    " ORDER BY ej.exported_at DESC LIMIT 1) as last_export, "
    "(SELECT imported_at FROM import_batches ib2 "
    " WHERE ib2.project_id = p.id AND ib2.batch_type = 'vendor_books' "
    " ORDER BY ib2.imported_at DESC LIMIT 1) as last_import, "
    "(SELECT COUNT(*) FROM vendor_books vb "
    " JOIN import_batches ib ON ib.id = vb.batch_id "
    " WHERE ib.project_id = p.id) as vendor_book_count, "
    "(SELECT COUNT(*) FROM vendor_books vb2 "
    " JOIN import_batches ib3 ON ib3.id = vb2.batch_id "
    " WHERE ib3.project_id = p.id "
    " AND (SELECT bm.match_status FROM book_matches bm "
    "      WHERE bm.vendor_book_id = vb2.id "
    "        AND bm.match_status != 'same_title_different_isbn' "
    "      ORDER BY bm.id DESC LIMIT 1) = 'already_owned'"
    ") as already_owned_count, "
    "COALESCE("
    "  (SELECT CASE p.subtotal_mode "
    "     WHEN 'quantity_times_list_price' "
    "       THEN SUM(si2.selected_quantity * si2.list_price) "
    "     ELSE SUM(si2.selected_quantity * si2.purchase_price) "
    "   END "
    "   FROM selection_items si2 "
    "   WHERE si2.project_id = p.id AND si2.selected_quantity > 0), "
    "  0"
    ") as selection_amount "
    "FROM procurement_projects p ORDER BY p.created_at DESC"
).fetchall()
```

⚠ alias 衝突注意：原有 subquery 用 `si`（`selection_items`）和 `ej`（`export_jobs`），新增的 subquery 使用 `ib2`、`vb`、`ib`、`vb2`、`ib3`、`bm`、`si2` 以避免 alias 重名。

驗證：`pytest tests/test_project_delete.py` 仍通過（不修改 API 合約，只新增欄位）。

---

### Step 2：更新卡片 HTML 結構

**檔案**: `app/static/projects.html`

讀取 `projects.html` 的 `loadProjects()` 函式，替換 `el.innerHTML = projects.map(...)` 的 template string。

**新 template 結構（JavaScript template literal 形式）：**

```javascript
const cur = getProjectId();
el.innerHTML = projects.map(p => {
  const isCurrent = cur == p.id;
  const escapedName = p.name.replace(/'/g, "\\'");
  // 狀態文字輔助
  const fmtDate = iso => new Date(iso).toLocaleDateString('zh-TW');
  const fmtNum = n => Math.round(n).toLocaleString('zh-TW');

  // 書商書目行
  let importRow;
  if (p.vendor_book_count === 0) {
    importRow = '尚未匯入書商書目';
  } else {
    const ownedStr = p.already_owned_count > 0
      ? ` · 館藏重複 ${p.already_owned_count} 本` : '';
    const importDate = p.last_import ? `（${fmtDate(p.last_import)}）` : '';
    importRow = `書商書目 ${p.vendor_book_count} 本${importDate}${ownedStr}`;
  }

  // 選書行（MVP：selection_amount 使用 selection_items 快照欄位，不套用 user_overrides）
  const selRow = p.selection_count === 0
    ? '尚未選書'
    : `已選 ${p.selection_count} 本 · 小計 NT$ ${fmtNum(p.selection_amount)} 元`;

  // 預算行
  let budgetRow;
  if (p.budget_amount == null) {
    budgetRow = '預算未設定';
  } else if (p.selection_amount === 0) {
    budgetRow = `預算 NT$ ${fmtNum(p.budget_amount)} 元（未使用）`;
  } else {
    const remaining = p.budget_amount - p.selection_amount;
    const pct = Math.round(p.selection_amount / p.budget_amount * 100);
    if (remaining >= 0) {
      budgetRow = `預算剩餘 NT$ ${fmtNum(remaining)} 元（已用 ${pct}%）`;
    } else {
      budgetRow = `預算超支 NT$ ${fmtNum(-remaining)} 元`;
    }
  }

  // 匯出行
  const exportRow = p.last_export
    ? `上次匯出 ${fmtDate(p.last_export)}`
    : '尚未匯出';

  return `
  <div class="project-card${isCurrent ? ' current' : ''}" onclick="selectCard(${p.id},'${escapedName}')">
    <div class="project-card-top">
      <div class="project-info">
        <div class="project-name">${p.name}${isCurrent ? ' <span class="badge badge-available">目前使用</span>' : ''}</div>
        <div class="project-meta">
          ${p.project_type === 'local_culture' ? '本土文化採購' : '一般圖書採購'} ·
          定價欄：${p.price_field === 'purchase_price' ? '採購單價' : '定價'} ·
          小計：${p.subtotal_mode === 'quantity_times_purchase_price' ? '數量×採購單價' : '數量×定價'}
        </div>
      </div>
      <div class="project-actions">
        <button class="btn btn-primary btn-sm" onclick="selectProject(event,${p.id},'${escapedName}')">選擇</button>
        <button class="btn btn-secondary btn-sm" onclick="openEdit(event,${p.id},'${escapedName}',${p.budget_amount},'${p.price_field}','${p.subtotal_mode}')">設定</button>
        <button class="btn btn-danger-outline btn-sm" onclick="confirmDelete(event,${p.id},'${escapedName}')">刪除</button>
      </div>
    </div>
    <div class="project-card-status">
      <div>${importRow}</div>
      <div>${selRow}</div>
      <div>${budgetRow}</div>
      <div>${exportRow}</div>
    </div>
    <div class="project-card-nav">
      <button class="btn btn-secondary btn-sm" onclick="goToStep(event,'/import.html',${p.id},'${escapedName}')">匯入</button>
      <button class="btn btn-secondary btn-sm" onclick="goToStep(event,'/selection.html',${p.id},'${escapedName}')">選書</button>
      <button class="btn btn-secondary btn-sm" onclick="goToStep(event,'/export-check.html',${p.id},'${escapedName}')">匯出前檢查</button>
      <button class="btn btn-secondary btn-sm" onclick="goToStep(event,'/export.html',${p.id},'${escapedName}')">匯出 Excel</button>
    </div>
  </div>
  `;
}).join('');
```

**重點：**
- `const escapedName = p.name.replace(/'/g, "\\'");` 提取至 map body（原本是 inline）。
- `fmtDate` / `fmtNum` 為 map-scope 輔助函式，不需全域宣告。
- 移除舊的第 2、3 條 `.project-meta`（定價欄獨立行 + 預算獨立行），整併至 `project-card-status`。

---

### Step 3：新增 `goToStep` helper

**檔案**: `app/static/projects.html`

在 `enterProject` 函式附近新增：

```javascript
function goToStep(event, url, id, name) {
  event.stopPropagation();
  setProject(id, name);
  window.location.href = url;
}
```

---

### Step 4：更新 CSS

**檔案**: `app/static/css/style.css`

讀取目前 `.project-card` 相關 block，進行以下兩項修改：

**4a. 修改 `.project-card`**

將 `align-items: center` 改為 `flex-direction: column; align-items: stretch`，`gap: 16px` 改為 `gap: 10px`：

```css
.project-card {
  background: #fff; border-radius: 12px; padding: 20px 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.07);
  display: flex; flex-direction: column; align-items: stretch;
  gap: 10px; margin-bottom: 12px;
  cursor: pointer;
  position: relative;
  border: 1px solid rgba(0,0,0,0.04);
  transition: box-shadow 0.15s, transform 0.15s, border-color 0.15s;
}
```

**4b. 在 `.project-card .project-actions` 後新增**

```css
.project-card-top {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}
.project-info { flex: 1; }
.project-card-status {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 12px;
  color: #6e6e73;
  padding-top: 6px;
  border-top: 1px solid rgba(0,0,0,0.05);
}
.project-card-nav {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
```

`::before` 偽元素（`position: absolute; left: 0; top: 16px; bottom: 16px`）保持不變——卡片仍為 `position: relative`，偽元素定位不受 flex 方向影響。

---

### Step 5：新增 API 測試

**檔案**: `tests/test_project_delete.py`（或確認是否有更合適的測試檔，必要時建立 `tests/test_project_list.py`）

確認既有 conftest fixture（`auth_client`、`project_db`）可用，新增以下測試：

```python
def test_list_projects_returns_new_summary_fields(auth_client, project_db):
    """list_projects 包含 last_import, vendor_book_count, already_owned_count, selection_amount"""
    resp = auth_client.get("/api/projects/")
    assert resp.status_code == 200
    projects = resp.json()
    assert len(projects) >= 1
    p = projects[0]
    assert "last_import" in p
    assert "vendor_book_count" in p
    assert "already_owned_count" in p
    assert "selection_amount" in p
    # 無資料時的預設值
    assert p["vendor_book_count"] == 0
    assert p["already_owned_count"] == 0
    assert p["selection_amount"] == 0

def test_list_projects_selection_amount_uses_subtotal_mode(auth_client, project_db):
    """selection_amount 依 subtotal_mode 計算"""
    # 此測試需要建立 import_batch + vendor_book + selection_item fixture
    # 若 conftest 無現成 fixture，可用 project_db 直接 INSERT 測試資料
    # 留在實作時依 conftest 現況決定具體寫法
    pass  # placeholder — 實作時補全
```

若現有 `project_db` fixture 已有選書資料，`test_list_projects_selection_amount_uses_subtotal_mode` 可直接驗證。若無，先完成 Step 1-4，再補全此測試。

---

## 實作順序

1. Step 1（API）→ pytest 確認 58 passed（或更多）
2. Step 2（HTML template）→ 手動確認卡片渲染
3. Step 3（goToStep）→ 點擊按鈕確認導頁不觸發 card onclick
4. Step 4（CSS）→ 視覺確認 column layout 正常
5. Step 5（測試）→ 補全並執行 pytest

---

## 完成條件

- [ ] Step 1：`GET /api/projects/` 回傳 `last_import`、`vendor_book_count`、`already_owned_count`、`selection_amount`
- [ ] Step 2：卡片顯示 4 行狀態摘要（import / selection / budget / export）
- [ ] Step 3：`goToStep` 正確 stopPropagation 並導頁
- [ ] Step 4：卡片 column layout 正常，`::before` guide bar 不受影響
- [ ] Step 5：pytest 全部通過（現有 58 + 新增至少 1）
- [ ] 手動驗收：5 個驗收場景（尚未匯入 / 有館藏重複 / 有預算使用 / 四種按鈕 / card click 仍正常）
