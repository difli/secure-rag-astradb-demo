#!/usr/bin/env python3
"""Seed restricted documents with populated ACL fields."""
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Colors
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
NC = '\033[0m'

def main():
    print(f"{YELLOW}=== Seeding Restricted Documents ==={NC}\n")
    
    # Check servers
    try:
        requests.get("http://localhost:9000/.well-known/jwks.json", timeout=2)
        requests.get("http://localhost:8080/health", timeout=2)
    except Exception:
        print(f"{RED}Error: Servers not running. Please start:{NC}")
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
        print(f"{RED}Error getting token: {e}{NC}")
        return 1
    
    # Restricted documents with populated allow lists
    restricted_docs = [
        {
            "tenant_id": "acme",
            "doc_id": "acme-finance-budget-2024",
            "text": "Confidential Finance Document: 2024 budget allocation includes $2M for R&D, $1.5M for marketing, $1M for customer support, and $500K for infrastructure improvements. Budget approval required from CFO.",
            "visibility": "restricted",
            "allow_teams": ["finance"],
            "allow_users": [],
            "deny_users": [],
            "owner_user_ids": []
        },
        {
            "tenant_id": "acme",
            "doc_id": "acme-finance-revenue-forecast",
            "text": "Finance Team Only: Revenue forecast for 2024 projects $50M in total revenue with 30% growth target. Key assumptions include 20% customer retention rate and 15% new customer acquisition.",
            "visibility": "restricted",
            "allow_teams": ["finance"],
            "allow_users": [],
            "deny_users": [],
            "owner_user_ids": []
        },
        {
            "tenant_id": "acme",
            "doc_id": "acme-alice-personal-notes",
            "text": "Personal notes for alice@acme.com: Follow up with Enterprise client ABC Corp regarding their custom integration requirements. Meeting scheduled for next week.",
            "visibility": "restricted",
            "allow_teams": [],
            "allow_users": ["alice@acme.com"],
            "deny_users": [],
            "owner_user_ids": ["alice@acme.com"]
        },
        {
            "tenant_id": "acme",
            "doc_id": "acme-restricted-sales-data",
            "text": "Confidential sales data: Q4 sales exceeded targets by 15%. Top performing regions: North America and Europe. Key accounts: ABC Corp, XYZ Inc, and Tech Solutions Ltd.",
            "visibility": "restricted",
            "allow_teams": ["sales", "finance"],
            "allow_users": [],
            "deny_users": [],
            "owner_user_ids": []
        },
        {
            "tenant_id": "acme",
            "doc_id": "acme-restricted-hr-policy",
            "text": "HR Policy Document: New remote work policy effective January 2024. All employees must complete remote work training by end of Q1. Contact HR for questions.",
            "visibility": "restricted",
            "allow_teams": ["hr"],
            "allow_users": [],
            "deny_users": [],
            "owner_user_ids": []
        },
        {
            "tenant_id": "acme",
            "doc_id": "acme-restricted-bob-notes",
            "text": "Personal notes for bob@acme.com: Review Q4 marketing campaign results. Schedule meeting with design team next Monday.",
            "visibility": "restricted",
            "allow_teams": [],
            "allow_users": ["bob@acme.com"],
            "deny_users": [],
            "owner_user_ids": ["bob@acme.com"]
        }
    ]
    
    print(f"Seeding {len(restricted_docs)} restricted documents...\n")
    
    success = 0
    failed = 0
    
    for doc in restricted_docs:
        try:
            resp = requests.post(
                "http://localhost:8080/ingest",
                headers={"Authorization": f"Bearer {token}"},
                json=doc,
                timeout=10
            )
            if resp.status_code == 200:
                allow_info = []
                if doc["allow_teams"]:
                    allow_info.append(f"teams: {doc['allow_teams']}")
                if doc["allow_users"]:
                    allow_info.append(f"users: {doc['allow_users']}")
                allow_str = ", ".join(allow_info) if allow_info else "none"
                print(f"{GREEN}✓{NC} {doc['doc_id']} (allow: {allow_str})")
                success += 1
            else:
                print(f"{RED}✗{NC} {doc['doc_id']} - HTTP {resp.status_code}")
                try:
                    error = resp.json()
                    print(f"  Error: {error.get('detail', 'Unknown')}")
                except:
                    print(f"  Response: {resp.text[:100]}")
                failed += 1
        except Exception as e:
            print(f"{RED}✗{NC} {doc['doc_id']} - Exception: {e}")
            failed += 1
    
    print(f"\n{GREEN}Summary:{NC} {success} succeeded, {failed} failed")
    
    if success > 0:
        print(f"\n{YELLOW}Verify with:{NC}")
        print("  make verify-seed")
        print("\n{YELLOW}Test query:{NC}")
        print("  curl -X POST http://localhost:8080/query \\")
        print("    -H \"Authorization: Bearer <token>\" \\")
        print("    -H \"Content-Type: application/json\" \\")
        print("    -d '{\"question\": \"What is the budget?\"}'")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())

