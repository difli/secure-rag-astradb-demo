#!/usr/bin/env python3
"""Verify that seeded documents have correct ACL fields populated."""
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.astra import astra_find, get_collection_name
from app.config import get_config, CollectionMode

def verify_documents():
    """Check what documents exist and their ACL fields."""
    config = get_config()
    
    # Get a token (we'll use reader token directly)
    tokens = config.TOKENS
    acme_tokens = tokens.get("acme", {})
    reader_token = acme_tokens.get("reader")
    
    if not reader_token:
        print("Error: No reader token for acme tenant")
        return
    
    collection = get_collection_name("acme")
    
    # Query all documents
    try:
        result = astra_find(
            collection=collection,
            filter_dict={},  # Get all documents
            sort={},
            options={"limit": 100},
            role="reader",
            tenant_id="acme"
        )
        
        # Extract documents
        if "data" in result:
            documents = result.get("data", {}).get("documents", [])
        elif "documents" in result:
            documents = result.get("documents", [])
        else:
            documents = []
        
        print(f"Found {len(documents)} documents in collection '{collection}'\n")
        
        # Group by visibility
        public = []
        internal = []
        restricted = []
        other = []
        
        for doc in documents:
            vis = doc.get("visibility", "unknown")
            doc_id = doc.get("doc_id", "unknown")
            allow_teams = doc.get("allow_teams", [])
            allow_users = doc.get("allow_users", [])
            
            if vis == "public":
                public.append((doc_id, allow_teams, allow_users))
            elif vis == "internal":
                internal.append((doc_id, allow_teams, allow_users))
            elif vis == "restricted":
                restricted.append((doc_id, allow_teams, allow_users))
            else:
                other.append((doc_id, vis))
        
        print("=" * 60)
        print("PUBLIC DOCUMENTS (should have empty allow lists):")
        print("=" * 60)
        for doc_id, teams, users in public[:5]:
            print(f"  {doc_id}")
            print(f"    allow_teams: {teams}")
            print(f"    allow_users: {users}")
        if len(public) > 5:
            print(f"  ... and {len(public) - 5} more public documents")
        
        print("\n" + "=" * 60)
        print("INTERNAL DOCUMENTS (should have empty allow lists):")
        print("=" * 60)
        for doc_id, teams, users in internal[:5]:
            print(f"  {doc_id}")
            print(f"    allow_teams: {teams}")
            print(f"    allow_users: {users}")
        if len(internal) > 5:
            print(f"  ... and {len(internal) - 5} more internal documents")
        
        print("\n" + "=" * 60)
        print("RESTRICTED DOCUMENTS (should have populated allow lists):")
        print("=" * 60)
        if not restricted:
            print("  ⚠️  NO RESTRICTED DOCUMENTS FOUND!")
            print("  Run 'make seed-acme' to seed documents with populated ACL fields")
        else:
            for doc_id, teams, users in restricted:
                print(f"  {doc_id}")
                print(f"    allow_teams: {teams}")
                print(f"    allow_users: {users}")
                if not teams and not users:
                    print(f"    ⚠️  WARNING: Restricted document has empty allow lists!")
        
        if other:
            print("\n" + "=" * 60)
            print("OTHER DOCUMENTS:")
            print("=" * 60)
            for doc_id, vis in other:
                print(f"  {doc_id}: visibility={vis}")
        
    except Exception as e:
        print(f"Error querying database: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_documents()

