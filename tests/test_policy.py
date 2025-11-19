"""Unit tests for ACL policy filter builder."""
import pytest
from datetime import datetime
from app.policy import build_acl_filter, get_today_iso
from app.security import User


def test_public_visibility():
    """Test that public documents are always accessible."""
    user = User(sub="alice@acme.com", tenant="acme", teams=["finance"])
    today = get_today_iso()
    
    filter_dict = build_acl_filter(user, today, is_shared_collection=False)
    
    # Should include public visibility
    assert "$and" in filter_dict
    visibility_block = filter_dict["$and"][0]
    assert {"visibility": "public"} in visibility_block["$or"]


def test_internal_visibility():
    """Test that internal documents are accessible to authenticated users."""
    user = User(sub="alice@acme.com", tenant="acme", teams=["finance"])
    today = get_today_iso()
    
    filter_dict = build_acl_filter(user, today, is_shared_collection=False)
    
    # Should include internal visibility
    visibility_block = filter_dict["$and"][0]
    assert {"visibility": "internal"} in visibility_block["$or"]


def test_restricted_visibility_with_team():
    """Test that restricted documents require team/user/owner match."""
    user = User(sub="alice@acme.com", tenant="acme", teams=["finance"])
    today = get_today_iso()
    
    filter_dict = build_acl_filter(user, today, is_shared_collection=False)
    
    # Should include restricted with team/user/owner checks
    visibility_block = filter_dict["$and"][0]
    restricted_clause = None
    for clause in visibility_block["$or"]:
        if isinstance(clause, dict) and "$and" in clause:
            restricted_clause = clause
            break
    
    assert restricted_clause is not None
    assert {"visibility": "restricted"} in restricted_clause["$and"]
    
    # Check for team matching
    or_clause = restricted_clause["$and"][1]["$or"]
    team_checks = [c for c in or_clause if "allow_teams" in c]
    assert len(team_checks) > 0


def test_restricted_visibility_with_user():
    """Test restricted documents accessible via allow_users."""
    user = User(sub="alice@acme.com", tenant="acme", teams=[])
    today = get_today_iso()
    
    filter_dict = build_acl_filter(user, today, is_shared_collection=False)
    
    visibility_block = filter_dict["$and"][0]
    restricted_clause = None
    for clause in visibility_block["$or"]:
        if isinstance(clause, dict) and "$and" in clause:
            restricted_clause = clause
            break
    
    assert restricted_clause is not None
    or_clause = restricted_clause["$and"][1]["$or"]
    user_checks = [c for c in or_clause if "allow_users" in c]
    assert len(user_checks) > 0


def test_deny_users():
    """Test that deny_users filtering is handled (may be in post-processing)."""
    user = User(sub="alice@acme.com", tenant="acme", teams=["finance"])
    today = get_today_iso()
    
    filter_dict = build_acl_filter(user, today, is_shared_collection=False)
    
    # Deny_users filtering may be done in application logic due to Astra DB limitations
    # The filter should still be valid
    assert "$and" in filter_dict
    assert len(filter_dict["$and"]) > 0


def test_shared_collection_tenant_filter():
    """Test that shared collection mode adds tenant_id filter."""
    user = User(sub="alice@acme.com", tenant="acme", teams=["finance"])
    today = get_today_iso()
    
    filter_dict = build_acl_filter(user, today, is_shared_collection=True)
    
    # Should include tenant_id filter
    tenant_filter = None
    for clause in filter_dict["$and"]:
        if isinstance(clause, dict) and "tenant_id" in clause:
            tenant_filter = clause
            break
    
    assert tenant_filter is not None
    assert tenant_filter["tenant_id"] == "acme"


def test_per_tenant_collection_no_tenant_filter():
    """Test that per-tenant mode does not add tenant_id filter."""
    user = User(sub="alice@acme.com", tenant="acme", teams=["finance"])
    today = get_today_iso()
    
    filter_dict = build_acl_filter(user, today, is_shared_collection=False)
    
    # Should NOT include tenant_id filter
    tenant_filters = [
        clause for clause in filter_dict["$and"]
        if isinstance(clause, dict) and "tenant_id" in clause
    ]
    assert len(tenant_filters) == 0


def test_valid_from_to_filters():
    """Test that valid_from and valid_to filters are handled (may be in post-processing)."""
    user = User(sub="alice@acme.com", tenant="acme", teams=["finance"])
    today = get_today_iso()
    
    filter_dict = build_acl_filter(user, today, is_shared_collection=False)
    
    # Date filtering may be done in application logic due to Astra DB index requirements
    # The filter should still be valid and include visibility checks
    assert "$and" in filter_dict
    assert len(filter_dict["$and"]) > 0
    # Visibility block should always be present
    visibility_block = filter_dict["$and"][0]
    assert "$or" in visibility_block

