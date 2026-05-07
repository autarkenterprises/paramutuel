"""Control panel — operator-facing CLI + web shell over the V3 protocol.

Builds calldata for the operator's wager-lifecycle actions (create, resolve,
retract, expire, fee withdraw) and dispatches them via ``cast send``.
Operator-facing only — there is no public route into this service. Two
guard rails enforce that posture:

1. The dispatcher requires an explicit ``--allow-execute`` flag at process
   start. Without it, every action returns a dry-run command rather than
   broadcasting a transaction.
2. The web shell gates write paths on a bearer token via
   :func:`service.control_panel.security.token_authorized`. Read paths
   exist only as convenience over the indexer; nothing here exposes
   keying material.

Submodules:

- :mod:`commands` — calldata builders shared with the proposition service.
- :mod:`security` — token check used by both this and the proposition shell.
- :mod:`cli` — argparse-driven command-line surface.
- :mod:`web` — token-gated HTTP shell mirroring the CLI commands.
"""
