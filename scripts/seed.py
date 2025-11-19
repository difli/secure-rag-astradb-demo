#!/usr/bin/env python3
"""Seed script to populate demo data via /ingest endpoint."""
import os
import sys
import requests
import json
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import config


def create_document(
    tenant_id: str,
    doc_id: str,
    text: str,
    visibility: str,
    allow_teams: list = None,
    allow_users: list = None,
    deny_users: list = None,
    owner_user_ids: list = None,
    valid_from: str = None,
    valid_to: str = None
) -> Dict[str, Any]:
    """Create a document payload."""
    doc = {
        "tenant_id": tenant_id,
        "doc_id": doc_id,
        "text": text,
        "visibility": visibility,
        "allow_teams": allow_teams or [],
        "allow_users": allow_users or [],
        "deny_users": deny_users or [],
        "owner_user_ids": owner_user_ids or [],
        # Add $vectorize to automatically generate embeddings during insert
        "$vectorize": text
    }
    # Only include date fields if they're not None
    if valid_from is not None:
        doc["valid_from"] = valid_from
    if valid_to is not None:
        doc["valid_to"] = valid_to
    return doc


def seed_demo_data(base_url: str, token: str):
    """Seed demo documents for testing."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    documents = [
        # Public documents - Acme product information
        create_document(
            tenant_id="acme",
            doc_id="acme-product-overview",
            text="Acme Corporation offers a comprehensive suite of enterprise software solutions including CRM, ERP, and business intelligence tools. Our flagship product, Acme Enterprise Suite, helps organizations streamline operations and improve productivity.",
            visibility="public"
        ),
        create_document(
            tenant_id="acme",
            doc_id="acme-product-features",
            text="Key features of Acme products include: real-time analytics, automated workflow management, secure cloud integration, and customizable dashboards. All products come with 24/7 support and regular security updates.",
            visibility="public"
        ),
        create_document(
            tenant_id="acme",
            doc_id="acme-pricing",
            text="Acme offers flexible pricing plans: Starter ($99/month), Professional ($299/month), and Enterprise (custom pricing). All plans include core features with Enterprise adding advanced security, dedicated support, and custom integrations.",
            visibility="public"
        ),
        create_document(
            tenant_id="acme",
            doc_id="acme-customer-success",
            text="Acme has helped over 10,000 companies worldwide improve their operations. Customer testimonials highlight increased efficiency, reduced costs, and improved team collaboration as key benefits.",
            visibility="public"
        ),
        
        # Internal documents - Acme company information
        create_document(
            tenant_id="acme",
            doc_id="acme-internal-q4-results",
            text="Internal memo: Q4 financial results exceeded expectations with revenue growth of 25% year-over-year. Key drivers include strong Enterprise sales and expansion in the European market.",
            visibility="internal"
        ),
        create_document(
            tenant_id="acme",
            doc_id="acme-internal-roadmap",
            text="Internal roadmap: Q1 priorities include launching the new AI-powered analytics module, expanding the partner program, and enhancing security features based on customer feedback.",
            visibility="internal"
        ),
        
        # Restricted documents - Finance team
        create_document(
            tenant_id="acme",
            doc_id="acme-finance-budget-2024",
            text="Confidential Finance Document: 2024 budget allocation includes $2M for R&D, $1.5M for marketing, $1M for customer support, and $500K for infrastructure improvements. Budget approval required from CFO.",
            visibility="restricted",
            allow_teams=["finance"]
        ),
        create_document(
            tenant_id="acme",
            doc_id="acme-finance-revenue-forecast",
            text="Finance Team Only: Revenue forecast for 2024 projects $50M in total revenue with 30% growth target. Key assumptions include 20% customer retention rate and 15% new customer acquisition.",
            visibility="restricted",
            allow_teams=["finance"]
        ),
        
        # Restricted documents - User-specific
        create_document(
            tenant_id="acme",
            doc_id="acme-alice-personal-notes",
            text="Personal notes for alice@acme.com: Follow up with Enterprise client ABC Corp regarding their custom integration requirements. Meeting scheduled for next week.",
            visibility="restricted",
            allow_users=["alice@acme.com"],
            owner_user_ids=["alice@acme.com"]
        ),
        
        # Document with date restrictions
        create_document(
            tenant_id="acme",
            doc_id="acme-promo-2024",
            text="Limited time promotion: 20% discount on all Enterprise plans valid from 2024-01-01 to 2024-12-31. Contact sales for details.",
            visibility="public",
            valid_from="2024-01-01",
            valid_to="2024-12-31"
        ),
        
        # Denied user example
        create_document(
            tenant_id="acme",
            doc_id="acme-sensitive-info",
            text="This document contains sensitive information that should not be visible to blocked users. Access is restricted to authorized personnel only.",
            visibility="public",
            deny_users=["blocked@acme.com"]
        ),
        
        # Zen tenant documents
        create_document(
            tenant_id="zen",
            doc_id="zen-product-overview",
            text="Zen Corp focuses on mindfulness and productivity solutions. Our meditation app has over 1 million users and our productivity tools help teams achieve better work-life balance.",
            visibility="public"
        ),
        create_document(
            tenant_id="zen",
            doc_id="zen-internal-launch",
            text="Internal: New product launch scheduled for next quarter. The Zen Workspace platform will integrate meditation breaks, focus timers, and team wellness tracking.",
            visibility="internal"
        ),
    ]
    
    print(f"Seeding {len(documents)} documents to {base_url}/ingest")
    
    success_count = 0
    error_count = 0
    
    for doc in documents:
        try:
            response = requests.post(
                f"{base_url}/ingest",
                json=doc,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            print(f"✓ Ingested {doc['doc_id']}")
            success_count += 1
        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_detail = response.json().get("detail", response.text[:200])
            except:
                error_detail = response.text[:200]
            print(f"✗ Failed to ingest {doc['doc_id']}: HTTP {response.status_code} - {error_detail}")
            error_count += 1
        except Exception as e:
            print(f"✗ Failed to ingest {doc['doc_id']}: {e}")
            error_count += 1
    
    print(f"\nSummary: {success_count} succeeded, {error_count} failed")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Seed demo data")
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        help="Base URL of the API (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--token",
        help="JWT token for authentication (required)"
    )
    parser.add_argument(
        "--tenant",
        default="acme",
        help="Tenant ID to use (default: acme)"
    )
    
    args = parser.parse_args()
    
    if not args.token:
        print("Error: --token is required")
        print("\nExample JWT payload:")
        print(json.dumps({
            "sub": "alice@acme.com",
            "tenant": "acme",
            "teams": ["finance"],
            "iss": config.OIDC_ISSUER.rstrip("/"),
            "aud": config.OIDC_AUDIENCE,
            "exp": 9999999999,
            "iat": 1000000000
        }, indent=2))
        sys.exit(1)
    
    seed_demo_data(args.url, args.token)


