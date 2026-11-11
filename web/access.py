"""Checking Cloudflare Access tokens (used by the dev site and the admin pages).

Cloudflare Access sits in front of the site and lets in only who its policy
allows; it then passes a signed token (JWT) with each request. Checking that
token here as well means a page stays closed even if Access is switched off
or the app is reached some other way.
"""
from __future__ import annotations

from flask import Request


class AccessCheck:
    def __init__(self, team_domain : str, audience : str):
        """team_domain: e.g. myteam.cloudflareaccess.com; audience: the Access
        application's audience (AUD) tag. Either empty: nothing gets in."""
        self.team = team_domain.strip()
        self.aud = audience.strip()
        self.jwks = None
        if self.configured:
            import jwt
            self.jwks = jwt.PyJWKClient(f"https://{self.team}/cdn-cgi/access/certs",
                                        cache_keys=True)

    @property
    def configured(self) -> bool:
        return bool(self.team and self.aud)

    def email(self, request : Request) -> str | None:
        """The signed-in email ('' if the token has none), or None if the
        request carries no valid token for this Access application."""
        if self.jwks is None:
            return None
        import jwt
        token = (request.headers.get("Cf-Access-Jwt-Assertion")
                 or request.cookies.get("CF_Authorization"))
        if not token:
            return None
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.aud,
                                issuer=f"https://{self.team}")
        except Exception:
            return None
        return str(claims.get("email", "")).strip().lower()


_issuer_keys : dict = {}


def email_from_any_team(request : Request) -> str | None:
    """Like AccessCheck.email, for when the team and application aren't
    configured: accepts a token signed by the Cloudflare Access team that
    issued it (any *.cloudflareaccess.com team, any application). Cloudflare
    sets this token on every request to a path Access protects, so this
    keeps the page closed if the Access rule is ever removed."""
    import jwt
    from urllib.parse import urlparse
    token = (request.headers.get("Cf-Access-Jwt-Assertion")
             or request.cookies.get("CF_Authorization"))
    if not token:
        return None
    try:
        issuer = str(jwt.decode(token, options={"verify_signature": False}).get("iss", ""))
        url = urlparse(issuer)
        if url.scheme != "https" or not url.hostname \
                or not url.hostname.endswith(".cloudflareaccess.com") or url.path not in ("", "/"):
            return None
        if issuer not in _issuer_keys:
            if len(_issuer_keys) > 20:          # tokens from many teams: someone probing
                _issuer_keys.clear()
            _issuer_keys[issuer] = jwt.PyJWKClient(
                f"https://{url.hostname}/cdn-cgi/access/certs", cache_keys=True)
        key = _issuer_keys[issuer].get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], issuer=issuer,
                            options={"verify_aud": False})
    except Exception:
        return None
    return str(claims.get("email", "")).strip().lower()
