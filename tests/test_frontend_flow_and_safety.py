"""Frontend syntax, escaping, and flow regression tests for app/static."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"
COMMON_JS = STATIC_DIR / "js" / "common.js"

INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)


def _read(rel_path: str) -> str:
    return (STATIC_DIR / rel_path).read_text(encoding="utf-8")


def _require_node() -> str:
    node = shutil.which("node")
    assert node is not None, "node is required to run frontend JavaScript syntax and behavior checks"
    return node


def _check_js_syntax(node: str, code: str, label: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tmp:
        tmp.write(code)
        tmp_path = Path(tmp.name)
    try:
        proc = subprocess.run(
            [node, "--check", str(tmp_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert proc.returncode == 0, f"JS syntax error in {label}:\n{proc.stderr}"
    finally:
        tmp_path.unlink(missing_ok=True)


def test_all_static_js_and_inline_scripts_pass_node_check() -> None:
    node = _require_node()
    for js_file in sorted((STATIC_DIR / "js").glob("*.js")):
        _check_js_syntax(node, js_file.read_text(encoding="utf-8"), js_file.name)

    html_files = sorted(STATIC_DIR.glob("*.html"))
    assert html_files, "Expected static HTML files under app/static"
    for html_file in html_files:
        text = html_file.read_text(encoding="utf-8")
        scripts = INLINE_SCRIPT_RE.findall(text)
        for idx, script in enumerate(scripts, start=1):
            if script.strip():
                _check_js_syntax(node, script, f"{html_file.name}#script-{idx}")


def test_common_js_helpers_runtime_behavior() -> None:
    node = _require_node()
    common_src = COMMON_JS.read_text(encoding="utf-8")
    harness = f"""
global.document = {{ addEventListener() {{}} }};
global.window = {{ location: {{ pathname: '/projects.html', href: '' }} }};
{common_src}
const out = {{
  esc_html: esc('<script>"\\'&</script>'),
  esc_null: esc(null),
  parse_ok: safeParseJson('{{"a":1}}', {{}}),
  parse_bad: safeParseJson('not-json', {{ fallback: true }}),
  err_422: formatApiError([{{ loc: ['body', 'name'], msg: 'Field required' }}], 422),
  err_str: formatApiError('權限不足', 403),
  h_count: H_ALLOWED.length,
}};
console.log(JSON.stringify(out));
"""
    proc = subprocess.run(
        [node, "-e", harness],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    result = json.loads(proc.stdout.strip())
    assert result["esc_html"] == "&lt;script&gt;&quot;&#39;&amp;&lt;/script&gt;"
    assert result["esc_null"] == ""
    assert result["parse_ok"] == {"a": 1}
    assert result["parse_bad"] == {"fallback": True}
    assert "[object Object]" not in result["err_422"]
    assert "name" in result["err_422"]
    assert result["err_str"] == "權限不足"
    assert result["h_count"] == 9


def test_common_js_and_login_auth_and_toast_hardening() -> None:
    common = _read("js/common.js")
    login = _read("login.html")

    assert "/login.html?expired=1" in common
    assert "clearTimeout(_toastTimer)" in common
    assert "function requireProject(" in common
    assert "網路連線失敗" in common

    assert "expired" in login
    assert "登入已逾時，請重新登入" in login


def test_projects_and_admin_templates_safety_and_flow() -> None:
    projects = _read("projects.html")
    admin = _read("admin-templates.html")

    # No duplicate display:flex on edit-modal
    edit_modal_line = next(line for line in projects.splitlines() if 'id="edit-modal"' in line)
    assert edit_modal_line.count("display:") == 1
    assert "display:none" in edit_modal_line

    # Project cards pass numeric id rather than string-interpolated project name
    assert "escapedName" not in projects
    assert "esc(p.name)" in projects
    assert "/import.html?tab=vendor" in projects
    assert "api('/api/backup/restore'" in projects
    assert "if (getProjectId() == id) setProject(id, name);" in projects

    # admin-templates fixes
    assert "document.getElementById('save-btn').disabled = false;" in admin
    assert "api('/api/admin/templates/analyze'" in admin
    assert "projectTypeLabel(" in admin
    assert "esc(" in admin


def test_import_and_match_flow_and_safety() -> None:
    imp = _read("import.html")
    match = _read("match.html")

    assert "URLSearchParams(window.location.search).get('tab')" in imp
    assert "this.value='';" in imp
    assert "savedMappings" in imp
    assert "savedExtraFields" in imp
    assert "resetVendorWizard()" in imp
    assert "hasExistingHoldings" in imp
    assert "esc(" in imp

    assert 'href="/selection.html"' in match
    assert "requireProject()" in match
    assert "runMatch(this)" in match
    assert "event.target" not in match
    assert "safeParseJson(" in match
    assert "esc(" in match


def test_selection_flow_sync_and_ux() -> None:
    sel = _read("selection.html")

    # H_ALLOWED centralized in common.js
    assert "const H_ALLOWED" not in sel
    assert "requireProject()" in sel
    assert "safeParseJson(" in sel
    assert "esc(" in sel

    # Sync selIdMap dynamically on refreshBudget and read in saveOverrides
    assert "selIdMap[s.id] = s.sel_id;" in sel
    assert "const selId = selIdMap[bookId] || null;" in sel

    # Selection lock rule, sticky budget bar, filter persistence, debounce + IME, preserve page
    assert "function removeBook(" not in sel
    assert "LOCKED_CTA_TITLE" in sel
    assert "position: sticky" in sel
    assert "budget-remaining" in sel
    assert "compositionstart" in sel
    assert "compositionend" in sel
    assert "sessionStorage.setItem(filterStorageKey()" in sel
    assert "preservePage" in sel


@pytest.mark.parametrize("rel_path", ["export-check.html", "export.html"])
def test_export_pages_common_safety(rel_path: str) -> None:
    content = _read(rel_path)
    assert "const H_ALLOWED" not in content
    assert "requireProject()" in content
    assert "safeParseJson(" in content
    assert "esc(" in content


def test_export_check_and_export_pricing_and_snapshot_fixes() -> None:
    check = _read("export-check.html")
    exp = _read("export.html")

    # export-check: owned rows can still be removed, query params forwarded, quantity locked, detached snapshot handled
    assert "const actionCell = isOwned" in check
    assert 'onclick="removeBook(${d.sel_id})"' in check
    assert "/export.html?price_field=${pf}&subtotal_mode=${sm}" in check
    assert "input.disabled = true;" in check
    assert "btn.disabled = !d.total_selected;" in check
    assert "if (sourceExists)" in check

    # export: query params synced, onchange bound, overrides applied to prices, budget & school remembered
    assert 'id="price-field" onchange="loadPreview()"' in exp
    assert 'id="subtotal-mode" onchange="loadPreview()"' in exp
    assert "params.get('price_field')" in exp
    assert "params.get('subtotal_mode')" in exp
    assert "ov.list_price || b.list_price" in exp
    assert "ov.purchase_price || b.purchase_price" in exp
    assert "proj.budget_amount" in exp
    assert "LAST_SCHOOL_NAME_KEY" in exp
    assert "exportBtn.disabled = items.length === 0;" in exp
