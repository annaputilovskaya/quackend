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


def test_get_missing_collection_returns_empty_list(store: QuackStore) -> None:
    assert store.get_all("unknown") == []


def test_ensure_generates_collection_with_sequential_ids(store: QuackStore) -> None:
    store.ensure("users", USER_SCHEMA)
    items = store.get_all("users")
    assert len(items) == COLLECTION_SIZE
    assert items[0]["id"] == "1"
    assert items[-1]["id"] == str(COLLECTION_SIZE)


def test_set_seed_42_produces_identical_collections() -> None:
    first = QuackStore()
    first.set_seed(42)
    first.ensure("users", USER_SCHEMA)
    second = QuackStore()
    second.set_seed(42)
    second.ensure("users", USER_SCHEMA)
    assert first.get_all("users") == second.get_all("users")


def test_get_existing_key_returns_item(store: QuackStore) -> None:
    store.ensure("users", USER_SCHEMA)

    item = store.get("users", "5")

    assert item is not None
    assert item["id"] == "5"


def test_get_missing_key_returns_none(store: QuackStore) -> None:
    store.ensure("users", USER_SCHEMA)
    assert store.get("users", "999") is None


def test_create_without_id_assigns_next_key(store: QuackStore) -> None:
    store.ensure("users", USER_SCHEMA)

    created = store.create("users", {"name": "Bob"})
    stored = store.get("users", created["id"])

    assert created["id"] == str(COLLECTION_SIZE + 1)
    assert stored is not None
    assert stored["name"] == "Bob"


def test_update_existing_key_persists_changes(store: QuackStore) -> None:
    store.ensure("users", USER_SCHEMA)

    updated = store.update("users", "2", {"name": "Updated"})
    stored = store.get("users", "2")

    assert updated is not None
    assert stored is not None
    assert stored["name"] == "Updated"


def test_update_missing_key_returns_none(store: QuackStore) -> None:
    store.ensure("users", USER_SCHEMA)
    assert store.update("users", "999", {}) is None


def test_delete_existing_key_returns_true(store: QuackStore) -> None:
    store.ensure("users", USER_SCHEMA)
    assert store.delete("users", "2") is True
    assert store.get("users", "2") is None


def test_delete_missing_key_returns_false(store: QuackStore) -> None:
    store.ensure("users", USER_SCHEMA)
    assert store.delete("users", "999") is False


def test_ensure_broken_schema_propagates_warning(store: QuackStore) -> None:
    warnings: list[str] = []
    store.ensure("broken", {"properties": {"x": {}}}, warn=warnings.append)
    assert any("missing type" in w for w in warnings)


def test_first_or_create_persists_the_generated_item(store: QuackStore) -> None:
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}

    created = store.first_or_create("widgets", "abc", schema)
    stored = store.get("widgets", "abc")
    again = store.first_or_create("widgets", "abc", schema)

    assert created["id"] == "abc"
    # Persistence, not object identity: the second call has to hand back the very
    # item the store holds, otherwise it regenerated a fresh name under the same
    # key. Comparing values keeps a store that hands out copies legal.
    assert stored == created
    assert again == created


def test_first_or_create_returns_seeded_item(store: QuackStore) -> None:
    store.ensure("widgets", {"type": "object", "properties": {"name": {"type": "string"}}})

    item = store.first_or_create("widgets", "3", {"type": "object"})

    assert item["id"] == "3"


def test_first_returns_first_seeded_item(store: QuackStore) -> None:
    store.ensure("widgets", {"type": "object", "properties": {"name": {"type": "string"}}})

    first = store.first("widgets")

    assert first is not None
    assert first["id"] == "1"
    assert store.first("missing") is None


def test_create_ignores_client_supplied_id(store: QuackStore) -> None:
    store.ensure("users", USER_SCHEMA)

    created = store.create("users", {"id": "custom", "name": "Bob"})

    assert created["id"] == str(COLLECTION_SIZE + 1)
    assert store.get("users", created["id"]) == created
