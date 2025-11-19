"""Astra DB Data API helpers."""
import requests
from typing import Dict, List, Optional, Any
from app.config import config


def get_collection_name(tenant_id: str) -> str:
    """Get collection name based on collection mode."""
    from app.config import CollectionMode
    if config.COLLECTION_MODE == CollectionMode.PER_TENANT:
        return f"chunks_{tenant_id}"
    return config.SHARED_COLLECTION_NAME


def astra_find(
    collection: str,
    filter_dict: Dict,
    sort: Dict,
    options: Optional[Dict] = None,
    role: str = "reader",
    tenant_id: str = None
) -> Dict:
    """
    Execute a find query against Astra DB Data API.
    
    Args:
        collection: Collection name
        filter_dict: Filter criteria (ACL filter)
        sort: Sort criteria (e.g., {"$vectorize": "question"})
        options: Additional options (limit, etc.)
        role: Token role ("reader" or "writer")
        tenant_id: Tenant ID for token selection
    
    Returns:
        Response JSON from Data API
    """
    if tenant_id is None:
        raise ValueError("tenant_id is required for token selection")
    
    token = config.get_token(tenant_id, role)
    if not token:
        raise ValueError(f"No {role} token found for tenant {tenant_id}")
    
    base_url = config.get_astra_base_url()
    url = f"{base_url}/{collection}"
    
    # Build find command
    # According to Astra DB Data API, limit should be inside an "options" object
    find_cmd = {
        "find": {
            "filter": filter_dict,
            "sort": sort
        }
    }
    
    # Add options if provided (limit, projection, etc. go inside "options")
    if options:
        find_cmd["find"]["options"] = options
    
    headers = {
        "X-Cassandra-Token": token,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            url,
            json=find_cmd,
            headers=headers,
            timeout=30
        )
        result = response.json()
        
        # Check for embedding service not configured error
        if response.status_code == 200 and "errors" in result:
            errors = result.get("errors", [])
            embedding_error = any(
                err.get("errorCode") == "EMBEDDING_SERVICE_NOT_CONFIGURED" 
                for err in errors
            )
            if embedding_error:
                # Fall back to query without vectorization
                find_cmd_no_vector = {
                    "find": {
                        "filter": filter_dict,
                        "options": options or {}
                    }
                }
                # Remove sort if it contains $vectorize
                if "$vectorize" in str(sort):
                    # Try again without vectorization
                    response = requests.post(
                        url,
                        json=find_cmd_no_vector,
                        headers=headers,
                        timeout=30
                    )
                    result = response.json()
                    # If still has errors, log but continue
                    if "errors" in result and result["errors"]:
                        # Check if it's still an embedding error or a different issue
                        non_embedding_errors = [
                            e for e in result["errors"]
                            if e.get("errorCode") != "EMBEDDING_SERVICE_NOT_CONFIGURED"
                        ]
                        if non_embedding_errors:
                            # There are other errors, but we'll still try to return what we can
                            pass
        
        # Don't raise on 200 status even if there are errors in the response
        # The application layer will handle empty results
        if response.status_code != 200:
            response.raise_for_status()
        return result
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Astra DB find failed: {e}")


def astra_insert(
    collection: str,
    doc: Dict,
    role: str = "writer",
    tenant_id: str = None
) -> Dict:
    """
    Insert a document into Astra DB Data API.
    
    Args:
        collection: Collection name
        doc: Document to insert
        role: Token role ("reader" or "writer")
        tenant_id: Tenant ID for token selection
    
    Returns:
        Response JSON from Data API
    """
    if tenant_id is None:
        raise ValueError("tenant_id is required for token selection")
    
    token = config.get_token(tenant_id, role)
    if not token:
        raise ValueError(f"No {role} token found for tenant {tenant_id}")
    
    base_url = config.get_astra_base_url()
    url = f"{base_url}/{collection}"
    
    # Wrap document in insertOne command
    insert_cmd = {
        "insertOne": {
            "document": doc
        }
    }
    
    headers = {
        "X-Cassandra-Token": token,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            url,
            json=insert_cmd,
            headers=headers,
            timeout=30
        )
        result = response.json()
        
        # Check for collection not exist error
        if response.status_code == 200 and "errors" in result:
            errors = result.get("errors", [])
            collection_error = any(
                err.get("errorCode") == "COLLECTION_NOT_EXIST" 
                for err in errors
            )
            if collection_error:
                raise RuntimeError(
                    f"Collection '{collection}' does not exist. "
                    f"Please create it in the Astra DB UI or use the Data API createCollection command."
                )
            
            # Check for embedding service not configured error
            # If this happens, retry without $vectorize to allow degraded mode operation
            embedding_error = any(
                err.get("errorCode") == "EMBEDDING_SERVICE_NOT_CONFIGURED"
                for err in errors
            )
            if embedding_error:
                # Remove $vectorize and retry insert (allows system to work without embedding service)
                if "$vectorize" in doc:
                    doc_without_vectorize = {k: v for k, v in doc.items() if k != "$vectorize"}
                    # Retry insert without $vectorize
                    insert_cmd_retry = {
                        "insertOne": {
                            "document": doc_without_vectorize
                        }
                    }
                    retry_response = requests.post(
                        url,
                        json=insert_cmd_retry,
                        headers=headers,
                        timeout=30
                    )
                    retry_result = retry_response.json()
                    
                    # Check if retry was successful
                    if retry_response.status_code == 200 and "errors" not in retry_result:
                        # Successfully inserted without $vectorize
                        # Return a warning in the result
                        retry_result["_warning"] = "Document inserted without $vectorize (embedding service not configured). Vector search will not work until embedding service is configured."
                        return retry_result
                    else:
                        # Retry also failed, raise original error
                        raise RuntimeError(
                            f"Embedding service not configured for collection '{collection}'. "
                            f"Documents with $vectorize cannot be inserted. "
                            f"Please configure the embedding service in Astra DB UI to enable vector search."
                        )
        
        response.raise_for_status()
        return result
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Astra DB insert failed: {e}")

