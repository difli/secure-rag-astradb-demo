#!/usr/bin/env python3
"""
Complete setup and test script for vector search.
Works with or without embedding service configured.
"""
import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from astrapy import DataAPIClient
from app.config import get_config

def check_embedding_service(collection):
    """Check if embedding service is configured."""
    print("Checking embedding service configuration...")
    test_doc = {
        "tenant_id": "acme",
        "doc_id": "__embedding_test__",
        "text": "test",
        "visibility": "public",
        "$vectorize": "test"
    }
    
    try:
        collection.insert_one(test_doc)
        collection.delete_one({"_id": "__embedding_test__"})
        print("✓ Embedding service is configured")
        return True
    except Exception as e:
        if "EMBEDDING_SERVICE_NOT_CONFIGURED" in str(e):
            print("✗ Embedding service NOT configured")
            return False
        else:
            # Other error, but embedding service might work
            print(f"→ Note: {e}")
            return True

def setup_collection():
    """Set up collection and insert test documents."""
    print("=" * 60)
    print("Vector Search Setup and Test")
    print("=" * 60)
    print()
    
    config = get_config()
    tokens = config.TOKENS
    acme_tokens = tokens.get("acme", {})
    writer_token = acme_tokens.get("writer")
    
    if not writer_token:
        print("✗ No writer token for acme tenant")
        return 1
    
    # Initialize
    print("1. Initializing Astra DB client...")
    try:
        client = DataAPIClient(writer_token)
        api_endpoint = f"https://{config.ASTRA_DB_ID}-{config.ASTRA_REGION}.apps.astra.datastax.com"
        database = client.get_database(api_endpoint)
        collection = database.get_collection("chunks_acme")
        print("   ✓ Client initialized")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return 1
    
    # Check embedding service
    print("\n2. Checking embedding service...")
    has_embedding_service = check_embedding_service(collection)
    
    if not has_embedding_service:
        print("\n" + "=" * 60)
        print("EMBEDDING SERVICE NOT CONFIGURED")
        print("=" * 60)
        print("\nTo enable $vectorize, you need to configure the embedding service:")
        print("\nOption 1: Via Astra DB UI")
        print("  1. Go to https://astra.datastax.com")
        print("  2. Select your database")
        print("  3. Go to 'Collections' tab")
        print("  4. Click on 'chunks_acme' collection")
        print("  5. Go to 'Settings' or 'Vector Search' section")
        print("  6. Enable 'Vector Search' or 'Embedding Service'")
        print("  7. Select an embedding provider (OpenAI, Cohere, etc.)")
        print("  8. Configure API keys if needed")
        print("\nOption 2: Via Data API (if supported)")
        print("  - Some embedding services can be configured via API")
        print("  - Check Astra DB documentation for your provider")
        print("\nAfter enabling, run this script again.")
        print("=" * 60)
        return 1
    
    # Clear existing test documents
    print("\n3. Clearing old test documents...")
    try:
        collection.delete_many({"doc_id": {"$regex": "^test-|^astrapy-test-|^api-test-"}})
        print("   ✓ Cleared old test documents")
    except Exception as e:
        print(f"   → Note: {e}")
    
    # Insert test documents with $vectorize
    print("\n4. Inserting test documents with $vectorize...")
    test_documents = [
        {
            "tenant_id": "acme",
            "doc_id": "test-ai-1",
            "text": "Artificial intelligence and machine learning algorithms process data",
            "visibility": "public",
            "allow_teams": [],
            "allow_users": [],
            "deny_users": [],
            "owner_user_ids": [],
            "$vectorize": "Artificial intelligence and machine learning algorithms process data"
        },
        {
            "tenant_id": "acme",
            "doc_id": "test-cooking-1",
            "text": "Italian pasta recipes with fresh tomatoes and basil",
            "visibility": "public",
            "allow_teams": [],
            "allow_users": [],
            "deny_users": [],
            "owner_user_ids": [],
            "$vectorize": "Italian pasta recipes with fresh tomatoes and basil"
        },
        {
            "tenant_id": "acme",
            "doc_id": "test-sports-1",
            "text": "Basketball and football teams compete in championships",
            "visibility": "public",
            "allow_teams": [],
            "allow_users": [],
            "deny_users": [],
            "owner_user_ids": [],
            "$vectorize": "Basketball and football teams compete in championships"
        }
    ]
    
    try:
        result = collection.insert_many(test_documents)
        print(f"   ✓ Inserted {len(test_documents)} documents")
        print(f"   ✓ All documents include $vectorize field")
    except Exception as e:
        print(f"   ✗ Failed to insert: {e}")
        return 1
    
    # Wait for embeddings
    print("\n5. Waiting for embedding generation (8 seconds)...")
    time.sleep(8)
    
    # Test vector search queries
    print("\n6. Testing vector search queries...")
    test_queries = [
        ("AI machine learning", "test-ai-1"),
        ("cooking pasta recipes", "test-cooking-1"),
        ("sports basketball football", "test-sports-1"),
    ]
    
    all_passed = True
    for query_text, expected_doc_id in test_queries:
        print(f"\n   Query: \"{query_text}\"")
        try:
            cursor = collection.find(
                filter={"visibility": "public"},
                sort={"$vectorize": query_text},
                options={"limit": 5}
            )
            results = list(cursor)
            
            if results:
                found_ids = [doc.get("doc_id") for doc in results]
                print(f"   ✓ Found {len(results)} results: {found_ids}")
                
                if expected_doc_id in found_ids:
                    print(f"   ✓✓ Vector search found expected document!")
                else:
                    print(f"   ⚠️  Expected document not in top results")
                    all_passed = False
            else:
                print(f"   ⚠️  No results (embeddings may still be processing)")
                all_passed = False
        except Exception as e:
            print(f"   ✗ Query failed: {e}")
            all_passed = False
    
    # Test via API endpoints
    print("\n7. Testing via FastAPI endpoints...")
    try:
        # Check if servers are running
        requests.get("http://localhost:8080/health", timeout=2)
        
        # Get token
        resp = requests.post("http://localhost:9000/token",
            data={"sub": "alice@acme.com", "tenant": "acme", "teams": "finance"},
            timeout=5)
        token = resp.json()["access_token"]
        
        # Query via API
        resp = requests.post("http://localhost:8080/query",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "machine learning AI"},
            timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            matches = len(data.get("matches", []))
            context = len(data.get("prompt_context", []))
            print(f"   ✓ API query successful: {matches} matches, {context} context docs")
        else:
            print(f"   ⚠️  API query returned: HTTP {resp.status_code}")
    except Exception as e:
        print(f"   → Note: API test skipped ({e})")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    if all_passed:
        print("✓ All vector search tests passed!")
        print("✓ Documents inserted with $vectorize")
        print("✓ Vector search queries working")
        print("✓ Ready for production use")
        return 0
    else:
        print("⚠️  Some tests had issues")
        print("→ Embeddings may still be processing")
        print("→ Try running the script again in a few seconds")
        return 1

if __name__ == "__main__":
    sys.exit(setup_collection())

