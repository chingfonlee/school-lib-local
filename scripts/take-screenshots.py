r"""
scripts/take-screenshots.py
Automated screenshot capture for docs/user-guide/complete-walkthrough.md.
Produces 10 PNG screenshots by driving the app with Playwright.

Usage:
    .venv\Scripts\python.exe scripts\take-screenshots.py

Requirements:
    pip install playwright
    .venv\Scripts\playwright.exe install chromium
    config.yaml must exist with valid credentials (auth.default_admin_password not placeholder)

Strategy:
    - Starts a SEPARATE school-lib server on port 8766 (avoids conflicts with any running server)
    - Uses a SEPARATE screenshot DB: data/school_lib_screenshot.db (never touches production DB)
    - Temporarily patches config.yaml database.path; restores original on exit
    - Deletes the screenshot DB after screenshots are taken

Privacy rules enforced by this script:
    - School name in screenshots: SCHOOL_NAME constant (never a real school name)
    - Passwords are read from config.yaml and never printed
"""
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

import yaml

# ── Constants ────────────────────────────────────────────────────────────────

SCREENSHOT_PORT = 8766
BASE_URL = f"http://127.0.0.1:{SCREENSHOT_PORT}"
CONFIG_PATH = pathlib.Path("config.yaml")
CONFIG_BACKUP = pathlib.Path("config.yaml.screenshot_bak")
SCREENSHOT_DB = pathlib.Path("data/school_lib_screenshot.db")
IMAGES_DIR = pathlib.Path("docs/user-guide/images")
HOLDINGS_FILE = pathlib.Path("sample-data/holdings/sample-holdings.xlsx").resolve()
VENDOR_FILE = pathlib.Path(
    "sample-data/vendor-lists/local-culture-vendor-list-2026.xlsx"
).resolve()

# MUST be a demo/fictional school name — never change to a real school name
SCHOOL_NAME = "示範國小"


# ── Config management ────────────────────────────────────────────────────────

def read_config():
    """Read credentials from config.yaml. Never print password."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    username = cfg["auth"]["default_admin_username"]
    password = cfg["auth"]["default_admin_password"]
    if password in ("<change-me>", "", None):
        print("ERROR: config.yaml default_admin_password is still the placeholder value.")
        print("Set a real password in config.yaml before running this script.")
        sys.exit(1)
    return username, password


def patch_config_for_screenshots():
    """Backup config.yaml and redirect database.path to screenshot DB."""
    shutil.copy2(CONFIG_PATH, CONFIG_BACKUP)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["database"]["path"] = str(SCREENSHOT_DB).replace("\\", "/")
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
    print(f"[Config] Redirected DB → {SCREENSHOT_DB}")


def restore_config():
    """Restore original config.yaml from backup."""
    if CONFIG_BACKUP.exists():
        shutil.copy2(CONFIG_BACKUP, CONFIG_PATH)
        CONFIG_BACKUP.unlink()
        print("[Config] Restored config.yaml")


def cleanup_screenshot_db():
    """Delete the temporary screenshot database."""
    for path in [SCREENSHOT_DB,
                 SCREENSHOT_DB.with_suffix(".db-shm"),
                 SCREENSHOT_DB.with_suffix(".db-wal")]:
        if path.exists():
            path.unlink()
    print("[DB] Screenshot DB deleted")


# ── Server management ────────────────────────────────────────────────────────

def wait_for_server(timeout: int = 40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=2) as r:
                if r.status == 200:
                    print("[Server] Ready")
                    return
        except urllib.error.HTTPError as e:
            if e.code != 404:
                pass  # other HTTP errors still mean server is up; keep going
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Server did not respond at {BASE_URL}/api/health within {timeout}s")


# ── Screenshot flow ───────────────────────────────────────────────────────────

def verify_login_api(username: str, password: str):
    """Verify credentials work against the API before starting Playwright."""
    import json
    body = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[Auth] Pre-flight login: {resp.status} OK")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"Login API returned {e.code}: {detail}")


def take_screenshots(username: str, password: str):
    from playwright.sync_api import sync_playwright

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    def shot(name: str, page):
        path = IMAGES_DIR / name
        page.screenshot(path=str(path), full_page=False)
        print(f"[OK] {name}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            accept_downloads=True,
        )
        page = context.new_page()

        # ── 01-login.png: empty login form ───────────────────────────────
        print("[Step] 01 login page")
        page.goto(f"{BASE_URL}/login.html")
        page.wait_for_selector("#username")
        time.sleep(0.5)
        shot("01-login.png", page)

        # ── Login ─────────────────────────────────────────────────────────
        page.fill("#username", username)
        page.fill("#password", password)
        page.click("button.btn.btn-primary")
        # Wait for URL to include 'projects.html' (avoids glob-matching issues)
        page.wait_for_function(
            "() => window.location.href.includes('projects.html')",
            timeout=20000
        )
        page.wait_for_load_state("networkidle")

        # ── Clear default project to show empty state ─────────────────────
        print("[Step] Clearing default project(s)")
        page.evaluate("""async () => {
            const projects = await (await fetch('/api/projects/')).json();
            for (const p of projects) {
                await fetch('/api/projects/' + p.id, { method: 'DELETE' });
            }
        }""")
        time.sleep(0.5)
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#project-list")
        time.sleep(0.4)

        # ── 02-projects-empty.png: logged in, no projects ─────────────────
        print("[Step] 02 projects empty")
        shot("02-projects-empty.png", page)

        # ── Show new project form, fill it ────────────────────────────────
        print("[Step] 03 new project form")
        page.click("button:has-text('新增專案')")
        page.wait_for_selector("#new-form", state="visible")
        page.fill("#new-name", "115年度本土文化採購（示範）")
        page.select_option("#new-type", "local_culture")
        time.sleep(0.3)
        shot("03-project-create.png", page)

        # ── Create project ────────────────────────────────────────────────
        page.click("#new-form button.btn-primary")  # 建立
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(".project-card")
        time.sleep(0.3)

        # Select project (navigates to selection.html via enterProject())
        page.click(".project-card button.btn-primary.btn-sm")  # 選擇
        page.wait_for_function(
            "() => window.location.href.includes('selection.html')",
            timeout=10000
        )

        # ── Import holdings ───────────────────────────────────────────────
        print("[Step] 04 import holdings")
        page.goto(f"{BASE_URL}/import.html")
        page.wait_for_load_state("networkidle")
        # Wait for project to be confirmed loaded (pid async callback complete)
        page.wait_for_function(
            "() => !document.getElementById('project-label').textContent.includes('載入中')",
            timeout=10000,
        )
        # Holdings tab active by default; file input is hidden (custom drag-drop zone)
        page.wait_for_selector("button.tab-btn", state="visible")
        page.set_input_files("#holdings-file", str(HOLDINGS_FILE))
        page.wait_for_selector("#holdings-result .alert-success", timeout=20000)
        time.sleep(0.3)
        shot("04-import-holdings.png", page)

        # ── Import vendor list (wizard A→B→C→D→E) ─────────────────────────
        print("[Step] 05 import vendor list")
        # Navigate fresh to ensure project pid is set in JS context
        page.goto(f"{BASE_URL}/import.html")
        page.wait_for_load_state("networkidle")
        page.wait_for_function(
            "() => document.getElementById('project-label').textContent.includes('目前專案：')",
            timeout=10000,
        )
        proj_text = page.locator("#project-label").text_content()
        print(f"  [Debug] {proj_text.strip()}")
        page.click("button.tab-btn:has-text('書商書單')")
        time.sleep(0.3)
        page.set_input_files("#vendor-file", str(VENDOR_FILE))

        # Wait for wizard to advance to step B (step-A-status becomes hidden after success)
        page.wait_for_selector("#step-B", state="visible", timeout=30000)
        time.sleep(0.3)
        page.click("#step-B button.btn-primary")

        # Step C: field mapping — click 下一步 (validateAndGoD)
        page.wait_for_selector("#step-C", state="visible")
        time.sleep(0.3)
        page.click("#step-C button.btn-primary")

        # Step D: extra fields — click 下一步
        page.wait_for_selector("#step-D", state="visible")
        time.sleep(0.3)
        page.click("#step-D button.btn-primary")

        # Step E: confirm — click 確認匯入
        page.wait_for_selector("#step-E", state="visible")
        time.sleep(0.3)
        page.click("#confirm-btn")
        page.wait_for_selector("#step-E-result .alert-success", timeout=30000)
        time.sleep(0.3)
        shot("05-import-vendor-list.png", page)

        # ── Match results ─────────────────────────────────────────────────
        print("[Step] 06 match results")
        page.goto(f"{BASE_URL}/match.html")
        page.wait_for_load_state("networkidle")
        # Wait for stat cards to be populated by loadStats()
        page.wait_for_selector("#stats-row .stat-card", timeout=15000)
        page.wait_for_selector("#book-body tr", timeout=10000)
        time.sleep(0.5)
        shot("06-match-results.png", page)

        # ── Selection: add 3 books ────────────────────────────────────────
        print("[Step] 07 selection")
        page.goto(f"{BASE_URL}/selection.html")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#book-grid .book-card", timeout=15000)
        time.sleep(0.5)

        for i in range(3):
            n_disabled = page.locator("button.book-cta[disabled]").count()
            available = page.locator("button.book-cta:not([disabled])")
            if available.count() == 0:
                print(f"  [warn] No more available books to add at iteration {i}")
                break
            available.first.click()
            # Wait for one more button to become disabled (API call complete)
            page.wait_for_function(
                f"() => document.querySelectorAll('button.book-cta[disabled]').length > {n_disabled}",
                timeout=8000,
            )
            time.sleep(0.3)

        time.sleep(0.5)
        shot("07-selection.png", page)

        # ── Export check ──────────────────────────────────────────────────
        print("[Step] 08 export check")
        page.goto(f"{BASE_URL}/export-check.html")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#stats-row .stat-card", timeout=15000)
        time.sleep(0.5)
        shot("08-export-check.png", page)

        # ── Export: fill school name (示範國小), screenshot before clicking ─
        print("[Step] 09 export page")
        page.goto(f"{BASE_URL}/export.html")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("#school-name")
        page.fill("#school-name", SCHOOL_NAME)
        time.sleep(0.3)
        shot("09-export.png", page)

        # ── Trigger export and intercept download ─────────────────────────
        print("[Step] Triggering export...")
        with page.expect_download(timeout=30000) as dl_ctx:
            page.click("#export-btn")
        dl_ctx.value  # Wait for download to be ready; discard file
        page.wait_for_load_state("networkidle")
        time.sleep(0.5)

        # ── Projects dashboard after export ───────────────────────────────
        print("[Step] 10 dashboard after export")
        page.goto(f"{BASE_URL}/projects.html")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(".project-card")
        time.sleep(0.5)
        shot("10-dashboard-after-export.png", page)

        browser.close()

    print("\nAll screenshots captured.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("take-screenshots.py")
    print("=" * 50)

    for f in [HOLDINGS_FILE, VENDOR_FILE]:
        if not f.exists():
            print(f"ERROR: Required file missing: {f}")
            sys.exit(1)

    username, password = read_config()
    print(f"[Config] username={username!r}, password=[hidden]")

    server_proc = None
    config_patched = False
    try:
        patch_config_for_screenshots()
        config_patched = True

        print(f"[Server] Starting uvicorn on port {SCREENSHOT_PORT}...")
        server_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(SCREENSHOT_PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_for_server(timeout=40)
        verify_login_api(username, password)

        take_screenshots(username, password)

    except Exception as exc:
        exc_str = str(exc).encode("ascii", errors="replace").decode("ascii")
        print(f"\nFAILED: {exc_str}")
        import traceback
        traceback.print_exc(file=sys.stdout)

    finally:
        if server_proc is not None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_proc.kill()
            time.sleep(1)  # Let OS release file handles before deleting DB
            print("[Server] Stopped")
        if config_patched:
            restore_config()
        cleanup_screenshot_db()

    print(f"\nDone. Images in: {IMAGES_DIR.resolve()}")
    imgs = sorted(IMAGES_DIR.glob("*.png"))
    for img in imgs:
        print(f"  {img.name}  ({img.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
