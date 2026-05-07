"""Paramutuel V3 indexer package.

This package consumes ParamutuelFactoryV3 / ParamutuelWagerV3 events from a
Base / Base-Sepolia JSON-RPC endpoint, mirrors them into a SQLite database,
and exposes a read-only HTTP API used by the explorer, the proposition
service, and the bet-scout agent. ADR-0010 collapsed the protocol to V3
only, so the indexer no longer recognises legacy v1/v2 / standalone freeform
event topics.

Modules
-------
``indexer``
    Event-decoding core: RPC plumbing, ``apply_log`` event-application
    state machine (idempotent on ``event_id``), schema bootstrap, and the
    chunked ``sync_logs`` loop with bisecting fallback for RPCs that reject
    wide block ranges.
``api``
    Synchronous HTTP read API over the SQLite database. Reads only — never
    mutates chain state. Mounted both as ``/<endpoint>`` and ``/api/...``
    so the explorer can prefix-mount it without rewriting routes.
``live_api``
    Process that combines a background sync loop with the read API in one
    daemon. Reads ``factoryAddress`` and ``indexerFromBlock`` from
    ``config/deployments.json`` (or env) so the operator does not have to
    pass them on every restart.
``sweeper``
    Best-effort daemon that calls ``expire()`` on wagers whose resolution
    window has elapsed, defaulting to dry-run.

The package marker is intentionally lightweight; the modules are imported
lazily by their CLI entrypoints.
"""

