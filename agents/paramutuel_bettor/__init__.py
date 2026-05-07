"""Bet-scout subagent: scan indexer data, rank bet ideas, and emit tx-ready hints.

This package is deliberately a *read-only* planner. It never holds a private
key, never signs, and never broadcasts: the only outputs are JSON blobs that
describe candidate placeBet calls (target address, calldata hex, approval
metadata, odds at quote time). The host (a wallet, a higher-level agent, or
a human operator) is responsible for actually signing and submitting.

Module layout, top-down:

* ``__main__`` — argparse + JSON-stdin entry point. Routes ``health``,
  ``scan``, ``recommend``, ``quote``, and ``json`` commands.
* ``planner`` — orchestrator: ``recommend`` (scan + rank) and
  ``quote_wager`` (single (wager, outcome, amount) quote).
* ``policy`` — ``pick_outcome`` strategy dispatch and per-row summarisation.
* ``odds`` — pure parimutuel maths (mirrors the on-chain payout formula and
  the MCP server's odds calculator).
* ``calldata`` — Foundry ``cast``-shelled ABI encoders for the V3
  ``placeBet`` and ``approve`` calls and the quote payload builder.
* ``indexer_client`` — thin urllib HTTP client against the indexer service.
* ``config`` — resolves the indexer base URL from env/deployments.json.

The package never imports a Web3 client and never reads a private key,
which is what keeps the subagent contract simple: feed JSON in, get JSON
out, no side effects on chain.
"""

__all__ = ["__version__"]

__version__ = "0.2.0"
