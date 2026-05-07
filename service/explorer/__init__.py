"""Explorer service — read-only HTTP shell over the indexer API.

A thin static-asset + read-proxy layer that fronts the SQLite-backed indexer
(:mod:`service.indexer`) for UI consumption. Holds no protocol state; the
indexer is the source of truth and the dApp talks directly to the indexer's
JSON endpoints — the explorer exists to serve the static HTML/JS bundle and
forward CORS-safe queries.

Pure data-shape helpers live in :mod:`service.explorer.logic`; the HTTP
shell lives in :mod:`service.explorer.server`.
"""
