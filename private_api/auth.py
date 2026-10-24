"""Ephemeral local-development bearer authentication and scoped API policy."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass

TENANT_PATTERN = re.compile(r"^synthetic-org-[a-z0-9][a-z0-9-]{0,44}$")
READ_SCOPES = frozenset({
    "health:read", "findings:read", "evidence:read", "incidents:read", "reports:read",
    "telemetry:read", "processing:read", "investigations:read",
})
ALLOWED_SCOPES = READ_SCOPES | {"investigations:write"}
DEFAULT_READ_SCOPES = READ_SCOPES
MAX_TOKEN_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    role: str
    scopes: frozenset[str]
    expires_at: float

    def allows(self, scope: str) -> bool:
        return scope in self.scopes


@dataclass(frozen=True)
class AuthenticationResult:
    principal: Principal | None
    reason: str


class LocalTokenRegistry:
    """Holds only token digests; credentials expire and disappear on process exit."""

    def __init__(self, *, clock=time.time) -> None:
        self._clock = clock
        self._entries: list[tuple[bytes, Principal]] = []

    def issue_development_token(
        self,
        tenant_id: str,
        *,
        scopes: frozenset[str] = DEFAULT_READ_SCOPES,
        ttl_seconds: int = 8 * 60 * 60,
    ) -> str:
        if not TENANT_PATTERN.fullmatch(tenant_id):
            raise ValueError("tenant ID must use the synthetic-org-* format")
        if not scopes or not scopes.issubset(ALLOWED_SCOPES):
            raise ValueError("only recognized local API scopes are supported")
        if not 1 <= ttl_seconds <= MAX_TOKEN_TTL_SECONDS:
            raise ValueError("token lifetime must be between 1 second and 24 hours")
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("ascii")).digest()
        role = "local_investigator" if "investigations:write" in scopes else "local_read_only"
        principal = Principal(tenant_id, role, scopes, self._clock() + ttl_seconds)
        self._entries.append((digest, principal))
        return token

    def authenticate(self, authorization: str | None) -> AuthenticationResult:
        if not authorization:
            return AuthenticationResult(None, "missing_token")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token or token.strip() != token:
            return AuthenticationResult(None, "malformed_token")
        try:
            candidate = hashlib.sha256(token.encode("ascii")).digest()
        except UnicodeEncodeError:
            return AuthenticationResult(None, "invalid_token")
        found_expired = False
        match: Principal | None = None
        now = self._clock()
        for digest, principal in self._entries:
            if hmac.compare_digest(candidate, digest):
                if principal.expires_at <= now:
                    found_expired = True
                else:
                    match = principal
        if match is not None:
            return AuthenticationResult(match, "authenticated")
        return AuthenticationResult(None, "expired_token" if found_expired else "invalid_token")
