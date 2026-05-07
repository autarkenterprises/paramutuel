"""Resolution-service package.

Houses the operator-facing resolution daemon (`service.py`) and its pure
helpers (`logic.py`). The resolution service watches the indexer for V3
wagers whose betting window has closed but whose resolution window is
still open, looks up an operator-curated decision JSON keyed by wager
address, and (when explicitly authorized) submits the appropriate
`resolve(uint256)` / `resolve(string)` / `retract()` transaction via
`cast send`.

The package intentionally exports nothing at the top level; callers
either run `python -m service.resolution.service` or import the
specific helpers they need.
"""

__all__ = []
