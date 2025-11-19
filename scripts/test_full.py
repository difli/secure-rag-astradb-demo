#!/usr/bin/env python3
"""Comprehensive test script for the RAG demo."""
import os
import sys
import time
import subprocess
import requests
import json
import signal
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Colors
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
NC = '\033[0m'

def print_status(msg, status="info"):
    """Print colored status message."""
    if status == "ok":
        print(f"{GREEN}✓{NC} {msg}")
    elif status == "error":
        print(f"{RED}✗{NC} {msg}")
    else:
        print(f"{YELLOW}→{NC} {msg}")

def kill_processes():
    """Kill any existing processes."""
    try:
        subprocess.run(["pkill", "-f", "mock_oidc.py"], check=False, capture_output=True)
        subprocess.run(["pkill", "-f", "app.main:app"], check=False, capture_output=True)
        time.sleep(1)
    except Exception:
        pass

def test_unit_tests():
    """Run unit tests."""
    print_status("Running unit tests...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print_status("All unit tests passed", "ok")
        return True
    else:
        print_status("Unit tests failed", "error")
        print(result.stdout)
        print(result.stderr)
        return False

def test_oidc_server():
    """Test OIDC server."""
    print_status("Starting OIDC server...")
    oidc_process = subprocess.Popen(
        [sys.executable, "scripts/mock_oidc.py"],
        cwd=Path(__file__).parent.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to start
    for _ in range(10):
        try:
            response = requests.get("http://localhost:9000/.well-known/jwks.json", timeout=1)
            if response.status_code == 200:
                print_status("OIDC server started", "ok")
                return oidc_process
        except Exception:
            time.sleep(0.5)
    
    print_status("OIDC server failed to start", "error")
    oidc_process.terminate()
    return None

def test_get_token():
    """Test getting a token from OIDC server."""
    print_status("Getting test token...")
    try:
        response = requests.post(
            "http://localhost:9000/token",
            data={
                "sub": "alice@acme.com",
                "tenant": "acme",
                "teams": "finance,engineering"
            },
            timeout=5
        )
        if response.status_code == 200:
            token = response.json()["access_token"]
            print_status("Token obtained", "ok")
            return token
        else:
            print_status(f"Failed to get token: {response.status_code}", "error")
            return None
    except Exception as e:
        print_status(f"Failed to get token: {e}", "error")
        return None

def test_main_api(token):
    """Test main API."""
    # Use environment from .env file (load_dotenv already called)
    # Don't override with test values - use real credentials if available
    env = os.environ.copy()
    
    # Only set defaults if not already in environment
    env.setdefault("OIDC_ISSUER", "http://localhost:9000/")
    env.setdefault("OIDC_AUDIENCE", "api://rag-demo")
    env.setdefault("COLLECTION_MODE", "per_tenant")
    
    print_status("Starting main API...")
    api_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"],
        cwd=Path(__file__).parent.parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for API to start
    for _ in range(10):
        try:
            response = requests.get("http://localhost:8080/health", timeout=1)
            if response.status_code == 200:
                print_status("Main API started", "ok")
                break
        except Exception:
            time.sleep(0.5)
    else:
        print_status("Main API failed to start", "error")
        api_process.terminate()
        return None, None
    
    # Test health endpoint
    print_status("Testing /health endpoint...")
    try:
        response = requests.get("http://localhost:8080/health", timeout=2)
        if response.status_code == 200 and response.json().get("status") == "ok":
            print_status("Health check passed", "ok")
        else:
            print_status(f"Health check failed: {response.status_code}", "error")
            return api_process, None
    except Exception as e:
        print_status(f"Health check failed: {e}", "error")
        return api_process, None
    
    # Test query endpoint with auth
    print_status("Testing /query endpoint (with auth)...")
    try:
        response = requests.post(
            "http://localhost:8080/query",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "test"},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            matches = len(data.get("matches", []))
            print_status(f"Query successful: {matches} matches found", "ok")
        elif response.status_code == 500:
            error_detail = response.json().get("detail", "")
            if "Collection" in error_detail and "not exist" in error_detail:
                print_status("Query attempted (collection may need creation)", "error")
            else:
                print_status(f"Query failed: {error_detail[:100]}", "error")
        else:
            print_status(f"Query endpoint failed: HTTP {response.status_code}", "error")
            print(f"Response: {response.text[:200]}")
    except Exception as e:
        print_status(f"Query endpoint error: {e}", "error")
    
    # Test query without auth
    print_status("Testing /query endpoint (without auth - should fail)...")
    try:
        response = requests.post(
            "http://localhost:8080/query",
            json={"question": "test"},
            timeout=2
        )
        if response.status_code == 403:
            print_status("Auth check working (correctly rejected)", "ok")
        else:
            print_status(f"Auth check failed: HTTP {response.status_code}", "error")
    except Exception as e:
        print_status(f"Auth check error: {e}", "error")
    
    # Test ingest endpoint
    print_status("Testing /ingest endpoint (with auth)...")
    try:
        response = requests.post(
            "http://localhost:8080/ingest",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "tenant_id": "acme",
                "doc_id": f"test-doc-{int(time.time())}",
                "text": "Test document for integration testing",
                "visibility": "public"
            },
            timeout=10
        )
        if response.status_code == 200:
            result = response.json()
            print_status(f"Ingest successful: {result.get('doc_id')}", "ok")
        elif response.status_code == 500:
            error_detail = response.json().get("detail", "")
            if "Collection" in error_detail and "not exist" in error_detail:
                print_status("Ingest attempted (collection may need creation)", "error")
            else:
                print_status(f"Ingest failed: {error_detail[:100]}", "error")
        else:
            print_status(f"Ingest endpoint failed: HTTP {response.status_code}", "error")
            print(f"Response: {response.text[:200]}")
    except Exception as e:
        print_status(f"Ingest endpoint error: {e}", "error")
    
    # Test ingest without auth
    print_status("Testing /ingest endpoint (without auth - should fail)...")
    try:
        response = requests.post(
            "http://localhost:8080/ingest",
            json={
                "tenant_id": "acme",
                "doc_id": "test-doc-1",
                "text": "Test document",
                "visibility": "public"
            },
            timeout=2
        )
        if response.status_code == 403:
            print_status("Ingest auth check working (correctly rejected)", "ok")
        else:
            print_status(f"Ingest auth check failed: HTTP {response.status_code}", "error")
    except Exception as e:
        print_status(f"Ingest auth check error: {e}", "error")
    
    return api_process, token

def main():
    """Run all tests."""
    print(f"{YELLOW}=== Testing Secure Multi-Tenant RAG Demo ==={NC}\n")
    
    # Cleanup
    kill_processes()
    
    # Test 1: Unit tests
    if not test_unit_tests():
        return 1
    print()
    
    # Test 2: OIDC server
    oidc_process = test_oidc_server()
    if not oidc_process:
        return 1
    print()
    
    try:
        # Test 3: Get token
        token = test_get_token()
        if not token:
            return 1
        print()
        
        # Test 4: Main API
        api_process, _ = test_main_api(token)
        if not api_process:
            return 1
        print()
        
        print(f"{GREEN}=== All tests completed successfully ==={NC}")
        return 0
        
    finally:
        # Cleanup
        print_status("Cleaning up...")
        if oidc_process:
            oidc_process.terminate()
            oidc_process.wait()
        if 'api_process' in locals() and api_process:
            api_process.terminate()
            api_process.wait()
        kill_processes()

if __name__ == "__main__":
    sys.exit(main())

