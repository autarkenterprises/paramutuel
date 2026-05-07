"""Proposition service — draft wager ingestion, operator review, dispatch.

Pipeline
--------
1. ``ingest`` walks ``config/proposition-sources.json``, fans into
   ``rss`` / ``json_sources`` per entry, and stores raw items in
   ``source_items``. ``upsert_source_item`` enforces dedupe via the
   ``UNIQUE(source_id, external_id)`` constraint, so re-running ingest
   is safe.
2. ``synthesize`` turns each new item into a conservative YES/NO
   proposition draft (or, for ``--include-calendar``, a daily/weekly
   template) and ``db.insert_proposal`` lands it as ``status='pending'``
   in ``proposals``.
3. ``server`` exposes an operator HTTP API: list / edit / approve /
   reject / dispatch. ``dispatch_proposal`` re-uses
   ``service.control_panel.commands.build_create_wager_command`` to
   construct the ``cast send`` invocation, so the proposition path and
   the manual control panel share one calldata encoder.
4. Approval flips ``pending → approved``; ``dispatch`` (gated by
   ``--allow-execute``) shells out to ``cast send`` and stores the
   resulting tx hint or stderr on the proposal row, never mutating
   chain state without an explicit operator action.

Authoritative neighbours
------------------------
* ``service.control_panel`` for the create-wager command builder and
  bearer-token authorization helper (``token_authorized``).
* The on-chain factory configured via ``--factory`` / ``FACTORY_ADDRESS``
  / ``config/deployments.json`` (same address the indexer watches).

Tests under ``service/proposition/tests/`` exercise the synth and
ingest paths against synthetic feeds; this package marker keeps the
import surface lean.
"""
