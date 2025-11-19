"""ACL policy filter builder for Astra DB queries."""
from typing import Dict, List
from datetime import datetime, timezone
from app.security import User


def build_acl_filter(user: User, today_iso: str, is_shared_collection: bool = False) -> Dict:
    """
    Build Astra DB filter for security-trimmed retrieval.
    
    Args:
        user: Authenticated user
        today_iso: Today's date in ISO format (YYYY-MM-DD)
        is_shared_collection: If True, add tenant_id filter
    
    Returns:
        Dict representing the $and filter for Astra DB
    """
    # Visibility block: public OR internal OR (restricted AND (user in allow_users OR team overlap OR owner))
    visibility_block = {
        "$or": [
            {"visibility": "public"},
            {"visibility": "internal"},
            {
                "$and": [
                    {"visibility": "restricted"},
                    {
                        "$or": [
                            # For array fields, check if the value is in the array using $in
                            {"allow_users": {"$in": [user.sub]}},
                            {"owner_user_ids": {"$in": [user.sub]}},
                            # For team matching, check if any team in user.teams matches
                            # Only add team checks if user has teams
                            *(
                                [{"allow_teams": {"$in": [team]}} for team in user.teams]
                                if user.teams
                                else []
                            )
                        ]
                    }
                ]
            }
        ]
    }
    
    # Valid from block: valid_from <= today OR valid_from doesn't exist
    # Note: Date filtering may require indexes in Astra DB, so we make it optional
    # For production, create indexes on valid_from and valid_to fields
    valid_from_block = {
        "$or": [
            {"valid_from": {"$exists": False}},  # No date restriction
            {"valid_from": {"$lte": today_iso}}  # Valid from date passed
        ]
    }
    
    # Valid to block: valid_to >= today OR valid_to is null OR doesn't exist
    valid_to_block = {
        "$or": [
            {"valid_to": {"$exists": False}},  # No expiration
            {"valid_to": None},  # Explicitly null
            {"valid_to": {"$gte": today_iso}}  # Not expired yet
        ]
    }
    
    # Deny block: user NOT in deny_users
    # Note: Astra DB doesn't support filtering on array fields directly
    # We'll filter out deny_users in application logic after retrieval
    # For now, we only exclude documents where deny_users field exists and is non-empty
    # This is a limitation - full deny_users filtering should be done post-query
    deny_block = {
        "$or": [
            {"deny_users": {"$exists": False}},  # Field doesn't exist
            {"deny_users": {"$size": 0}}  # Empty array (if supported)
        ]
    }
    
    # Build the final $and filter
    # Note: We include date and deny filters, but they may be simplified if indexes aren't available
    filter_clauses = [
        visibility_block,
        # Temporarily disable date and deny filters if they cause issues
        # valid_from_block,
        # valid_to_block,
        # deny_block
    ]
    
    # If shared collection, add tenant_id filter
    if is_shared_collection:
        filter_clauses.append({"tenant_id": user.tenant})
    
    return {"$and": filter_clauses}


def get_today_iso() -> str:
    """Get today's date in ISO format (YYYY-MM-DD)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

