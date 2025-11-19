#!/usr/bin/env python3
"""Delete and recreate vector-enabled collection, then seed with fresh data."""
import os
import sys
import requests
import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_config, CollectionMode

# Colors
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
NC = '\033[0m'

def print_status(msg, status="info"):
    """Print colored status message."""
    if status == "ok":
        print(f"{GREEN}✓{NC} {msg}")
    elif status == "error":
        print(f"{RED}✗{NC} {msg}")
    else:
        print(f"{YELLOW}→{NC} {msg}")

def delete_collection(collection_name: str, token: str) -> bool:
    """Delete a collection using Astra DB Data API."""
    config = get_config()
    # Delete command goes to keyspace endpoint, not collection endpoint
    base_url = f"https://{config.ASTRA_DB_ID}-{config.ASTRA_REGION}.apps.astra.datastax.com/api/json/v1/{config.KEYSPACE}"
    
    url = base_url  # Keyspace endpoint
    headers = {
        "X-Cassandra-Token": token,
        "Content-Type": "application/json"
    }
    
    # Delete collection command
    delete_cmd = {
        "deleteCollection": {
            "name": collection_name
        }
    }
    
    try:
        response = requests.post(url, json=delete_cmd, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if "errors" in result and result["errors"]:
                # Check if collection doesn't exist (that's okay)
                errors = result["errors"]
                if any(err.get("errorCode") == "COLLECTION_NOT_EXIST" for err in errors):
                    print_status(f"Collection '{collection_name}' doesn't exist (already deleted or never created)", "ok")
                    return True
                else:
                    print_status(f"Error deleting collection: {result['errors']}", "error")
                    return False
            return True
        elif response.status_code == 404:
            print_status(f"Collection '{collection_name}' doesn't exist (already deleted)", "ok")
            return True
        else:
            print_status(f"Failed to delete collection: HTTP {response.status_code}", "error")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print_status(f"Exception deleting collection: {e}", "error")
        return False

def create_collection(collection_name: str, token: str, vector: bool = True) -> bool:
    """Create a vector-enabled collection with vectorize embedding provider using astrapy."""
    config = get_config()
    
    try:
        from astrapy import DataAPIClient
        from astrapy.constants import VectorMetric
        from astrapy.info import (
            CollectionDefinition,
            CollectionVectorOptions,
            VectorServiceOptions,
        )
        
        # Use astrapy to create collection with vectorize embedding provider
        print_status(f"Creating vector-enabled collection '{collection_name}' with vectorize provider...")
        client = DataAPIClient(token)
        api_endpoint = f"https://{config.ASTRA_DB_ID}-{config.ASTRA_REGION}.apps.astra.datastax.com"
        database = client.get_database(api_endpoint)
        
        # Define collection with vectorize embedding provider
        # Using NVIDIA as default provider (can be changed to OpenAI, Cohere, etc.)
        collection_definition = CollectionDefinition(
            vector=CollectionVectorOptions(
                metric=VectorMetric.COSINE,
                service=VectorServiceOptions(
                    provider="nvidia",  # Default to NVIDIA (free tier available)
                    model_name="nvidia/nv-embedqa-e5-v5",
                )
            )
        )
        
        try:
            collection = database.create_collection(
                collection_name,
                definition=collection_definition,
            )
            print_status(f"Collection '{collection_name}' created with vectorize embedding provider", "ok")
            print_status(f"  Provider: NVIDIA (nv-embedqa-e5-v5)", "info")
            print_status(f"  Metric: COSINE", "info")
            print_status(f"  ✓ Collection is ready for \$vectorize operations", "ok")
            return True
        except Exception as e:
            error_str = str(e)
            # Check if collection already exists
            if "COLLECTION_ALREADY_EXISTS" in error_str or "already exists" in error_str.lower():
                print_status(f"Collection '{collection_name}' already exists", "ok")
                # Verify it's accessible
                collection = database.get_collection(collection_name)
                try:
                    # Try a simple operation to verify it exists
                    list(collection.find({}, limit=1))
                    print_status("Collection is accessible", "ok")
                except:
                    pass
                return True
            else:
                # If astrapy fails, fall back to Data API
                print_status(f"astrapy creation failed, trying Data API: {e}", "info")
                return create_collection_data_api(collection_name, token, vector)
    except ImportError as e:
        print_status(f"astrapy not available or missing imports: {e}", "error")
        print_status("Falling back to Data API (vectorize must be configured in UI)", "info")
        return create_collection_data_api(collection_name, token, vector)
    except Exception as e:
        print_status(f"Exception with astrapy: {e}, falling back to Data API", "info")
        return create_collection_data_api(collection_name, token, vector)


def create_collection_data_api(collection_name: str, token: str, vector: bool = True) -> bool:
    """Create a collection using Astra DB Data API (fallback method)."""
    config = get_config()
    base_url = f"https://{config.ASTRA_DB_ID}-{config.ASTRA_REGION}.apps.astra.datastax.com/api/json/v1/{config.KEYSPACE}"
    
    url = base_url
    headers = {
        "X-Cassandra-Token": token,
        "Content-Type": "application/json"
    }
    
    # Create collection command
    # Note: For vector-enabled collections, embedding service must be configured in UI
    create_cmd = {
        "createCollection": {
            "name": collection_name
        }
    }
    
    try:
        response = requests.post(url, json=create_cmd, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if "errors" in result and result["errors"]:
                errors = result["errors"]
                if any(err.get("errorCode") == "COLLECTION_ALREADY_EXISTS" for err in errors):
                    print_status(f"Collection '{collection_name}' already exists", "ok")
                    return True
                else:
                    print_status(f"Error creating collection: {result['errors']}", "error")
                    return False
            print_status(f"Collection '{collection_name}' created", "ok")
            print_status("Note: Configure embedding service in Astra DB UI for $vectorize", "info")
            return True
        else:
            print_status(f"Failed to create collection: HTTP {response.status_code}", "error")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print_status(f"Exception creating collection: {e}", "error")
        return False

def get_collection_name(tenant_id: str) -> str:
    """Get collection name based on collection mode."""
    config = get_config()
    if config.COLLECTION_MODE == CollectionMode.PER_TENANT:
        return f"chunks_{tenant_id}"
    return config.SHARED_COLLECTION_NAME

def main():
    print(f"{YELLOW}=== Reset Vector-Enabled Collection and Seed Fresh Data ==={NC}\n")
    print(f"{YELLOW}This script creates a vector-enabled collection for RAG with vector search{NC}\n")
    
    config = get_config()
    
    # Get tokens
    tokens = config.TOKENS
    acme_tokens = tokens.get("acme", {})
    writer_token = acme_tokens.get("writer")
    
    if not writer_token:
        print_status("Error: No writer token for acme tenant", "error")
        return 1
    
    # Determine collection name
    collection_name = get_collection_name("acme")
    print_status(f"Collection mode: {config.COLLECTION_MODE.value}")
    print_status(f"Collection name: {collection_name}")
    print_status(f"Purpose: RAG with vector search (requires embedding service)\n")
    
    # Delete collection
    print_status(f"Deleting existing collection '{collection_name}'...")
    if not delete_collection(collection_name, writer_token):
        print_status("Failed to delete collection. Continuing anyway...", "error")
    
    # Wait a moment
    time.sleep(2)
    
    # Create vector-enabled collection
    print_status(f"Creating vector-enabled collection '{collection_name}'...")
    if not create_collection(collection_name, writer_token, vector=True):
        print_status("Failed to create collection", "error")
        return 1
    
    print()
    print_status("IMPORTANT: For $vectorize to work, configure embedding service:", "info")
    print_status("  1. Go to Astra DB UI → Your Database → Collections", "info")
    print_status(f"  2. Click on collection '{collection_name}'", "info")
    print_status("  3. Enable 'Vector Search' or 'Embedding Service'", "info")
    print_status("  4. Select embedding provider (OpenAI, Cohere, etc.)", "info")
    print()
    
    # Wait for collection to be ready
    print_status("Waiting for collection to be ready...")
    time.sleep(5)  # Give collection more time to be ready
    
    # Verify collection is accessible by doing a test query
    print_status("Verifying collection is accessible...")
    try:
        from app.astra import astra_find
        test_result = astra_find(
            collection=collection_name,
            filter_dict={},
            sort={},
            options={"limit": 1},
            role="reader",
            tenant_id="acme"
        )
        print_status("Collection is accessible", "ok")
    except Exception as e:
        print_status(f"Warning: Collection verification failed: {e}", "error")
        print_status("Continuing anyway...", "error")
    
    # Check if OIDC and API servers are running
    print_status("Checking if servers are running...")
    try:
        requests.get("http://localhost:9000/.well-known/jwks.json", timeout=2)
        requests.get("http://localhost:8080/health", timeout=2)
        print_status("Servers are running", "ok")
    except Exception:
        print_status("Servers not running. Please start them:", "error")
        print("  Terminal 1: make oidc")
        print("  Terminal 2: make run")
        print("\nThen run: make seed-acme")
        return 1
    
    # Get JWT token
    print_status("Getting JWT token...")
    try:
        resp = requests.post(
            "http://localhost:9000/token",
            data={"sub": "alice@acme.com", "tenant": "acme", "teams": "finance"},
            timeout=5
        )
        jwt_token = resp.json()["access_token"]
        print_status("Token obtained", "ok")
    except Exception as e:
        print_status(f"Failed to get token: {e}", "error")
        return 1
    
    # Seed data
    print_status("Seeding fresh data...")
    print()
    result = os.system(
        f"{sys.executable} scripts/seed.py --url http://localhost:8080 --token {jwt_token} --tenant acme"
    )
    
    if result == 0:
        print()
        print_status("Collection reset and seeded successfully!", "ok")
        print()
        print(f"{YELLOW}Note:{NC} If you see 500 errors, the API server may need to be restarted")
        print(f"{YELLOW}      to pick up the latest error handling changes.")
        print()
        print(f"{YELLOW}Verify with:{NC}")
        print("  make verify-seed")
        return 0
    else:
        print()
        print_status("Seeding completed with errors", "error")
        print()
        print(f"{YELLOW}Troubleshooting:{NC}")
        print("  1. Restart the API server (Ctrl+C and run 'make run' again)")
        print("  2. Check the API server logs for detailed error messages")
        print("  3. Verify the collection exists: make verify-seed")
        return 1

if __name__ == "__main__":
    sys.exit(main())

