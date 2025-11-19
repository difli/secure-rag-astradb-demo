#!/usr/bin/env python3
"""Quick script to seed realistic Acme company data."""
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Colors
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
NC = '\033[0m'

def main():
    print(f"{YELLOW}=== Seeding Realistic Acme Data ==={NC}\n")
    
    # Check servers
    try:
        requests.get("http://localhost:9000/.well-known/jwks.json", timeout=2)
        requests.get("http://localhost:8080/health", timeout=2)
    except Exception:
        print("Error: Servers not running. Please start:")
        print("  Terminal 1: make oidc")
        print("  Terminal 2: make run")
        return 1
    
    # Get token
    print("Getting JWT token...")
    try:
        resp = requests.post(
            "http://localhost:9000/token",
            data={"sub": "alice@acme.com", "tenant": "acme", "teams": "finance"},
            timeout=5
        )
        token = resp.json()["access_token"]
        print(f"{GREEN}✓{NC} Token obtained\n")
    except Exception as e:
        print(f"Error getting token: {e}")
        return 1
    
    # Run seed script
    print("Seeding documents...")
    result = os.system(
        f"{sys.executable} scripts/seed.py --url http://localhost:8080 --token {token} --tenant acme"
    )
    
    if result == 0:
        print(f"\n{GREEN}✓{NC} Seeding complete!")
        print(f"\n{YELLOW}Test query:{NC}")
        print("  curl -X POST http://localhost:8080/query \\")
        print("    -H \"Authorization: Bearer <token>\" \\")
        print("    -H \"Content-Type: application/json\" \\")
        print("    -d '{\"question\": \"What products does Acme offer?\"}'")
        return 0
    else:
        print(f"\nError during seeding")
        return 1

if __name__ == "__main__":
    sys.exit(main())

