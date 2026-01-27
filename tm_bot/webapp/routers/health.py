"""
Health check and media serving endpoints.
"""

import os
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from ..dependencies import get_current_user

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "zana-webapp"}


@router.get("/api/media/avatars/{user_id}")
async def get_user_avatar(
    request: Request,
    user_id: str,
    current_user_id: int = Depends(get_current_user),
):
    """
    Serve user avatar image.
    
    Args:
        user_id: User ID (string)
    
    Returns:
        Avatar image file or 404 if not found/not visible (auth required)
    """
    try:
        root_dir = request.app.state.root_dir
        if not root_dir:
            raise HTTPException(status_code=500, detail="Server configuration error: root_dir not set")

        # IMPORTANT: Use Postgres-backed DB (not legacy SQLite)
        from db.postgres_db import get_db_session
        from sqlalchemy import text

        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT avatar_path, avatar_visibility
                    FROM users
                    WHERE user_id = :user_id
                    LIMIT 1;
                """),
                {"user_id": str(user_id)},
            ).mappings().fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        # Check visibility (default to 'public' if not set)
        visibility = row.get("avatar_visibility") or "public"
        if visibility != "public":
            raise HTTPException(status_code=403, detail="Avatar is private")

        avatar_path = row.get("avatar_path")
        
        # If avatar_path is not in database, try standard location
        if not avatar_path:
            # Try standard avatar location: media/avatars/{user_id}.jpg
            standard_path = os.path.join("media", "avatars", f"{user_id}.jpg")
            full_path = os.path.join(root_dir, standard_path)
            # If file doesn't exist at standard location, return 404
            if not os.path.exists(full_path):
                raise HTTPException(status_code=404, detail="Avatar not found")
        else:
            # Resolve full path from database
            # If path is relative, it's relative to root_dir
            if os.path.isabs(avatar_path):
                full_path = avatar_path
            else:
                full_path = os.path.join(root_dir, avatar_path)
        
        # Normalize path separators
        full_path = os.path.normpath(full_path)
        
        # Security check: ensure path is within root_dir
        root_dir_abs = os.path.abspath(root_dir)
        full_path_abs = os.path.abspath(full_path)
        if not full_path_abs.startswith(root_dir_abs):
            from utils.logger import get_logger
            logger = get_logger(__name__)
            logger.warning(f"Attempted access outside root_dir: {full_path}")
            raise HTTPException(status_code=403, detail="Invalid path")
        
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="Avatar file not found")
        
        # Determine content type from file extension
        content_type = "image/jpeg"  # Default
        if full_path.lower().endswith(".png"):
            content_type = "image/png"
        elif full_path.lower().endswith(".gif"):
            content_type = "image/gif"
        
        return FileResponse(
            full_path,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
            }
        )
            
    except HTTPException:
        raise
    except Exception as e:
        from utils.logger import get_logger
        logger = get_logger(__name__)
        logger.exception(f"Error serving avatar for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to serve avatar: {str(e)}")
