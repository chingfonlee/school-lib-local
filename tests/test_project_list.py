"""Tests for project list summary fields."""


def _project_by_id(projects, project_id):
    return next(p for p in projects if p["id"] == project_id)


def test_list_projects_returns_new_summary_fields(auth_client, project_db):
    """list_projects includes summary fields with empty defaults."""
    project_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='測試專案'"
    ).fetchone()[0]

    resp = auth_client.get("/api/projects/")

    assert resp.status_code == 200
    project = _project_by_id(resp.json(), project_id)
    assert project["last_import"] is None
    assert project["vendor_book_count"] == 0
    assert project["already_owned_count"] == 0
    assert project["selection_amount"] == 0


def test_list_projects_summary_counts_vendor_batches_and_owned_matches(auth_client, project_db):
    """list_projects summarizes vendor imports and latest owned matches."""
    project_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='測試專案'"
    ).fetchone()[0]
    project_db.execute(
        "INSERT INTO import_batches(project_id, batch_type, original_filename, imported_at) "
        "VALUES (?, 'vendor_books', 'vendor.xlsx', '2026-01-01T08:00:00')",
        (project_id,),
    )
    vendor_batch_id = project_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    project_db.execute(
        "INSERT INTO import_batches(project_id, batch_type, original_filename, imported_at) "
        "VALUES (?, 'library_holdings', 'holdings.xlsx', '2026-01-02T08:00:00')",
        (project_id,),
    )
    project_db.execute(
        "INSERT INTO vendor_books(batch_id, title, list_price, purchase_price) "
        "VALUES (?, 'Book A', 100, 80)",
        (vendor_batch_id,),
    )
    owned_book_id = project_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    project_db.execute(
        "INSERT INTO vendor_books(batch_id, title, list_price, purchase_price) "
        "VALUES (?, 'Book B', 120, 90)",
        (vendor_batch_id,),
    )
    available_book_id = project_db.execute("SELECT last_insert_rowid()").fetchone()[0]
    project_db.execute(
        "INSERT INTO book_matches(vendor_book_id, match_status) "
        "VALUES (?, 'same_title_different_isbn')",
        (owned_book_id,),
    )
    project_db.execute(
        "INSERT INTO book_matches(vendor_book_id, match_status) VALUES (?, 'already_owned')",
        (owned_book_id,),
    )
    project_db.execute(
        "INSERT INTO book_matches(vendor_book_id, match_status) VALUES (?, 'available')",
        (available_book_id,),
    )
    project_db.commit()

    resp = auth_client.get("/api/projects/")

    assert resp.status_code == 200
    project = _project_by_id(resp.json(), project_id)
    assert project["last_import"] == "2026-01-01T08:00:00"
    assert project["vendor_book_count"] == 2
    assert project["already_owned_count"] == 1


def test_list_projects_selection_amount_uses_purchase_price_mode(auth_client, project_db):
    """selection_amount uses purchase_price for quantity_times_purchase_price."""
    project_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='測試專案'"
    ).fetchone()[0]
    project_db.execute(
        "INSERT INTO selection_items(project_id, vendor_book_id, selected_quantity, list_price, purchase_price) "
        "VALUES (?, 1, 2, 100, 80)",
        (project_id,),
    )
    project_db.execute(
        "INSERT INTO selection_items(project_id, vendor_book_id, selected_quantity, list_price, purchase_price) "
        "VALUES (?, 2, 0, 500, 400)",
        (project_id,),
    )
    project_db.commit()

    resp = auth_client.get("/api/projects/")

    assert resp.status_code == 200
    project = _project_by_id(resp.json(), project_id)
    assert project["selection_count"] == 2
    assert project["selection_amount"] == 160


def test_list_projects_selection_amount_uses_list_price_mode(auth_client, project_db):
    """selection_amount uses list_price for quantity_times_list_price."""
    project_id = project_db.execute(
        "SELECT id FROM procurement_projects WHERE name='測試專案'"
    ).fetchone()[0]
    project_db.execute(
        "UPDATE procurement_projects SET subtotal_mode='quantity_times_list_price' WHERE id=?",
        (project_id,),
    )
    project_db.execute(
        "INSERT INTO selection_items(project_id, vendor_book_id, selected_quantity, list_price, purchase_price) "
        "VALUES (?, 1, 3, 100, 80)",
        (project_id,),
    )
    project_db.commit()

    resp = auth_client.get("/api/projects/")

    assert resp.status_code == 200
    project = _project_by_id(resp.json(), project_id)
    assert project["selection_amount"] == 300
