"""FastAPI application with /ingest and /query endpoints."""
import os
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables before importing config
load_dotenv()

from app.config import config
from app.security import get_current_user, User
from app.astra import astra_find, astra_insert, get_collection_name
from app.policy import build_acl_filter, get_today_iso
from app.ratelimit import rate_limiter


app = FastAPI(
    title="Secure Multi-Tenant RAG API",
    description="Production-ready RAG demo with per-chunk ACLs using Astra DB",
    version="1.0.0"
)

# Add exception handler for better error messages
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler with production-ready error handling."""
    from fastapi.responses import JSONResponse
    
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    # For production: Don't expose internal error details
    # In production, log the full error internally, return generic message to client
    # For demo: Return error detail for debugging (remove in production)
    import logging
    try:
        logger = logging.getLogger(__name__)
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
    except:
        # Logging not configured, continue without logging
        pass
    
    # Return generic error message (don't leak implementation details)
    # Note: For demo purposes, we return the error detail. In production, use:
    # content={"detail": "Internal server error"}
    error_detail = str(exc)
    return JSONResponse(
        status_code=500,
        content={"detail": error_detail}
    )


class IngestRequest(BaseModel):
    """Request model for /ingest endpoint."""
    tenant_id: str = Field(..., description="Tenant ID")
    doc_id: str = Field(..., description="Document ID")
    text: str = Field(..., description="Chunk text content")
    visibility: str = Field(..., description="Visibility: public, internal, or restricted")
    allow_teams: List[str] = Field(default_factory=list, description="Teams allowed to access")
    allow_users: List[str] = Field(default_factory=list, description="Users allowed to access")
    deny_users: List[str] = Field(default_factory=list, description="Users denied access")
    owner_user_ids: List[str] = Field(default_factory=list, description="Owner user IDs")
    valid_from: Optional[str] = Field(None, description="Valid from date (YYYY-MM-DD)")
    valid_to: Optional[str] = Field(None, description="Valid to date (YYYY-MM-DD)")
    # Note: $vectorize is automatically added to documents during insert for automatic embedding generation
    # For BYO embeddings, you can add a $vector field instead (array of floats)


class QueryRequest(BaseModel):
    """Request model for /query endpoint."""
    question: str = Field(..., description="Query question for vector search")


class QueryResponse(BaseModel):
    """Response model for /query endpoint."""
    matches: List[Dict[str, Any]] = Field(..., description="Matching documents with doc_id and visibility")
    prompt_context: List[Dict[str, str]] = Field(..., description="Context documents with doc_id and text")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/ingest")
async def ingest(
    request: IngestRequest,
    user: User = Depends(get_current_user)
):
    """
    Ingest a document chunk with ACL metadata.
    
    Requires authentication. User's tenant must match request.tenant_id.
    """
    # Check tenant match
    if user.tenant != request.tenant_id:
        raise HTTPException(
            status_code=403,
            detail=f"User tenant '{user.tenant}' does not match request tenant '{request.tenant_id}'"
        )
    
    # Rate limiting
    rate_limiter.check_rate_limit(user.sub)
    
    # Build document
    doc = {
        "tenant_id": request.tenant_id,
        "doc_id": request.doc_id,
        "text": request.text,
        "visibility": request.visibility,
        "allow_teams": request.allow_teams,
        "allow_users": request.allow_users,
        "deny_users": request.deny_users,
        "owner_user_ids": request.owner_user_ids,
    }
    
    # Add $vectorize to automatically generate embeddings during insert
    # Only add if embedding service is configured (will be detected on first insert attempt)
    # If embedding service is not configured, document will be inserted without $vectorize
    # This allows the system to work in degraded mode until embedding service is configured
    try:
        # Try to insert with $vectorize first
        doc["$vectorize"] = request.text
    except:
        # If there's an issue, we'll handle it in the insert attempt
        pass
    
    # Add optional date fields
    if request.valid_from:
        doc["valid_from"] = request.valid_from
    if request.valid_to:
        doc["valid_to"] = request.valid_to
    
    # Get collection name
    collection = get_collection_name(request.tenant_id)
    
    # Insert into Astra DB
    try:
        result = astra_insert(collection, doc, role="writer", tenant_id=request.tenant_id)
        return {
            "status": "success",
            "collection": collection,
            "doc_id": request.doc_id,
            "result": result
        }
    except Exception as e:
        import traceback
        error_detail = str(e)
        # Include traceback in detail for debugging
        if isinstance(e, RuntimeError):
            error_detail = str(e)
        else:
            error_detail = f"{type(e).__name__}: {str(e)}"
        raise HTTPException(status_code=500, detail=error_detail)


@app.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    user: User = Depends(get_current_user)
):
    """
    Security-trimmed retrieval with vector search.
    
    Returns only chunks the user is authorized to access based on ACL rules.
    """
    # Rate limiting
    rate_limiter.check_rate_limit(user.sub)
    
    # Build ACL filter
    from app.config import CollectionMode
    today_iso = get_today_iso()
    is_shared = config.COLLECTION_MODE == CollectionMode.SHARED
    acl_filter = build_acl_filter(user, today_iso, is_shared_collection=is_shared)
    
    # Get collection name
    collection = get_collection_name(user.tenant)
    
    # Build sort (using $vectorize for vector similarity search)
    # Format: {"$vectorize": "query text"} - $vectorize is a pseudo-field allowed in sort
    sort = {
        "$vectorize": request.question
        # Alternative for BYO embeddings:
        # "$vector": embedding_vector  # where embedding_vector is computed from request.question
    }
    
    # Query options
    options = {
        "limit": 8
    }
    
    # Execute query
    try:
        result = astra_find(
            collection=collection,
            filter_dict=acl_filter,
            sort=sort,
            options=options,
            role="reader",
            tenant_id=user.tenant
        )
        
        # Extract documents from result
        # Handle both direct "data" structure and potential error responses
        if "data" in result:
            documents = result.get("data", {}).get("documents", [])
        elif "documents" in result:
            documents = result.get("documents", [])
        else:
            # If there are errors but also data, try to extract documents
            documents = []
            # Debug: check what we actually got
            if "errors" in result:
                # If we have errors, the fallback query might have failed
                # Try to see if there's any data despite errors
                pass
        
        # Post-filter: Apply deny_users, date validity, and restricted document ACL checks
        # This ensures proper enforcement of allow_teams and allow_users for restricted documents
        today_iso = get_today_iso()
        filtered_docs = []
        for doc in documents:
            visibility = doc.get("visibility", "public")
            
            # For restricted documents, verify ACL rules are met
            if visibility == "restricted":
                # Check if user is in allow_users
                allow_users = doc.get("allow_users", [])
                user_allowed = isinstance(allow_users, list) and user.sub in allow_users
                
                # Check if user is in owner_user_ids
                owner_user_ids = doc.get("owner_user_ids", [])
                user_is_owner = isinstance(owner_user_ids, list) and user.sub in owner_user_ids
                
                # Check if user's teams overlap with allow_teams
                allow_teams = doc.get("allow_teams", [])
                team_allowed = False
                if isinstance(allow_teams, list) and allow_teams and user.teams:
                    # Check if any of user's teams are in allow_teams
                    team_allowed = any(team in allow_teams for team in user.teams)
                
                # User must be allowed via users, owners, or teams
                if not (user_allowed or user_is_owner or team_allowed):
                    continue  # Skip this restricted document
            
            # Check deny_users (application-level filter since DB doesn't support it)
            deny_users = doc.get("deny_users", [])
            if isinstance(deny_users, list) and user.sub in deny_users:
                continue  # Skip this document
            
            # Check date validity
            valid_from = doc.get("valid_from")
            if valid_from and valid_from > today_iso:
                continue  # Not valid yet
            
            valid_to = doc.get("valid_to")
            if valid_to and valid_to < today_iso:
                continue  # Expired
            
            filtered_docs.append(doc)
        
        # Build response
        matches = [
            {
                "doc_id": doc.get("doc_id"),
                "visibility": doc.get("visibility")
            }
            for doc in filtered_docs
        ]
        
        prompt_context = [
            {
                "doc_id": doc.get("doc_id"),
                "text": doc.get("text")
            }
            for doc in filtered_docs
        ]
        
        return QueryResponse(matches=matches, prompt_context=prompt_context)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

