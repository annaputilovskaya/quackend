"""Provide a stateful in-memory store of generated mock collections."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from faker import Faker

from quackend.generator import generate_value

COLLECTION_SIZE = 10


class QuackStore:
    """Store mock items keyed by string ids, one collection per resource."""

    def __init__(self, fake: Faker | None = None) -> None:
        """Initialize the store, optionally reusing a shared Faker instance.

        Args:
            fake: an optional Faker instance; a new one is created otherwise.
        """
        self._fake = fake or Faker()
        self._collections: dict[str, dict[str, dict[str, Any]]] = {}
        self._schemas: dict[str, dict[str, Any]] = {}

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
        schema: dict[str, Any],
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

        def on_warn(message: str) -> None:
            if warn:
                warn(f"{resource}: {message}")

        items: dict[str, dict[str, Any]] = {}
        for i in range(1, COLLECTION_SIZE + 1):
            item = generate_value(schema, self._fake, warn=on_warn)
            if not isinstance(item, dict):
                item = {"value": item}
            item["id"] = str(i)
            items[str(i)] = item
        self._collections[resource] = items
        self._schemas[resource] = schema

    def get(self, resource: str, key: str) -> dict[str, Any] | None:
        """Return one item by key, or None when absent.

        Args:
            resource: the collection name.
            key: the item key.

        Returns:
            The stored item, or None when the key is missing.
        """
        return (self._collections.get(resource) or {}).get(key)

    def get_all(self, resource: str) -> list[dict[str, Any]]:
        """Return all items of a collection in insertion order.

        Args:
            resource: the collection name.

        Returns:
            A list of the stored items.
        """
        return list((self._collections.get(resource) or {}).values())

    def _next_key(self, resource: str) -> str:
        existing = (self._collections.get(resource) or {}).keys()
        numbers = [int(k) for k in existing if k.isdigit()]
        return str(max(numbers, default=0) + 1)

    def create(self, resource: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create and store a new item, assigning the next free key.

        Args:
            resource: the collection name.
            data: the item payload.

        Returns:
            The stored item, including its assigned id.
        """
        key = self._next_key(resource)
        item = dict(data)
        if "id" not in item:
            item["id"] = key
        if resource not in self._collections:
            self._collections[resource] = {}
        self._collections[resource][key] = item
        return item

    def update(
        self,
        resource: str,
        key: str,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Merge data into an existing item.

        Args:
            resource: the collection name.
            key: the item key.
            data: the fields to merge.

        Returns:
            The updated item, or None when the key is missing.
        """
        collection = self._collections.get(resource)
        if not collection or key not in collection:
            return None
        item = {**collection[key], **data}
        item["id"] = key
        collection[key] = item
        return item

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
