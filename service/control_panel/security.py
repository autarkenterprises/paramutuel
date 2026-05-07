"""Bearer-token gate shared by the control panel and proposition service.

Two header forms are accepted: ``X-Token: <secret>`` for clients that prefer a
custom header (curl from a runbook), and ``Authorization: Bearer <secret>``
for clients following the standard. A missing or empty ``expected_token``
fails closed — i.e. an operator who forgets to set the env var cannot
accidentally expose write endpoints, because the function returns ``False``
in that case rather than ``True``.
"""
from __future__ import annotations


def token_authorized(*, expected_token: str | None, auth_header: str | None, x_token: str | None) -> bool:
    """Return True iff the caller presents a token matching ``expected_token``.

    Fails closed when ``expected_token`` is unset (None or empty string) so a
    misconfigured deployment cannot serve write endpoints to the public.
    """
    if not expected_token:
        return False
    if x_token and x_token == expected_token:
        return True
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :] == expected_token
    return False
