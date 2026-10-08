"""Provide a stateful in-memory store of generated mock collections."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from faker import Faker

from quackend.generator import ARRAY_MAX, DEPTH_LIMIT, generate_object

__all__ = ["COLLECTION_SIZE", "QuackStore", "StoreConfig", "StoreProtocol"]

COLLECTION_SIZE = 10


def _no_warn(_message: str) -> None:
    """Discard a fail-soft message."""


@dataclass(frozen=True, slots=True)
class StoreConfig:
    """The limits a store generates with, as a value a caller can pass in.

    Every default is the generator's own default, so an unconfigured store and a
    store configured with `StoreConfig()` generate exactly the same data and the
    two cannot drift apart.

    Attributes:
        collection_size: how many items a seeded collection holds.
        depth_limit: how deep an object nests before it becomes empty.
        array_max: the longest array a generated item can hold.
    """

    collection_size: int = COLLECTION_SIZE
    depth_limit: int = DEPTH_LIMIT
    array_max: int = ARRAY_MAX


class StoreProtocol(Protocol):
    """Contract every store adapter satisfies.

    ``build_app`` depends on this protocol instead of :class:`QuackStore`, so any
    adapter that keeps generated collections can be injected without touching
    the server.
    """

    def set_seed(self, seed: int | None) -> None:
        """Seed the internal generator for deterministic output.

        Args:
            seed: the seed value; None keeps random output.
        """

    def ensure(
        self,
        resource: str,
        schema: Mapping[str, Any],
        warn: Callable[[str], None] | None = None,
    ) -> None:
        """Generate a collection for a resource when it does not exist yet.

        Args:
            resource: the collection name.
            schema: the item schema used by the generator.
            warn: an optional callback receiving generator warnings.
        """

    def get(self, resource: str, key: str) -> dict[str, Any] | None:
        """Return one item by key, or None when absent.

        Args:
            resource: the collection name.
            key: the item key.

        Returns:
            A copy of the stored item, or None when the key is missing.
        """

    def first(self, resource: str) -> dict[str, Any] | None:
        """Return the first stored item of a collection.

        Args:
            resource: the collection name.

        Returns:
            A copy of the first item in insertion order, or None for a missing or
            empty collection.
        """

    def get_all(self, resource: str) -> list[dict[str, Any]]:
        """Return all items of a collection in insertion order.

        Args:
            resource: the collection name.

        Returns:
            A list of copies of the stored items.
        """

    def first_or_create(
        self,
        resource: str,
        key: str,
        schema: Mapping[str, Any],
        warn: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Return an existing item or generate one with the given key.

        Args:
            resource: the collection name.
            key: the item key to look up or assign.
            schema: the item schema used by the generator.
            warn: an optional callback receiving generator warnings.

        Returns:
            A copy of the stored item, generated on demand when the key is missing.
        """

    def create(self, resource: str, data: Mapping[str, Any]) -> dict[str, Any]:
        """Create and store a new item under the next free key.

        Args:
            resource: the collection name.
            data: the item payload.

        Returns:
            A copy of the stored item, including its assigned id.
        """

    def update(
        self,
        resource: str,
        key: str,
        data: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Merge data into an existing item.

        Args:
            resource: the collection name.
            key: the item key.
            data: the fields to merge.

        Returns:
            A copy of the updated item, or None when the key is missing.
        """

    def delete(self, resource: str, key: str) -> bool:
        """Remove an item, reporting whether it existed.

        Args:
            resource: the collection name.
            key: the item key.

        Returns:
            True when the item was removed, False when it was missing.
        """


class QuackStore:
    """Store mock items keyed by string ids, one collection per resource.

    Every item crosses the store boundary as a deep copy, so a client can neither
    read the store's data by mutating what it was handed nor write it by mutating
    a payload it passed in.
    """

    def __init__(self, config: StoreConfig | None = None) -> None:
        """Initialize the store with the limits it generates within.

        Args:
            config: the generation limits; the generator defaults are used
                otherwise. The store owns its Faker, so determinism is requested
                with :meth:`set_seed`.
        """
        self._config = config if config is not None else StoreConfig()
        self._fake = Faker()
        self._collections: dict[str, dict[str, dict[str, Any]]] = {}
        self._counters: dict[str, int] = {}

    def _generate(
        self,
        schema: Mapping[str, Any],
        warn: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Generate one item with the limits this store is configured with.

        Args:
            schema: the item schema used by the generator.
            warn: an optional callback receiving generator warnings.

        Returns:
            A generated object.
        """
        return generate_object(
            schema,
            self._fake,
            warn,
            depth_limit=self._config.depth_limit,
            array_max=self._config.array_max,
        )

    def set_seed(self, seed: int | None) -> None:
        """Seed the internal Faker for deterministic generation.

        Args:
            seed: the faker seed; None keeps random output.
        """
        if seed is not None:
            self._fake.seed_instance(seed)

    def ensure(
        self,
        resource: str,
        schema: Mapping[str, Any],
        warn: Callable[[str], None] | None = None,
    ) -> None:
        """Generate a collection for a resource when it does not exist yet.

        Args:
            resource: the collection name.
            schema: the item schema used by the generator.
            warn: an optional callback receiving generator warnings.
        """
        if resource in self._collections:
            return

        emit = warn if warn is not None else _no_warn

        def on_warn(message: str) -> None:
            emit(f"{resource}: {message}")

        items: dict[str, dict[str, Any]] = {}
        for i in range(1, self._config.collection_size + 1):
            item = self._generate(schema, on_warn)
            item["id"] = str(i)
            items[str(i)] = item
        self._collections[resource] = items
        self._counters[resource] = self._config.collection_size

    def get(self, resource: str, key: str) -> dict[str, Any] | None:
        """Return one item by key, or None when absent.

        Args:
            resource: the collection name.
            key: the item key.

        Returns:
            A copy of the stored item, or None when the key is missing.
        """
        item = (self._collections.get(resource) or {}).get(key)
        return copy.deepcopy(item) if item is not None else None

    def first_or_create(
        self,
        resource: str,
        key: str,
        schema: Mapping[str, Any],
        warn: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Return an existing item or generate one with the given key.

        Args:
            resource: the collection name.
            key: the item key to look up or assign.
            schema: the item schema used by the generator.
            warn: an optional callback receiving generator warnings.

        Returns:
            A copy of the stored item, generated on demand when the key is missing.
        """
        existing = self.get(resource, key)
        if existing is not None:
            return existing

        emit = warn if warn is not None else _no_warn

        def on_warn(message: str) -> None:
            emit(f"{resource}: {message}")

        item = self._generate(schema, on_warn)
        item["id"] = key
        if resource not in self._collections:
            self._collections[resource] = {}
        self._collections[resource][key] = item
        return copy.deepcopy(item)

    def first(self, resource: str) -> dict[str, Any] | None:
        """Return the first stored item of a collection.

        Args:
            resource: the collection name.

        Returns:
            A copy of the first item in insertion order, or None for a missing or
            empty collection.
        """
        values = list((self._collections.get(resource) or {}).values())
        return copy.deepcopy(values[0]) if values else None

    def get_all(self, resource: str) -> list[dict[str, Any]]:
        """Return all items of a collection in insertion order.

        Args:
            resource: the collection name.

        Returns:
            A list of copies of the stored items.
        """
        return copy.deepcopy(list((self._collections.get(resource) or {}).values()))

    def _next_key(self, resource: str) -> str:
        """Assign the next key of a collection without ever repeating one.

        The counter and the highest key still present are read together and the
        higher of the two wins, because a seeded or already created id can be
        deleted and is then gone from the collection while a client has already
        seen it. The counter is written back in the same step, so both halves stay
        in step even when no ``create`` followed an ``ensure``.

        Args:
            resource: the collection name.

        Returns:
            A key one past every key the collection has ever handed out.
        """
        existing = (self._collections.get(resource) or {}).keys()
        numbers = [int(k) for k in existing if k.isdigit()]
        key = max(self._counters.get(resource, 0), max(numbers, default=0)) + 1
        self._counters[resource] = key
        return str(key)

    def create(self, resource: str, data: Mapping[str, Any]) -> dict[str, Any]:
        """Create and store a new item under the next free key.

        Any ``id`` in the payload is ignored: identity is assigned by the store,
        so the key of a stored item always equals its ``id``.

        Args:
            resource: the collection name.
            data: the item payload.

        Returns:
            A copy of the stored item, including its assigned id.
        """
        key = self._next_key(resource)
        item = copy.deepcopy(dict(data))
        item["id"] = key
        self._collections.setdefault(resource, {})[key] = item
        return copy.deepcopy(item)

    def update(
        self,
        resource: str,
        key: str,
        data: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Merge data into an existing item.

        Args:
            resource: the collection name.
            key: the item key.
            data: the fields to merge.

        Returns:
            A copy of the updated item, or None when the key is missing.
        """
        collection = self._collections.get(resource)
        if not collection or key not in collection:
            return None
        item = {**collection[key], **copy.deepcopy(dict(data))}
        item["id"] = key
        collection[key] = item
        return copy.deepcopy(item)

    def delete(self, resource: str, key: str) -> bool:
        """Remove an item, reporting whether it existed.

        Args:
            resource: the collection name.
            key: the item key.

        Returns:
            True when the item was removed, False when it was missing.
        """
        collection = self._collections.get(resource)
        if not collection or key not in collection:
            return False
        del collection[key]
        return True
