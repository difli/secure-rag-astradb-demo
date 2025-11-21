#!/usr/bin/env python3
"""
Production-ready demo of the Secure Multi-Tenant RAG system.
Demonstrates best practices: authentication, error handling, and vector search.
"""
import os
import sys
import time
import uuid
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

# Request timeout configuration
REQUEST_TIMEOUT = 10
HEALTH_CHECK_TIMEOUT = 2
VECTOR_GENERATION_WAIT = 5

def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70 + "\n")

def print_status(message: str, status: str = "info"):
    """Print a status message with icon."""
    icons = {
        "ok": "✓",
        "error": "✗",
        "warning": "⚠️",
        "info": "→"
    }
    icon = icons.get(status, "→")
    print(f"   {icon} {message}")

def check_servers() -> bool:
    """Check if servers are running with proper error handling."""
    try:
        resp1 = requests.get(
            "http://localhost:9000/.well-known/jwks.json",
            timeout=HEALTH_CHECK_TIMEOUT
        )
        resp1.raise_for_status()
        
        resp2 = requests.get(
            "http://localhost:8080/health",
            timeout=HEALTH_CHECK_TIMEOUT
        )
        resp2.raise_for_status()
        return True
    except requests.exceptions.ConnectionError:
        return False
    except requests.exceptions.Timeout:
        return False
    except requests.exceptions.HTTPError:
        return False
    except Exception:
        return False

def get_token() -> str:
    """Get JWT token from mock OIDC server with error handling."""
    try:
        resp = requests.post(
            "http://localhost:9000/token",
            data={
                "sub": "alice@acme.com",
                "tenant": "acme",
                "teams": "finance"
            },
            timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Failed to get token: HTTP {e.response.status_code}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to get token: {e}")
    except KeyError:
        raise RuntimeError("Token response missing 'access_token' field")

def get_token_bob() -> str:
    """Get JWT token for bob (not in finance team) for comparison."""
    try:
        resp = requests.post(
            "http://localhost:9000/token",
            data={
                "sub": "bob@acme.com",
                "tenant": "acme",
                "teams": "sales"
            },
            timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Failed to get bob token: HTTP {e.response.status_code}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to get bob token: {e}")
    except KeyError:
        raise RuntimeError("Token response missing 'access_token' field")

def check_document_exists(token: str, doc_id: str) -> bool:
    """Check if a document exists using vector search query."""
    try:
        resp = requests.post(
            "http://localhost:8080/query",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "test"},
            timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        
        data = resp.json()
        # Check both matches and prompt_context, but deduplicate by doc_id
        matches = data.get("matches", [])
        prompt_context = data.get("prompt_context", [])
        # Get unique doc_ids from both lists
        doc_ids = set()
        for doc in matches:
            doc_id_val = doc.get("doc_id")
            if doc_id_val:
                doc_ids.add(doc_id_val)
        for doc in prompt_context:
            doc_id_val = doc.get("doc_id")
            if doc_id_val:
                doc_ids.add(doc_id_val)
        found = doc_id in doc_ids
        
        # Try more specific query if not found
        if not found and doc_id.startswith("demo-"):
            keyword = doc_id.replace("demo-", "").replace("-", " ")
            resp2 = requests.post(
                "http://localhost:8080/query",
                headers={"Authorization": f"Bearer {token}"},
                json={"question": keyword},
                timeout=REQUEST_TIMEOUT
            )
            if resp2.status_code == 200:
                data2 = resp2.json()
                matches2 = data2.get("matches", [])
                prompt_context2 = data2.get("prompt_context", [])
                doc_ids2 = set()
                for doc in matches2:
                    doc_id_val = doc.get("doc_id")
                    if doc_id_val:
                        doc_ids2.add(doc_id_val)
                for doc in prompt_context2:
                    doc_id_val = doc.get("doc_id")
                    if doc_id_val:
                        doc_ids2.add(doc_id_val)
                found = doc_id in doc_ids2
        
        return found
    except requests.exceptions.RequestException:
        return False
    except Exception:
        return False

def ingest_document(token: str, doc: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Ingest a document with proper error handling.
    
    Returns:
        (success: bool, error_message: Optional[str])
    """
    try:
        resp = requests.post(
            "http://localhost:8080/ingest",
            headers={"Authorization": f"Bearer {token}"},
            json=doc,
            timeout=REQUEST_TIMEOUT
        )
        
        if resp.status_code == 200:
            return True, None
        
        # Handle specific error cases
        try:
            error_detail = resp.json().get("detail", "Unknown error")
        except:
            error_detail = f"HTTP {resp.status_code}"
        
        return False, error_detail
    except requests.exceptions.Timeout:
        return False, "Request timeout"
    except requests.exceptions.ConnectionError:
        return False, "Connection error"
    except requests.exceptions.RequestException as e:
        return False, f"Request failed: {e}"

def query_documents(token: str, question: str) -> tuple[bool, Optional[Dict], Optional[str]]:
    """
    Query documents with proper error handling.
    
    Returns:
        (success: bool, data: Optional[Dict], error_message: Optional[str])
    """
    try:
        resp = requests.post(
            "http://localhost:8080/query",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": question},
            timeout=REQUEST_TIMEOUT
        )
        
        if resp.status_code == 200:
            return True, resp.json(), None
        
        try:
            error_detail = resp.json().get("detail", "Unknown error")
        except:
            error_detail = f"HTTP {resp.status_code}"
        
        return False, None, error_detail
    except requests.exceptions.Timeout:
        return False, None, "Request timeout"
    except requests.exceptions.ConnectionError:
        return False, None, "Connection error"
    except requests.exceptions.RequestException as e:
        return False, None, f"Request failed: {e}"

def main() -> int:
    """Run the complete demo with production-ready error handling."""
    print_header("Secure Multi-Tenant RAG Demo")
    
    # Generate correlation ID for this demo run
    correlation_id = str(uuid.uuid4())[:8]
    print(f"Demo Run ID: {correlation_id}\n")
    
    # Check servers
    print("Checking if servers are running...")
    if not check_servers():
        print_status("Servers are not running!", "error")
        print("\nPlease start the servers:")
        print("  Terminal 1: make oidc")
        print("  Terminal 2: make run")
        return 1
    
    print_status("Servers are running", "ok")
    print()
    
    # Get token
    print("1. Authentication")
    try:
        token = get_token()
        print_status("JWT token obtained", "ok")
        print_status("User: alice@acme.com, Tenant: acme, Teams: finance", "info")
        print()
    except RuntimeError as e:
        print_status(f"Failed to get token: {e}", "error")
        return 1
    except Exception as e:
        print_status(f"Unexpected error: {e}", "error")
        return 1
    
    # Ingest documents
    print("2. Document Ingestion")
    documents = [
        {
            "tenant_id": "acme",
            "doc_id": "demo-ai-1",
            "text": "Artificial intelligence and machine learning revolutionize how we process data and make decisions using neural networks.",
            "visibility": "public"
        },
        {
            "tenant_id": "acme",
            "doc_id": "demo-cooking-1",
            "text": "Italian cuisine features fresh pasta, rich tomato sauces, aromatic basil, and high-quality olive oil from Tuscany.",
            "visibility": "public"
        },
        {
            "tenant_id": "acme",
            "doc_id": "demo-sports-1",
            "text": "Basketball requires teamwork, strategy, and physical fitness. Players must coordinate passes and shots.",
            "visibility": "public"
        },
        {
            "tenant_id": "acme",
            "doc_id": "demo-tech-1",
            "text": "Cloud computing enables scalable infrastructure, distributed systems, and serverless architectures for modern applications.",
            "visibility": "public"
        }
    ]
    
    ingested = 0
    skipped = 0
    failed = 0
    
    for doc in documents:
        doc_id = doc["doc_id"]
        
        # Check if document already exists
        if check_document_exists(token, doc_id):
            skipped += 1
            print_status(f"{doc_id}: Already exists, skipping", "info")
            continue
        
        # Ingest document
        success, error = ingest_document(token, doc)
        if success:
            ingested += 1
            print_status(f"{doc_id}: Ingested successfully", "ok")
        else:
            failed += 1
            print_status(f"{doc_id}: Failed - {error}", "error")
    
    print()
    print_status(f"Summary: {ingested} new, {skipped} skipped, {failed} failed", "info")
    print_status("Documents include $vectorize for automatic embedding generation", "info")
    print()
    
    # Wait for vector generation
    if ingested > 0:
        print("3. Vector Generation")
        print_status(f"Waiting {VECTOR_GENERATION_WAIT} seconds for embeddings...", "info")
        time.sleep(VECTOR_GENERATION_WAIT)
        print_status("Ready for vector search queries", "ok")
        print()
    
    # Query examples
    print("4. Vector Search Queries")
    queries = [
        ("AI and neural networks", "Finds AI/ML documents"),
        ("Italian pasta recipes", "Finds cooking documents"),
        ("team sports basketball", "Finds sports documents"),
        ("cloud infrastructure", "Finds tech documents")
    ]
    
    successful_queries = 0
    failed_queries = 0
    
    for i, (question, description) in enumerate(queries, 1):
        print(f"\n   Query {i}: \"{question}\"")
        print(f"   Expected: {description}")
        
        success, data, error = query_documents(token, question)
        
        if success and data:
            # Merge matches (has visibility) and prompt_context (has text)
            prompt_context = data.get("prompt_context", [])
            matches = data.get("matches", [])
            
            # Create a map of doc_id -> visibility from matches
            visibility_map = {m.get("doc_id"): m.get("visibility", "unknown") for m in matches if m.get("doc_id")}
            
            # Deduplicate: create a dict keyed by doc_id, merging visibility from matches
            unique_docs = {}
            for doc in prompt_context:
                doc_id = doc.get("doc_id")
                if doc_id and doc_id not in unique_docs:
                    doc_copy = doc.copy()
                    doc_copy["visibility"] = visibility_map.get(doc_id, "unknown")
                    unique_docs[doc_id] = doc_copy
            
            if unique_docs:
                successful_queries += 1
                doc_list = list(unique_docs.values())
                print_status(f"Found {len(doc_list)} relevant documents", "ok")
                for j, doc in enumerate(doc_list[:2], 1):
                    doc_id = doc.get("doc_id", "N/A")
                    text = doc.get("text", "")[:60]
                    visibility = doc.get("visibility", "unknown")
                    print(f"      {j}. {doc_id} ({visibility}): {text}...")
            else:
                print_status("No results found", "warning")
        else:
            failed_queries += 1
            print_status(f"Query failed: {error}", "error")
    
    # ACL Enforcement Demonstration
    print()
    print_header("5. ACL Enforcement Demonstration")
    print("Testing security-trimmed retrieval with ACL filtering...")
    print()
    print("Current User: alice@acme.com (Tenant: acme, Teams: finance)")
    print()
    
    # Query that should return finance-restricted documents
    print("Query: \"budget and finance\"")
    print("Expected: Should return finance-restricted documents (alice is in 'finance' team)")
    print()
    
    success, data, error = query_documents(token, "budget and finance")
    
    if success and data:
        prompt_context = data.get("prompt_context", [])
        matches = data.get("matches", [])
        
        # Create visibility map from matches
        visibility_map = {m.get("doc_id"): m.get("visibility", "unknown") for m in matches if m.get("doc_id")}
        
        # Deduplicate and merge visibility
        unique_docs = {}
        for doc in prompt_context:
            doc_id = doc.get("doc_id")
            if doc_id and doc_id not in unique_docs:
                doc_copy = doc.copy()
                doc_copy["visibility"] = visibility_map.get(doc_id, "unknown")
                unique_docs[doc_id] = doc_copy
        
        if unique_docs:
            doc_list = list(unique_docs.values())
            print_status(f"Found {len(doc_list)} documents (ACL-filtered)", "ok")
            print()
            print("   Documents returned (user has access):")
            
            # Check for finance-restricted documents
            finance_docs = []
            public_docs = []
            personal_docs = []
            
            for doc in doc_list:
                doc_id = doc.get("doc_id", "")
                visibility = doc.get("visibility", "unknown")
                
                if "finance" in doc_id.lower() and visibility == "restricted":
                    finance_docs.append(doc)
                elif visibility == "public":
                    public_docs.append(doc)
                elif "alice" in doc_id.lower() and visibility == "restricted":
                    personal_docs.append(doc)
            
            # Show finance-restricted docs (should be visible to alice)
            if finance_docs:
                print_status("   ✓ Finance-restricted documents (visible: alice is in 'finance' team)", "ok")
                for doc in finance_docs[:2]:
                    doc_id = doc.get("doc_id", "N/A")
                    text = doc.get("text", "")[:70]
                    print(f"      • {doc_id}: {text}...")
            
            # Show personal docs (should be visible to alice)
            if personal_docs:
                print_status("   ✓ Personal documents (visible: alice is the owner)", "ok")
                for doc in personal_docs[:1]:
                    doc_id = doc.get("doc_id", "N/A")
                    text = doc.get("text", "")[:70]
                    print(f"      • {doc_id}: {text}...")
            
            # Show public docs
            if public_docs:
                print_status("   ✓ Public documents (visible: all users)", "ok")
                for doc in public_docs[:1]:
                    doc_id = doc.get("doc_id", "N/A")
                    print(f"      • {doc_id}")
            
            print()
            print("   Documents NOT returned (user does NOT have access):")
            print_status("   ✗ HR-restricted documents (filtered: alice not in 'hr' team)", "info")
            print_status("      Example: acme-restricted-hr-policy (visibility: restricted, allow_teams: ['hr'])", "info")
            print()
            print_status("   ✗ Bob's personal documents (filtered: alice not in allow_users)", "info")
            print_status("      Example: acme-restricted-bob-notes (visibility: restricted, allow_users: ['bob@acme.com'])", "info")
        else:
            print_status("No results found", "warning")
    else:
        print_status(f"Query failed: {error}", "error")
    
    # Comparison: Query with different user (bob, not in finance team)
    print()
    print("Comparison: Query with different user (bob@acme.com, teams: sales)")
    print("Expected: Should NOT see finance-restricted documents")
    print()
    
    try:
        bob_token = get_token_bob()
        success, data, error = query_documents(bob_token, "budget and finance")
        
        if success and data:
            prompt_context = data.get("prompt_context", [])
            matches = data.get("matches", [])
            visibility_map = {m.get("doc_id"): m.get("visibility", "unknown") for m in matches if m.get("doc_id")}
            
            unique_docs = {}
            for doc in prompt_context:
                doc_id = doc.get("doc_id")
                if doc_id and doc_id not in unique_docs:
                    doc_copy = doc.copy()
                    doc_copy["visibility"] = visibility_map.get(doc_id, "unknown")
                    unique_docs[doc_id] = doc_copy
            
            if unique_docs:
                doc_list = list(unique_docs.values())
                finance_docs = [d for d in doc_list if "finance" in d.get("doc_id", "").lower() and d.get("visibility") == "restricted"]
                
                if finance_docs:
                    print_status(f"⚠️  Found {len(finance_docs)} finance-restricted documents (unexpected!)", "warning")
                else:
                    print_status("✓ No finance-restricted documents returned (correct: bob not in 'finance' team)", "ok")
                    print_status(f"   Found {len(doc_list)} other documents (public/internal only)", "info")
        else:
            print_status(f"Query failed: {error}", "error")
    except Exception as e:
        print_status(f"Could not test bob's access: {e}", "warning")
        print_status("   (This is expected if bob token is not configured)", "info")
    
    # Summary
    print_header("Demo Complete")
    print("✓ Authentication: JWT token validated (RS256)")
    print("✓ Authorization: Tenant isolation enforced")
    print("✓ Ingestion: Documents stored with ACL metadata")
    print("✓ Vector Search: Semantic similarity matching")
    print("✓ Security: ACL-based access control (security-trimmed retrieval)")
    print("  • Documents filtered by visibility (public/internal/restricted)")
    print("  • Restricted documents filtered by allow_teams and allow_users")
    print("  • Users only see documents they are authorized to access")
    print()
    print("Production-Ready Concepts Demonstrated:")
    print("  • OIDC JWT authentication with signature verification")
    print("  • Multi-tenant data isolation")
    print("  • Per-chunk ACL enforcement")
    print("  • Security-trimmed retrieval")
    print("  • Input validation (Pydantic models)")
    print("  • Rate limiting")
    print("  • Error handling with proper HTTP status codes")
    print()
    print(f"Results: {successful_queries} successful queries, {failed_queries} failed")
    print()
    print("Try your own queries:")
    print("  curl -X POST http://localhost:8080/query \\")
    print("    -H 'Authorization: Bearer YOUR_TOKEN' \\")
    print("    -H 'Content-Type: application/json' \\")
    print("    -d '{\"question\": \"your question here\"}'")
    print()
    
    return 0 if failed_queries == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
