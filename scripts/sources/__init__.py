"""Fetchers for the free registers the organisation registry is built from.

Each module exposes ``fetch(cache: Path) -> dict`` that downloads into ``cache``
(skipping files already present) and returns a plain-JSON structure. Nothing
here needs an API key.
"""
