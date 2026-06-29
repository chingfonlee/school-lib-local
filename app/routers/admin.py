import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth import require_auth
from app.database import get_connection
from app.services.template_analyzer import analyze_template, FIELD_LABELS

router = APIRouter(prefix="/api/admin", tags=["admin"])

_TMP_DIR = Path("00_source") / ".tmp"

# 必填欄位：與 export_service.py 的直接 col_map[key] 呼叫保持一致
# optional 欄位（已在 export_service 以 if "x" in col_map 保護）不列入
REQUIRED_FIELDS: dict[str, list[str]] = {
    "local_culture": [
        "sort_order", "title", "author", "publisher", "isbn",
        "quantity", "price", "subtotal", "award_item", "notes",
    ],
    "local_culture_jh": [
        "sort_order", "title", "author", "publisher", "isbn",
        "quantity", "price", "subtotal", "award_item", "notes",
    ],
    "general_books": [
        "eligibility_label", "sort_order", "title", "author",
        "publisher", "isbn", "quantity", "price", "subtotal",
    ],
    "general_books_jh": [
        "eligibility_label", "sort_order", "title", "author",
        "publisher", "isbn", "quantity", "price", "subtotal",
    ],
}


@router.get("/templates")
async def list_templates(user_id: int = Depends(require_auth)):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM export_templates ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/templates/analyze")
async def analyze(
    file: UploadFile = File(...),
    project_type: str = Form(...),
    user_id: int = Depends(require_auth),
):
    if project_type not in REQUIRED_FIELDS:
        raise HTTPException(status_code=400, detail="無效的 project_type")

    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload").name
    tmp_path = _TMP_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    tmp_path.write_bytes(await file.read())

    try:
        result = analyze_template(str(tmp_path), project_type)
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"無法解析範本：{e}")

    result["tmp_path"] = str(tmp_path)
    result["original_filename"] = safe_name
    result["required_fields"] = REQUIRED_FIELDS.get(project_type, [])
    return result


class SaveTemplateRequest(BaseModel):
    project_type: str
    tmp_path: str
    original_filename: str
    sheet_name: str
    header_row: int
    data_start_row: int
    max_rows: int
    school_name_cell: str
    approved_budget_cell: str
    column_mappings: dict[str, str]


@router.post("/templates/save")
async def save_template(body: SaveTemplateRequest, user_id: int = Depends(require_auth)):
    # ── 1. 驗證 project_type ──────────────────────────────────────────────
    if body.project_type not in REQUIRED_FIELDS:
        raise HTTPException(status_code=400, detail="無效的 project_type")

    # ── 2. 清理 original_filename，限制 .xlsx 副檔名 ─────────────────────
    safe_name = Path(body.original_filename).name
    if not safe_name.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="檔案必須為 .xlsx 格式")

    # ── 3. 驗證 tmp_path 必須位於 _TMP_DIR 內 ────────────────────────────
    tmp_path = Path(body.tmp_path)
    allowed_tmp = _TMP_DIR.resolve()
    try:
        tmp_path.resolve().relative_to(allowed_tmp)
    except ValueError:
        raise HTTPException(status_code=400, detail="無效的暫存路徑")
    if not tmp_path.exists():
        raise HTTPException(status_code=400, detail="暫存檔案不存在，請重新上傳")

    # ── 4. 驗證必填欄位 ──────────────────────────────────────────────────
    required = REQUIRED_FIELDS[body.project_type]
    missing = [f for f in required if f not in body.column_mappings]
    if missing:
        missing_labels = [FIELD_LABELS.get(f, f) for f in missing]
        raise HTTPException(
            status_code=400,
            detail=f"以下必填欄位未對應：{', '.join(missing_labels)}",
        )

    # ── 5. 穩定目的路徑（project_type 唯一，不同類型不互相覆蓋）──────────
    dest_dir = Path("00_source") / "templates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{body.project_type}.xlsx"

    shutil.move(str(tmp_path), str(dest))

    # ── 6. 更新 DB ────────────────────────────────────────────────────────
    col_map_json = json.dumps(body.column_mappings, ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()
    dest_str = f"./{dest.as_posix()}"

    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM export_templates WHERE project_type = ?",
        (body.project_type,),
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE export_templates SET "
            "template_file_path=?, sheet_name=?, header_row=?, data_start_row=?, "
            "max_rows=?, school_name_cell=?, approved_budget_cell=?, "
            "column_mappings=?, updated_at=? "
            "WHERE project_type=?",
            (
                dest_str,
                body.sheet_name or None,
                body.header_row,
                body.data_start_row,
                body.max_rows,
                body.school_name_cell,
                body.approved_budget_cell,
                col_map_json,
                now,
                body.project_type,
            ),
        )
    else:
        conn.execute(
            "INSERT INTO export_templates "
            "(name, project_type, template_file_path, sheet_name, header_row, "
            "data_start_row, max_rows, school_name_cell, approved_budget_cell, "
            "column_mappings, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"{body.project_type}_uploaded",
                body.project_type,
                dest_str,
                body.sheet_name or None,
                body.header_row,
                body.data_start_row,
                body.max_rows,
                body.school_name_cell,
                body.approved_budget_cell,
                col_map_json,
                now,
                now,
            ),
        )

    conn.commit()
    conn.close()
    return {"ok": True, "saved_path": str(dest)}
