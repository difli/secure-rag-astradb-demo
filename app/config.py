"""Configuration management from environment variables."""
import os
import json
from typing import Dict, Optional
from enum import Enum


class CollectionMode(str, Enum):
    """Collection isolation mode."""
    PER_TENANT = "per_tenant"
    SHARED = "shared"


class Config:
    """Application configuration loaded from environment."""
    
    # Astra DB settings
    ASTRA_DB_ID: str
    ASTRA_REGION: str
    KEYSPACE: str = "rag"
    
    # Token management (tenant -> {reader, writer})
    TOKENS: Dict[str, Dict[str, str]]
    
    # OIDC settings
    OIDC_ISSUER: str
    OIDC_AUDIENCE: str
    
    # Collection mode
    COLLECTION_MODE: CollectionMode = CollectionMode.PER_TENANT
    SHARED_COLLECTION_NAME: str = "chunks"
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    def __init__(self):
        """Load configuration from environment variables."""
        # Required Astra DB settings
        self.ASTRA_DB_ID = os.getenv("ASTRA_DB_ID")
        if not self.ASTRA_DB_ID:
            raise ValueError("ASTRA_DB_ID environment variable is required")
        
        self.ASTRA_REGION = os.getenv("ASTRA_REGION", "us-east1")
        self.KEYSPACE = os.getenv("KEYSPACE", "rag")
        
        # Load tokens
        tokens_json = os.getenv("TOKENS_JSON")
        if not tokens_json:
            raise ValueError("TOKENS_JSON environment variable is required")
        
        try:
            self.TOKENS = json.loads(tokens_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid TOKENS_JSON format: {e}")
        
        # Validate token structure
        for tenant, tokens in self.TOKENS.items():
            if not isinstance(tokens, dict) or "reader" not in tokens or "writer" not in tokens:
                raise ValueError(f"Invalid token structure for tenant '{tenant}'. Expected {{'reader': '...', 'writer': '...'}}")
        
        # OIDC settings
        self.OIDC_ISSUER = os.getenv("OIDC_ISSUER")
        if not self.OIDC_ISSUER:
            raise ValueError("OIDC_ISSUER environment variable is required")
        
        # Ensure issuer ends with /
        if not self.OIDC_ISSUER.endswith("/"):
            self.OIDC_ISSUER += "/"
        
        self.OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE")
        if not self.OIDC_AUDIENCE:
            raise ValueError("OIDC_AUDIENCE environment variable is required")
        
        # Collection mode
        mode_str = os.getenv("COLLECTION_MODE", "per_tenant")
        try:
            self.COLLECTION_MODE = CollectionMode(mode_str)
        except ValueError:
            raise ValueError(f"Invalid COLLECTION_MODE: {mode_str}. Must be 'per_tenant' or 'shared'")
        
        self.SHARED_COLLECTION_NAME = os.getenv("SHARED_COLLECTION_NAME", "chunks")
        
        # Rate limiting
        self.RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    
    def get_astra_base_url(self) -> str:
        """Build Astra DB Data API base URL."""
        return f"https://{self.ASTRA_DB_ID}-{self.ASTRA_REGION}.apps.astra.datastax.com/api/json/v1/{self.KEYSPACE}"
    
    def get_token(self, tenant_id: str, role: str = "reader") -> Optional[str]:
        """Get token for tenant and role (reader/writer)."""
        tenant_tokens = self.TOKENS.get(tenant_id)
        if not tenant_tokens:
            return None
        return tenant_tokens.get(role)


# Global config instance (lazy initialization to avoid import-time errors)
_config_instance = None

def get_config():
    """Get or create the global config instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance

# Proxy class for lazy config access
class _ConfigProxy:
    """Proxy to lazy-loaded config."""
    def __getattr__(self, name):
        return getattr(get_config(), name)
    def __setattr__(self, name, value):
        # Allow setting _config_instance for testing
        if name == '_config_instance':
            object.__setattr__(self, name, value)
        else:
            setattr(get_config(), name, value)

config = _ConfigProxy()

