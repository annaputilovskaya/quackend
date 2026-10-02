import inspect
from types import MappingProxyType

import pytest

from quackend.store import COLLECTION_SIZE, QuackStore, StoreConfig, StoreProtocol

USER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "email": {"type": "string", "format": "email"},
    },
}

NESTED_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}

NESTED_OBJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "a": {
            "type": "object",
            "properties": {"b": {"type": "object", "properties": {"c": {"type": "string"}}}},
        }
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


class _FalsyWarn:
    """A working warn callback that claims to be empty."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, message: str) -> None:
        self.messages.append(message)

    def __bool__(self) -> bool:
        return False


def test_quack_store_satisfies_the_store_protocol() -> None:
    store: StoreProtocol = QuackStore()

    store.set_seed(7)
    store.ensure("users", USER_SCHEMA)

    assert len(store.get_all("users")) == COLLECTION_SIZE


def test_ensure_accepts_a_read_only_schema() -> None:
    store = QuackStore()

    store.ensure("users", MappingProxyType(USER_SCHEMA))

    item = store.first("users")
    assert item is not None
    assert isinstance(item["name"], str)


def test_first_or_create_accepts_a_read_only_schema() -> None:
    store = QuackStore()

    created = store.first_or_create("users", "1", MappingProxyType(USER_SCHEMA))

    assert created["id"] == "1"
    assert isinstance(created["name"], str)


def test_create_accepts_a_read_only_payload() -> None:
    store = QuackStore()

    created = store.create("users", MappingProxyType({"name": "Bob"}))

    assert created == {"name": "Bob", "id": "1"}
    assert store.get("users", "1") == created


def test_update_accepts_a_read_only_payload() -> None:
    store = QuackStore()
    store.ensure("users", USER_SCHEMA)

    updated = store.update("users", "1", MappingProxyType({"name": "Bob"}))

    assert updated is not None
    assert updated["name"] == "Bob"
    assert updated["id"] == "1"


def test_ensure_keeps_a_falsey_warn_callback() -> None:
    warn = _FalsyWarn()
    store = QuackStore()

    store.ensure("users", {}, warn=warn)

    assert any(message.startswith("users: missing type") for message in warn.messages)


def test_ensure_wraps_a_scalar_item_in_a_value_field() -> None:
    store = QuackStore()

    store.ensure("tags", {"type": "string", "enum": ["a"]})

    item = store.first("tags")
    assert item == {"value": "a", "id": "1"}


def test_get_returns_a_detached_copy() -> None:
    store = QuackStore()
    store.ensure("widgets", NESTED_SCHEMA)

    item = store.get("widgets", "1")
    assert item is not None
    item["tags"].append("mutated")

    stored = store.get("widgets", "1")
    assert stored is not None
    assert "mutated" not in stored["tags"]


def test_first_and_get_all_return_detached_copies() -> None:
    store = QuackStore()
    store.ensure("widgets", NESTED_SCHEMA)

    first = store.first("widgets")
    assert first is not None
    first["tags"].append("mutated")

    listed = store.get_all("widgets")
    listed[0]["tags"].append("mutated-too")

    reread_first = store.first("widgets")
    assert reread_first is not None
    assert "mutated" not in reread_first["tags"]
    assert "mutated-too" not in store.get_all("widgets")[0]["tags"]


def test_first_or_create_returns_a_detached_copy() -> None:
    store = QuackStore()

    created = store.first_or_create("widgets", "abc", NESTED_SCHEMA)
    created["tags"].append("mutated")

    stored = store.first_or_create("widgets", "abc", NESTED_SCHEMA)
    assert "mutated" not in stored["tags"]


def test_create_returns_a_detached_copy() -> None:
    store = QuackStore()

    created = store.create("widgets", {"tags": ["fresh"]})
    created["tags"].append("mutated")

    stored = store.get("widgets", created["id"])
    assert stored is not None
    assert stored["tags"] == ["fresh"]


def test_update_copies_the_payload_and_returns_a_detached_copy() -> None:
    store = QuackStore()
    store.ensure("widgets", NESTED_SCHEMA)
    payload = {"tags": ["submitted"]}

    updated = store.update("widgets", "1", payload)
    assert updated is not None
    updated["tags"].append("mutated")
    payload["tags"].append("mutated-in-the-payload-too")

    stored = store.get("widgets", "1")
    assert stored is not None
    assert stored["tags"] == ["submitted"]


def test_create_after_deleting_the_highest_id_does_not_reuse_it() -> None:
    store = QuackStore()
    store.ensure("users", USER_SCHEMA)
    store.delete("users", str(COLLECTION_SIZE))

    created = store.create("users", {"name": "Bob"})

    assert created["id"] == str(COLLECTION_SIZE + 1)


def test_create_after_deleting_every_id_does_not_restart_the_counter() -> None:
    store = QuackStore()
    store.ensure("users", USER_SCHEMA)
    for position in range(1, COLLECTION_SIZE + 1):
        store.delete("users", str(position))

    created = store.create("users", {"name": "Bob"})

    assert created["id"] == str(COLLECTION_SIZE + 1)


def test_created_ids_are_unique_within_a_seeded_collection() -> None:
    store = QuackStore()
    store.ensure("users", USER_SCHEMA)

    created = [store.create("users", {"name": name})["id"] for name in ("Ann", "Bo", "Cy")]

    assert len(set(created)) == 3


def test_the_store_takes_a_config_and_no_faker() -> None:
    assert list(inspect.signature(QuackStore.__init__).parameters) == ["self", "config"]


def test_the_collection_size_comes_from_the_config() -> None:
    store = QuackStore(StoreConfig(collection_size=3))

    store.ensure("users", USER_SCHEMA)

    assert len(store.get_all("users")) == 3


def test_the_depth_limit_comes_from_the_config() -> None:
    store = QuackStore(StoreConfig(depth_limit=1))

    store.ensure("widgets", NESTED_OBJECT_SCHEMA)

    item = store.first("widgets")
    assert item is not None
    assert item["a"] == {"b": {}}


def test_the_array_max_comes_from_the_config() -> None:
    store = QuackStore(StoreConfig(array_max=2))

    store.ensure("widgets", NESTED_SCHEMA)

    items = store.get_all("widgets")
    assert items
    assert all(len(item["tags"]) <= 2 for item in items)


def test_the_default_depth_limit_generates_one_level_deeper() -> None:
    shallow = QuackStore(StoreConfig(depth_limit=1))
    default = QuackStore()

    shallow.ensure("widgets", NESTED_OBJECT_SCHEMA)
    default.ensure("widgets", NESTED_OBJECT_SCHEMA)

    shallow_item = shallow.first("widgets")
    default_item = default.first("widgets")
    assert shallow_item is not None
    assert default_item is not None
    assert shallow_item["a"] == {"b": {}}
    assert isinstance(default_item["a"]["b"]["c"], str)
