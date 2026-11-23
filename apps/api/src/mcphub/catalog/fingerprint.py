"""Fingerprints of what an upstream server advertises, to notice when it changes.

A tool's fingerprint covers everything a model reads or relies on: name, title,
description, schemas and annotations. A changed description is exactly what a "rug pull"
looks like (a tool that was approved, then quietly told models to do something else), so
any change is recorded as a new server version with the names of the tools it touched.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import orjson


def canonical_json(value: Any) -> bytes:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS, default=str)


def tool_fingerprint(
    *,
    name: str,
    title: str | None,
    description: str | None,
    input_schema: Mapping[str, Any] | None,
    output_schema: Mapping[str, Any] | None,
    annotations: Mapping[str, Any] | None,
) -> str:
    document = {
        "name": name,
        "title": title,
        "description": description or "",
        "input_schema": input_schema or {},
        "output_schema": output_schema,
        "annotations": annotations or {},
    }
    return hashlib.sha256(canonical_json(document)).hexdigest()


def catalog_hash(
    tool_fingerprints: Mapping[str, str],
    resource_uris: Iterable[str] = (),
    prompt_names: Iterable[str] = (),
) -> str:
    document = {
        "tools": sorted(tool_fingerprints.items()),
        "resources": sorted(resource_uris),
        "prompts": sorted(prompt_names),
    }
    return hashlib.sha256(canonical_json(document)).hexdigest()


@dataclass(frozen=True, slots=True)
class CatalogDiff:
    added: list[str]
    removed: list[str]
    changed: list[str]

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def diff_tools(previous: Mapping[str, str], current: Mapping[str, str]) -> CatalogDiff:
    """Compare `name -> fingerprint` maps from two discoveries."""
    return CatalogDiff(
        added=sorted(current.keys() - previous.keys()),
        removed=sorted(previous.keys() - current.keys()),
        changed=sorted(
            name for name in current.keys() & previous.keys() if current[name] != previous[name]
        ),
    )
