from __future__ import annotations


def token_authorized(*, expected_token: str | None, auth_header: str | None, x_token: str | None) -> bool:
    if not expected_token:
        return False
    if x_token and x_token == expected_token:
        return True
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :] == expected_token
    return False
