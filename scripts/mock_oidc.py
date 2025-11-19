#!/usr/bin/env python3
"""
Simple mock OIDC provider for local development and testing.

This provides:
- JWKS endpoint at /.well-known/jwks.json
- Token endpoint at /token (for client credentials flow)
- Issues JWT tokens with RS256 signing

Usage:
    python scripts/mock_oidc.py

Then configure your .env:
    OIDC_ISSUER=http://localhost:9000/
    OIDC_AUDIENCE=api://rag-demo
"""
import os
import json
import jwt
import secrets
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel


app = FastAPI(title="Mock OIDC Provider")

# Generate RSA key pair on startup
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)
public_key = private_key.public_key()

# Serialize keys
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

public_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

# Convert to JWK format for JWKS endpoint
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
import base64

def pem_to_jwk(pem_bytes):
    """Convert PEM to JWK format."""
    public_key_obj = serialization.load_pem_public_key(pem_bytes, backend=default_backend())
    if isinstance(public_key_obj, RSAPublicKey):
        numbers = public_key_obj.public_numbers()
        n = numbers.n
        e = numbers.e
        
        # Convert to base64url
        def int_to_base64url(val):
            byte_length = (val.bit_length() + 7) // 8
            bytes_val = val.to_bytes(byte_length, 'big')
            return base64.urlsafe_b64encode(bytes_val).decode('utf-8').rstrip('=')
        
        return {
            "kty": "RSA",
            "use": "sig",
            "kid": "mock-key-1",
            "n": int_to_base64url(n),
            "e": int_to_base64url(e),
            "alg": "RS256"
        }
    return None

jwks_key = pem_to_jwk(public_pem)


class TokenRequest(BaseModel):
    """Token request model."""
    grant_type: str = "client_credentials"
    client_id: str = "test-client"
    client_secret: str = "test-secret"
    scope: str = "openid"


@app.get("/.well-known/jwks.json")
async def jwks():
    """JWKS endpoint for public key discovery."""
    return {
        "keys": [jwks_key]
    }


@app.get("/.well-known/openid-configuration")
async def openid_config():
    """OpenID Connect discovery endpoint."""
    issuer = os.getenv("OIDC_ISSUER", "http://localhost:9000/")
    return {
        "issuer": issuer.rstrip("/"),
        "jwks_uri": f"{issuer.rstrip('/')}/.well-known/jwks.json",
        "token_endpoint": f"{issuer.rstrip('/')}/token",
        "response_types_supported": ["token", "id_token"],
        "id_token_signing_alg_values_supported": ["RS256"]
    }


@app.post("/token")
async def token(
    grant_type: str = Form("client_credentials"),
    client_id: str = Form("test-client"),
    client_secret: str = Form("test-secret"),
    scope: str = Form("openid"),
    # Custom claims for RAG demo
    sub: str = Form(None),
    tenant: str = Form("acme"),
    teams: str = Form("finance")  # Comma-separated
):
    """
    Token endpoint - issues JWT tokens.
    
    Query params or form data:
    - sub: User ID (default: random)
    - tenant: Tenant ID (default: acme)
    - teams: Comma-separated teams (default: finance)
    """
    issuer = os.getenv("OIDC_ISSUER", "http://localhost:9000/").rstrip("/")
    audience = os.getenv("OIDC_AUDIENCE", "api://rag-demo")
    
    # Generate user ID if not provided
    if not sub:
        sub = f"user-{secrets.token_hex(4)}@example.com"
    
    # Parse teams
    teams_list = [t.strip() for t in teams.split(",")] if teams else []
    
    # Create token payload
    now = datetime.now(timezone.utc)
    # Add 1 hour + 5 minutes buffer to avoid timing issues
    exp_time = now + timedelta(hours=1, minutes=5)
    payload = {
        "sub": sub,
        "tenant": tenant,
        "teams": teams_list,
        "iss": issuer,
        "aud": audience,
        "exp": int(exp_time.timestamp()),
        "iat": int(now.timestamp()),
        "jti": secrets.token_urlsafe(16)
    }
    
    # Sign token
    token = jwt.encode(
        payload,
        private_pem,
        algorithm="RS256",
        headers={"kid": "mock-key-1"}
    )
    
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": scope
    }


@app.get("/")
async def root():
    """Root endpoint with usage instructions."""
    return {
        "message": "Mock OIDC Provider",
        "endpoints": {
            "jwks": "/.well-known/jwks.json",
            "openid_config": "/.well-known/openid-configuration",
            "token": "/token (POST)"
        },
        "usage": {
            "get_token": "POST /token with form data: sub, tenant, teams",
            "example": "curl -X POST http://localhost:9000/token -d 'sub=alice@acme.com&tenant=acme&teams=finance,engineering'"
        }
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 9000))
    print(f"""
    Mock OIDC Provider starting on http://localhost:{port}
    
    Configure your .env:
        OIDC_ISSUER=http://localhost:{port}/
        OIDC_AUDIENCE=api://rag-demo
    
    Get a token:
        curl -X POST http://localhost:{port}/token \\
            -d "sub=alice@acme.com" \\
            -d "tenant=acme" \\
            -d "teams=finance,engineering"
    """)
    uvicorn.run(app, host="0.0.0.0", port=port)

