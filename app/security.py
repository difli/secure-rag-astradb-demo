"""OIDC JWT authentication and user model."""
import os
import jwt
import requests
from typing import Optional, List
from datetime import datetime
from functools import lru_cache
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


security_scheme = HTTPBearer()


class User:
    """Authenticated user model."""
    def __init__(self, sub: str, tenant: str, teams: List[str]):
        self.sub = sub
        self.tenant = tenant
        self.teams = teams
        self.authenticated = True


@lru_cache(maxsize=1)
def get_jwks(issuer: str) -> dict:
    """Fetch JWKS from OIDC issuer (cached)."""
    jwks_url = f"{issuer}.well-known/jwks.json"
    try:
        response = requests.get(jwks_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch JWKS from {jwks_url}: {e}"
        )


def get_signing_key(token: str, jwks: dict) -> Optional[str]:
    """Extract the signing key from JWKS for the token."""
    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                # Convert JWK to PEM format
                from jwt.algorithms import RSAAlgorithm
                return RSAAlgorithm.from_jwk(key)
        
        return None
    except Exception as e:
        return None


def verify_jwt(token: str, issuer: str, audience: str) -> dict:
    """Verify JWT token and return claims."""
    jwks = get_jwks(issuer)
    signing_key = get_signing_key(token, jwks)
    
    if not signing_key:
        raise HTTPException(
            status_code=401,
            detail="Unable to find signing key for token"
        )
    
    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=issuer.rstrip("/"),
            audience=audience,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
            }
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security_scheme),
    config = None
) -> User:
    """Extract and verify user from JWT token."""
    if config is None:
        from app.config import config
    
    token = credentials.credentials
    
    try:
        claims = verify_jwt(token, config.OIDC_ISSUER, config.OIDC_AUDIENCE)
    except HTTPException:
        raise
    
    # Extract required claims
    sub = claims.get("sub")
    tenant = claims.get("tenant")
    teams = claims.get("teams", [])
    
    # Handle teams as string (comma-separated) or list
    if isinstance(teams, str):
        teams = [t.strip() for t in teams.split(",")] if teams else []
    
    if not sub:
        raise HTTPException(status_code=401, detail="Missing 'sub' claim in token")
    if not tenant:
        raise HTTPException(status_code=401, detail="Missing 'tenant' claim in token")
    if not isinstance(teams, list):
        raise HTTPException(status_code=401, detail="'teams' claim must be an array or comma-separated string")
    
    return User(sub=sub, tenant=tenant, teams=teams)

