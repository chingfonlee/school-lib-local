import sqlite3
import pytest
from app.routers.imports import _resolve_project_type


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE procurement_projects "
        "(id INTEGER PRIMARY KEY, project_type TEXT NOT NULL)"
    )
    c.execute("INSERT INTO procurement_projects VALUES (1, 'general_books')")
    c.execute("INSERT INTO procurement_projects VALUES (2, 'local_culture')")
    c.commit()
    yield c
    c.close()


def test_general_books_project_returns_general_books(conn):
    assert _resolve_project_type(conn, 1) == "general_books"


def test_local_culture_project_returns_local_culture(conn):
    assert _resolve_project_type(conn, 2) == "local_culture"


def test_missing_project_falls_back_to_local_culture(conn):
    assert _resolve_project_type(conn, 999) == "local_culture"
