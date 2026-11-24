import io
import sqlite3
from types import SimpleNamespace

import openpyxl
import pandas as pd
import pytest
import yaml

import run_server
import setup_first_run
from app.config import BASE_DIR, Config, _resolve_path
from app.main import SESSION_MAX_AGE_SECONDS, _validate_session_secret, app
from app.services import import_service


def _make_vendor_xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class _SpyConn:
    """Wraps a real sqlite3 connection to count executemany calls."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self.executemany_calls = 0

    def executemany(self, sql, seq_of_parameters):
        self.executemany_calls += 1
        return self._conn.executemany(sql, seq_of_parameters)

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _create_import_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE procurement_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            project_type TEXT NOT NULL DEFAULT 'local_culture'
        );
        CREATE TABLE import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            batch_type TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            profile_id INTEGER,
            imported_by INTEGER,
            imported_at TEXT NOT NULL,
            record_count INTEGER
        );
        CREATE TABLE vendor_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            award_item TEXT,
            vendor_seq TEXT,
            title TEXT,
            author TEXT,
            isbn TEXT,
            isbn_normalized TEXT,
            publish_date TEXT,
            list_price REAL,
            purchase_price REAL,
            publisher TEXT,
            age_range TEXT,
            isbn_status TEXT,
            completeness_status TEXT,
            extra_fields TEXT,
            source_row_number INTEGER,
            raw_row TEXT,
            category TEXT,
            book_type TEXT,
            policy_topic TEXT,
            summary TEXT,
            source_url TEXT,
            recommendation_source TEXT,
            eligibility_label TEXT,
            classification_number TEXT,
            award_notes TEXT
        );
        CREATE TABLE library_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            isbn TEXT,
            isbn_normalized TEXT,
            title TEXT,
            author TEXT,
            publisher TEXT,
            publish_year TEXT,
            price REAL,
            library_record_id TEXT,
            isbn_status TEXT,
            raw_row TEXT
        );
        CREATE TABLE book_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_book_id INTEGER,
            holding_id INTEGER
        );
        INSERT INTO procurement_projects(name, project_type) VALUES ('測試專案', 'local_culture');
        """
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# 1. Config & BASE_DIR tests
# ---------------------------------------------------------------------------


def test_resolve_path_handles_memory_absolute_and_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _resolve_path(":memory:") == ":memory:"
    abs_path = str((tmp_path / "custom.db").resolve())
    assert _resolve_path(abs_path) == abs_path
    assert _resolve_path("./data/school_lib.db") == str((BASE_DIR / "data" / "school_lib.db").resolve())


def test_config_errors_have_chinese_guidance(tmp_path):
    missing = tmp_path / "missing.yaml"
    with pytest.raises(RuntimeError, match="找不到設定檔"):
        Config(missing)

    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text('auth:\n  default_admin_password: "unterminated\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="YAML 格式錯誤"):
        Config(bad_yaml)

    incomplete = tmp_path / "incomplete.yaml"
    incomplete.write_text("server:\n  host: 127.0.0.1\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="缺少必要欄位"):
        Config(incomplete)


# ---------------------------------------------------------------------------
# 2. Session security tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_secret", [None, "", "   ", "<generate-a-random-secret>"])
def test_validate_session_secret_rejects_default_or_empty(bad_secret):
    with pytest.raises(RuntimeError, match="session_secret_key"):
        _validate_session_secret(bad_secret)


def test_validate_session_secret_accepts_valid_key():
    assert _validate_session_secret("a-valid-random-secret-key") == "a-valid-random-secret-key"


def test_session_middleware_has_max_age_and_same_site():
    session_middlewares = [m for m in app.user_middleware if m.cls.__name__ == "SessionMiddleware"]
    assert len(session_middlewares) == 1
    kwargs = session_middlewares[0].kwargs
    assert kwargs.get("max_age") == SESSION_MAX_AGE_SECONDS
    assert kwargs.get("same_site") == "lax"


# ---------------------------------------------------------------------------
# 3. setup_first_run tests
# ---------------------------------------------------------------------------


def test_setup_first_run_needs_setup_and_escapes_special_chars(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    assert setup_first_run.needs_setup(cfg_path) is True

    tricky_password = "p@ss\"word\\with#hash:colon'quote"
    secret_key = "0123456789abcdef" * 4
    setup_first_run.apply_setup_values(
        cfg_path,
        password=tricky_password,
        secret_key=secret_key,
        example_path=BASE_DIR / "config.example.yaml",
    )

    assert setup_first_run.needs_setup(cfg_path) is False
    parsed = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert parsed["auth"]["default_admin_password"] == tricky_password
    assert parsed["auth"]["session_secret_key"] == secret_key


def test_setup_first_run_preserves_existing_custom_settings(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    example_text = (BASE_DIR / "config.example.yaml").read_text(encoding="utf-8")
    cfg_path.write_text(example_text.replace("port: 8765", "port: 9123"), encoding="utf-8")

    setup_first_run.apply_setup_values(
        cfg_path,
        password="my-safe-password",
        secret_key="fedcba9876543210" * 4,
        example_path=BASE_DIR / "config.example.yaml",
    )

    parsed = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert parsed["server"]["port"] == 9123
    assert parsed["auth"]["default_admin_password"] == "my-safe-password"


# ---------------------------------------------------------------------------
# 4. run_server tests
# ---------------------------------------------------------------------------


def test_build_browser_url():
    assert run_server.build_browser_url("0.0.0.0", 8765) == "http://127.0.0.1:8765"
    assert run_server.build_browser_url("127.0.0.1", 9001) == "http://127.0.0.1:9001"


def test_run_server_already_running_opens_browser_and_exits_zero(monkeypatch, capsys):
    opened: list[str] = []
    uvicorn_called: list[bool] = []
    monkeypatch.setattr(run_server, "get_config", lambda: SimpleNamespace(server_host="127.0.0.1", server_port=8765))
    monkeypatch.setattr(run_server, "is_port_in_use", lambda host, port: True)
    monkeypatch.setattr(run_server, "check_health", lambda url: True)
    monkeypatch.setattr(run_server.webbrowser, "open", lambda url: opened.append(url) or True)
    monkeypatch.setattr(run_server.uvicorn, "run", lambda *args, **kwargs: uvicorn_called.append(True))

    code = run_server.main()
    out = capsys.readouterr().out
    assert code == 0
    assert "系統已在執行中" in out
    assert opened == ["http://127.0.0.1:8765"]
    assert uvicorn_called == []


def test_run_server_port_conflict_shows_guidance_and_exits_nonzero(monkeypatch, capsys):
    opened: list[str] = []
    monkeypatch.setattr(run_server, "get_config", lambda: SimpleNamespace(server_host="127.0.0.1", server_port=8765))
    monkeypatch.setattr(run_server, "is_port_in_use", lambda host, port: True)
    monkeypatch.setattr(run_server, "check_health", lambda url: False)
    monkeypatch.setattr(run_server.webbrowser, "open", lambda url: opened.append(url) or True)

    code = run_server.main()
    out = capsys.readouterr().out
    assert code == 1
    assert "Port 8765" in out
    assert "config.yaml" in out
    assert "server.port" in out
    assert opened == []


def test_run_server_starts_uvicorn_when_port_free(monkeypatch):
    run_calls: list[tuple] = []
    monkeypatch.setattr(run_server, "get_config", lambda: SimpleNamespace(server_host="127.0.0.1", server_port=8888))
    monkeypatch.setattr(run_server, "is_port_in_use", lambda host, port: False)
    monkeypatch.setattr(run_server, "wait_and_open_browser", lambda url: True)
    monkeypatch.setattr(
        run_server.uvicorn,
        "run",
        lambda app_str, host, port: run_calls.append((app_str, host, port)),
    )

    code = run_server.main()
    assert code == 0
    assert run_calls == [("app.main:app", "127.0.0.1", 8888)]


# ---------------------------------------------------------------------------
# 5. import_service performance & deduplication tests
# ---------------------------------------------------------------------------


def test_preview_excel_reads_only_one_data_row(monkeypatch):
    xlsx = _make_vendor_xlsx(
        [
            ["書名", "作者", "條碼", "定價", "單價"],
            ["書一", "作者A", "9789571234567", "300", "225"],
            ["書二", "作者B", "9789571234574", "350", "260"],
        ]
    )
    observed_nrows: list[int | None] = []
    orig_read_excel = pd.read_excel

    def spy_read_excel(*args, **kwargs):
        observed_nrows.append(kwargs.get("nrows"))
        return orig_read_excel(*args, **kwargs)

    monkeypatch.setattr(import_service.pd, "read_excel", spy_read_excel)
    res = import_service.preview_excel(xlsx, "sample.xlsx", header_row=0)
    assert res["source_columns"] == ["書名", "作者", "條碼", "定價", "單價"]
    assert observed_nrows == [1]


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=ROUND(G2*75%,0)", 0.75),
        ("=G2 * 80.5 %", 0.805),
        ("=ROUND(G2*0.75,0)", 0.75),
        ("=G2*.8", 0.8),
        ("=G2+10", None),
    ],
)
def test_parse_formula_multiplier_supports_percent_and_decimal(formula, expected):
    result = import_service._parse_formula_multiplier(formula)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_resolve_formula_purchase_price_decimal_multiplier():
    assert import_service._resolve_formula_purchase_price("=ROUND(G2*0.75,0)", 300) == 225.0
    assert import_service._resolve_formula_purchase_price("=G2*0.8", 250) == 200.0


def test_confirm_import_and_import_vendor_books_use_executemany(monkeypatch):
    xlsx = _make_vendor_xlsx(
        [
            ["書名", "作者", "出版社", "條碼", "定價", "單價", "獲獎項目"],
            ["本土繪本一", "作者甲", "出版社甲", "9789571234567", "300", "=ROUND(E2*0.75,0)", "好書獎"],
            ["本土繪本二", "作者乙", "出版社乙", "9789571234574", "400", "320", "好書獎"],
            ["合計", "", "", "", "700", "545", ""],
        ]
    )
    real_conn = _create_import_db()
    spy_conn = _SpyConn(real_conn)
    monkeypatch.setattr(import_service, "get_connection", lambda: spy_conn)
    monkeypatch.setattr(import_service, "run_match", lambda pid: {"matched": 0})

    res_confirm = import_service.confirm_import(
        file_bytes=xlsx,
        filename="vendor.xlsx",
        project_id=1,
        sheet_name=None,
        header_row=0,
        mappings={
            "title": "書名",
            "author": "作者",
            "publisher": "出版社",
            "isbn": "條碼",
            "list_price": "定價",
            "purchase_price": "單價",
            "award_item": "獲獎項目",
        },
        extra_field_settings=[],
        user_id=1,
    )
    assert res_confirm["record_count"] == 2
    assert res_confirm["skipped_count"] == 1
    assert spy_conn.executemany_calls == 1

    prices = [
        r["purchase_price"] for r in real_conn.execute("SELECT purchase_price FROM vendor_books ORDER BY id").fetchall()
    ]
    assert prices == [225.0, 320.0]

    res_legacy = import_service.import_vendor_books(
        file_bytes=xlsx,
        filename="vendor.xlsx",
        project_id=1,
        user_id=1,
    )
    assert res_legacy["record_count"] == 2
    assert spy_conn.executemany_calls == 2
    assert "unmapped_fields" in res_legacy
    assert "column_mapping" in res_legacy
    real_conn.close()


def test_insert_library_holding_rows_uses_executemany():
    real_conn = _create_import_db()
    spy_conn = _SpyConn(real_conn)
    batch_id = real_conn.execute(
        "INSERT INTO import_batches(project_id, batch_type, original_filename, imported_by, imported_at) "
        "VALUES (NULL, 'library_holdings', 'holdings.xlsx', 1, '2026-11-24T00:00:00+00:00')"
    ).lastrowid

    df = pd.DataFrame(
        [
            {"條碼": "9789571234567", "書名": "館藏一", "作者": "作者A", "出版社": "出版A", "價格": "250"},
            {"條碼": "9789571234574", "書名": "館藏二", "作者": "作者B", "出版社": "出版B", "價格": "300"},
            {"條碼": "", "書名": "合計", "作者": "", "出版社": "", "價格": "550"},
        ]
    )
    mapping = {"條碼": "isbn", "書名": "title", "作者": "author", "出版社": "publisher", "價格": "price"}
    count = import_service._insert_library_holding_rows(spy_conn, batch_id, df, mapping)
    real_conn.commit()

    assert count == 2
    assert spy_conn.executemany_calls == 1
    rows = real_conn.execute("SELECT title FROM library_holdings ORDER BY id").fetchall()
    assert [r["title"] for r in rows] == ["館藏一", "館藏二"]
    real_conn.close()
