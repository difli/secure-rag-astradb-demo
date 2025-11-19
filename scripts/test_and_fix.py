#!/usr/bin/env python3
"""Comprehensive test script that tests, identifies issues, and provides fixes."""
import os
import sys
import requests
import json
import time
import subprocess
import signal
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

# Colors
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

def print_status(msg, status="info"):
    """Print colored status message."""
    if status == "ok":
        print(f"{GREEN}✓{NC} {msg}")
    elif status == "error":
        print(f"{RED}✗{NC} {msg}")
    elif status == "info":
        print(f"{BLUE}→{NC} {msg}")
    else:
        print(f"{YELLOW}{msg}{NC}")

def test_servers():
    """Test if servers are running."""
    print_status("Testing servers...", "info")
    issues = []
    
    try:
        resp = requests.get("http://localhost:9000/.well-known/jwks.json", timeout=2)
        if resp.status_code == 200:
            print_status("OIDC server: running", "ok")
        else:
            issues.append("OIDC server returned non-200 status")
            print_status(f"OIDC server: HTTP {resp.status_code}", "error")
    except Exception as e:
        issues.append(f"OIDC server not running: {e}")
        print_status(f"OIDC server: not running ({e})", "error")
    
    try:
        resp = requests.get("http://localhost:8080/health", timeout=2)
        if resp.status_code == 200:
            print_status("API server: running", "ok")
        else:
            issues.append("API server returned non-200 status")
            print_status(f"API server: HTTP {resp.status_code}", "error")
    except Exception as e:
        issues.append(f"API server not running: {e}")
        print_status(f"API server: not running ({e})", "error")
    
    return issues

def test_auth():
    """Test authentication."""
    print_status("Testing authentication...", "info")
    issues = []
    
    try:
        resp = requests.post(
            "http://localhost:9000/token",
            data={"sub": "alice@acme.com", "tenant": "acme", "teams": "finance"},
            timeout=5
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            if token:
                print_status("Token obtained", "ok")
                return token, issues
            else:
                issues.append("Token response missing access_token")
                print_status("Token response missing access_token", "error")
        else:
            issues.append(f"Token endpoint returned HTTP {resp.status_code}")
            print_status(f"Token endpoint: HTTP {resp.status_code}", "error")
    except Exception as e:
        issues.append(f"Failed to get token: {e}")
        print_status(f"Failed to get token: {e}", "error")
    
    return None, issues

def test_ingest(token):
    """Test ingest endpoint."""
    print_status("Testing /ingest endpoint...", "info")
    issues = []
    
    doc = {
        "tenant_id": "acme",
        "doc_id": f"test-{int(time.time())}",
        "text": "Test document for verification",
        "visibility": "public"
    }
    
    try:
        resp = requests.post(
            "http://localhost:8080/ingest",
            headers={"Authorization": f"Bearer {token}"},
            json=doc,
            timeout=10
        )
        
        if resp.status_code == 200:
            result = resp.json()
            print_status(f"Ingest successful: {result.get('doc_id')}", "ok")
            return True, issues
        else:
            error_detail = "Unknown error"
            try:
                error_json = resp.json()
                error_detail = error_json.get("detail", str(error_json))
            except:
                error_detail = resp.text[:200]
            
            issues.append(f"Ingest failed: HTTP {resp.status_code} - {error_detail}")
            print_status(f"Ingest failed: HTTP {resp.status_code}", "error")
            print_status(f"  Error: {error_detail}", "error")
    except Exception as e:
        issues.append(f"Ingest exception: {e}")
        print_status(f"Ingest exception: {e}", "error")
    
    return False, issues

def test_query(token):
    """Test query endpoint."""
    print_status("Testing /query endpoint...", "info")
    issues = []
    
    try:
        resp = requests.post(
            "http://localhost:8080/query",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "test query"},
            timeout=10
        )
        
        if resp.status_code == 200:
            data = resp.json()
            matches = len(data.get("matches", []))
            context = len(data.get("prompt_context", []))
            print_status(f"Query successful: {matches} matches, {context} context docs", "ok")
            return True, issues
        else:
            error_detail = "Unknown error"
            try:
                error_json = resp.json()
                error_detail = error_json.get("detail", str(error_json))
            except:
                error_detail = resp.text[:200]
            
            issues.append(f"Query failed: HTTP {resp.status_code} - {error_detail}")
            print_status(f"Query failed: HTTP {resp.status_code}", "error")
            print_status(f"  Error: {error_detail}", "error")
    except Exception as e:
        issues.append(f"Query exception: {e}")
        print_status(f"Query exception: {e}", "error")
    
    return False, issues

def test_auth_enforcement():
    """Test that auth is enforced."""
    print_status("Testing authentication enforcement...", "info")
    issues = []
    
    try:
        resp = requests.post(
            "http://localhost:8080/query",
            json={"question": "test"},
            timeout=5
        )
        
        if resp.status_code == 403:
            print_status("Auth correctly enforced", "ok")
            return True, issues
        else:
            issues.append(f"Auth not enforced: HTTP {resp.status_code}")
            print_status(f"Auth check failed: HTTP {resp.status_code}", "error")
    except Exception as e:
        issues.append(f"Auth test exception: {e}")
        print_status(f"Auth test exception: {e}", "error")
    
    return False, issues

def start_servers():
    """Start OIDC and API servers if they're not running."""
    print_status("Checking if servers need to be started...", "info")
    
    oidc_process = None
    api_process = None
    
    # Check OIDC server
    try:
        requests.get("http://localhost:9000/.well-known/jwks.json", timeout=1)
        print_status("OIDC server already running", "ok")
    except:
        print_status("Starting OIDC server...", "info")
        oidc_process = subprocess.Popen(
            [sys.executable, "scripts/mock_oidc.py"],
            cwd=Path(__file__).parent.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        # Wait for server to start
        for _ in range(10):
            try:
                resp = requests.get("http://localhost:9000/.well-known/jwks.json", timeout=1)
                if resp.status_code == 200:
                    print_status("OIDC server started", "ok")
                    break
            except:
                time.sleep(0.5)
        else:
            print_status("OIDC server failed to start", "error")
            if oidc_process:
                oidc_process.terminate()
            return None, None
    
    # Check API server
    try:
        requests.get("http://localhost:8080/health", timeout=1)
        print_status("API server already running", "ok")
    except:
        print_status("Starting API server...", "info")
        env = os.environ.copy()
        api_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"],
            cwd=Path(__file__).parent.parent,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        # Wait for server to start
        for _ in range(15):
            try:
                resp = requests.get("http://localhost:8080/health", timeout=1)
                if resp.status_code == 200:
                    print_status("API server started", "ok")
                    break
            except:
                time.sleep(0.5)
        else:
            print_status("API server failed to start", "error")
            if api_process:
                api_process.terminate()
            if oidc_process:
                oidc_process.terminate()
            return None, None
    
    return oidc_process, api_process

def cleanup_servers(oidc_process, api_process):
    """Clean up started server processes."""
    if oidc_process:
        try:
            oidc_process.terminate()
            oidc_process.wait(timeout=5)
        except:
            try:
                oidc_process.kill()
            except:
                pass
    
    if api_process:
        try:
            api_process.terminate()
            api_process.wait(timeout=5)
        except:
            try:
                api_process.kill()
            except:
                pass

def main():
    print(f"{YELLOW}{'='*60}{NC}")
    print(f"{YELLOW}Comprehensive Application Test{NC}")
    print(f"{YELLOW}{'='*60}{NC}\n")
    
    all_issues = []
    oidc_process = None
    api_process = None
    servers_started = False
    
    # Test servers
    server_issues = test_servers()
    all_issues.extend(server_issues)
    
    # If servers aren't running, try to start them
    if server_issues:
        print()
        print_status("Servers not running. Attempting to start them...", "info")
        oidc_process, api_process = start_servers()
        
        if oidc_process or api_process:
            servers_started = True
            print()
            # Re-test servers
            server_issues = test_servers()
            all_issues = [issue for issue in all_issues if "not running" not in issue]
            all_issues.extend(server_issues)
        
        if server_issues:
            print(f"\n{RED}Server issues found. Please start servers manually:{NC}")
            print("  Terminal 1: make oidc")
            print("  Terminal 2: make run")
            cleanup_servers(oidc_process, api_process)
            return 1
    
    print()
    
    # Test auth
    token, auth_issues = test_auth()
    all_issues.extend(auth_issues)
    
    if not token:
        print(f"\n{RED}Authentication failed. Cannot continue tests.{NC}")
        return 1
    
    print()
    
    # Test ingest
    ingest_ok, ingest_issues = test_ingest(token)
    all_issues.extend(ingest_issues)
    
    print()
    
    # Test query
    query_ok, query_issues = test_query(token)
    all_issues.extend(query_issues)
    
    print()
    
    # Test auth enforcement
    auth_enforced, auth_enforce_issues = test_auth_enforcement()
    all_issues.extend(auth_enforce_issues)
    
    print()
    print(f"{YELLOW}{'='*60}{NC}")
    
    # Cleanup if we started servers
    if servers_started:
        print_status("Cleaning up started servers...", "info")
        cleanup_servers(oidc_process, api_process)
        print()
    
    if all_issues:
        print(f"{RED}Issues found:{NC}")
        for i, issue in enumerate(all_issues, 1):
            print(f"  {i}. {issue}")
        print()
        print(f"{YELLOW}Recommendations:{NC}")
        if any("API server" in issue for issue in all_issues):
            print("  1. Restart the API server (Ctrl+C and run 'make run' again)")
        if any("ingest" in issue.lower() for issue in all_issues):
            print("  2. Check API server logs for detailed error messages")
            print("  3. Verify collection exists: make verify-seed")
        return 1
    else:
        print(f"{GREEN}All tests passed! Application is working correctly.{NC}")
        return 0

if __name__ == "__main__":
    sys.exit(main())

