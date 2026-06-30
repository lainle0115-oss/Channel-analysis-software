from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from retail_assistant.auth_store import AuthStore


def make_store(tmp_path: Path) -> AuthStore:
    store = AuthStore(sqlite_path=tmp_path / "auth.sqlite3")
    store.init_db()
    return store


def test_register_and_authenticate_first_user_is_admin(tmp_path):
    store = make_store(tmp_path)

    user = store.register_user("Owner@Example.com", "strong-pass-1", "Owner")
    authed = store.authenticate("owner@example.com", "strong-pass-1")

    assert user.role == "admin"
    assert authed is not None
    assert authed.id == user.id
    assert authed.is_admin


def test_register_rejects_duplicate_email(tmp_path):
    store = make_store(tmp_path)
    store.register_user("user@example.com", "strong-pass-1")

    with pytest.raises(ValueError, match="已注册"):
        store.register_user("USER@example.com", "strong-pass-2")


def test_uploads_are_isolated_by_user(tmp_path):
    store = make_store(tmp_path)
    owner = store.register_user("owner@example.com", "strong-pass-1")
    user = store.register_user("user@example.com", "strong-pass-2")

    owner_upload = store.add_upload(owner.id, "owner.xlsx", "/tmp/owner.xlsx", 10)
    user_upload = store.add_upload(user.id, "user.xlsx", "/tmp/user.xlsx", 20)

    assert [record["id"] for record in store.list_uploads(owner.id)] == [owner_upload["id"]]
    assert [record["id"] for record in store.list_uploads(user.id)] == [user_upload["id"]]


def test_upload_kind_is_persisted_and_invalid_values_fall_back_to_auto(tmp_path):
    store = make_store(tmp_path)
    user = store.register_user("kind@example.com", "strong-pass-1")

    sales_upload = store.add_upload(user.id, "sales.xlsx", "/tmp/sales.xlsx", 10, upload_kind="sales")
    auto_upload = store.add_upload(user.id, "unknown.xlsx", "/tmp/unknown.xlsx", 10, upload_kind="bad-kind")

    rows = {record["id"]: record for record in store.list_uploads(user.id)}
    assert rows[sales_upload["id"]]["upload_kind"] == "sales"
    assert rows[auto_upload["id"]]["upload_kind"] == "auto"


def test_admin_user_summary_includes_upload_counts(tmp_path):
    store = make_store(tmp_path)
    owner = store.register_user("owner@example.com", "strong-pass-1")
    user = store.register_user("user@example.com", "strong-pass-2")
    store.add_upload(user.id, "sales.xlsx", "/tmp/sales.xlsx", 1234)

    rows = {row["email"]: row for row in store.list_users()}

    assert rows[owner.email]["role"] == "admin"
    assert rows[user.email]["upload_count"] == 1
    assert rows[user.email]["upload_bytes"] == 1234


def test_user_settings_round_trip(tmp_path):
    store = make_store(tmp_path)
    user = store.register_user("pipeline@example.com", "strong-pass-1", "Pipeline")

    assert store.get_user_setting(user.id, "pipeline_records") is None

    store.set_user_setting(user.id, "pipeline_records", '[{"name":"盒马"}]')
    assert store.get_user_setting(user.id, "pipeline_records") == '[{"name":"盒马"}]'

    store.set_user_setting(user.id, "pipeline_records", "[]")
    assert store.get_user_setting(user.id, "pipeline_records") == "[]"
