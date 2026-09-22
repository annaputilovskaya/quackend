import pytest

from quackend.store import COLLECTION_SIZE, QuackStore

USER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "email": {"type": "string", "format": "email"},
    },
}


@pytest.fixture()
def store() -> QuackStore:
    return QuackStore()


def test_get_missing_collection_returns_empty_list(store):
    assert store.get_all("unknown") == []


def test_ensure_generates_collection_with_sequential_ids(store):
    store.ensure("users", USER_SCHEMA)
    items = store.get_all("users")
    assert len(items) == COLLECTION_SIZE
    assert items[0]["id"] == "1"
    assert items[-1]["id"] == str(COLLECTION_SIZE)


def test_set_seed_42_produces_identical_collections():
    first = QuackStore()
    first.set_seed(42)
    first.ensure("users", USER_SCHEMA)
    second = QuackStore()
    second.set_seed(42)
    second.ensure("users", USER_SCHEMA)
    assert first.get_all("users") == second.get_all("users")


def test_get_existing_key_returns_item(store):
    store.ensure("users", USER_SCHEMA)
    assert store.get("users", "5")["id"] == "5"


def test_get_missing_key_returns_none(store):
    store.ensure("users", USER_SCHEMA)
    assert store.get("users", "999") is None


def test_create_without_id_assigns_next_key(store):
    store.ensure("users", USER_SCHEMA)
    created = store.create("users", {"name": "Bob"})
    assert created["id"] == str(COLLECTION_SIZE + 1)
    assert store.get("users", created["id"])["name"] == "Bob"


def test_update_existing_key_persists_changes(store):
    store.ensure("users", USER_SCHEMA)
    updated = store.update("users", "2", {"name": "Updated"})
    assert updated is not None
    assert store.get("users", "2")["name"] == "Updated"


def test_update_missing_key_returns_none(store):
    store.ensure("users", USER_SCHEMA)
    assert store.update("users", "999", {}) is None


def test_delete_existing_key_returns_true(store):
    store.ensure("users", USER_SCHEMA)
    assert store.delete("users", "2") is True
    assert store.get("users", "2") is None


def test_delete_missing_key_returns_false(store):
    store.ensure("users", USER_SCHEMA)
    assert store.delete("users", "999") is False


def test_ensure_broken_schema_propagates_warning(store):
    warnings = []
    store.ensure("broken", {"properties": {"x": {}}}, warn=warnings.append)
    assert any("missing type" in w for w in warnings)
