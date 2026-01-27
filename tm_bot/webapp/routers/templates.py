"""
Template-related endpoints.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from ..dependencies import get_current_user
from ..schemas import SubscribeTemplateRequest
from repositories.templates_repo import TemplatesRepository
from repositories.instances_repo import InstancesRepository
from repositories.settings_repo import SettingsRepository
from services.template_unlocks import TemplateUnlocksService
from db.postgres_db import get_db_session
from sqlalchemy import text
from utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["templates"])
logger = get_logger(__name__)


@router.get("/templates")
async def list_templates(
    request: Request,
    category: Optional[str] = Query(None, description="Filter by category"),
    program_key: Optional[str] = Query(None, description="Filter by program key"),
    user_id: int = Depends(get_current_user)
):
    """List templates with unlock status."""
    try:
        templates_repo = TemplatesRepository(request.app.state.root_dir)
        unlocks_service = TemplateUnlocksService(request.app.state.root_dir)
        
        templates = templates_repo.list_templates(category=category, program_key=program_key, is_active=True)
        templates_with_status = unlocks_service.annotate_templates_with_unlock_status(user_id, templates)
        
        return {"templates": templates_with_status}
    except Exception as e:
        logger.exception(f"Error listing templates: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}")


@router.get("/templates/{template_id}")
async def get_template(
    request: Request,
    template_id: str,
    user_id: int = Depends(get_current_user)
):
    """Get template details (simplified schema)."""
    try:
        templates_repo = TemplatesRepository(request.app.state.root_dir)
        
        template = templates_repo.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # All templates are now unlocked (simplified schema)
        return {
            **template,
            "unlocked": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting template: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")


@router.get("/templates/{template_id}/users")
async def get_template_users(
    request: Request,
    template_id: str,
    limit: int = Query(8, ge=1, le=20),
    user_id: int = Depends(get_current_user)
):
    """Get users using this template (for 'used by' badges)."""
    try:
        templates_repo = TemplatesRepository(request.app.state.root_dir)
        
        # Verify template exists
        template = templates_repo.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Get users with active instances for this template
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT DISTINCT i.user_id, u.first_name, u.username, u.avatar_path, u.avatar_file_unique_id
                    FROM promise_instances i
                    JOIN users u ON i.user_id = u.user_id
                    WHERE i.template_id = :template_id
                      AND i.status = 'active'
                    ORDER BY i.created_at_utc DESC
                    LIMIT :limit
                """),
                {"template_id": template_id, "limit": limit}
            ).fetchall()
        
        users = []
        for row in rows:
            users.append({
                "user_id": row[0],
                "first_name": row[1],
                "username": row[2],
                "avatar_path": row[3],
                "avatar_file_unique_id": row[4]
            })
        
        return {"users": users, "total": len(users)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting template users: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get template users: {str(e)}")


@router.post("/templates/{template_id}/subscribe")
async def subscribe_template(
    request: Request,
    template_id: str,
    subscribe_request: Optional[SubscribeTemplateRequest] = None,
    user_id: int = Depends(get_current_user)
):
    """Subscribe to a template (creates promise + instance)."""
    try:
        from datetime import date as date_type
        try:
            from dateutil.parser import parse as parse_date
        except ImportError:
            # Fallback to datetime.fromisoformat
            def parse_date(s: str) -> date_type:
                return date_type.fromisoformat(s.split('T')[0])
        
        instances_repo = InstancesRepository(request.app.state.root_dir)
        unlocks_service = TemplateUnlocksService(request.app.state.root_dir)
        
        # Check if template is unlocked
        unlock_status = unlocks_service.get_unlock_status(user_id, template_id)
        if not unlock_status["unlocked"]:
            raise HTTPException(
                status_code=403,
                detail=f"Template is locked: {unlock_status['lock_reason']}"
            )
        
        # Parse dates
        start_date = None
        target_date = None
        target_value_override = None
        if subscribe_request:
            if subscribe_request.start_date:
                start_date = parse_date(subscribe_request.start_date).date()
            if subscribe_request.target_date:
                target_date = parse_date(subscribe_request.target_date).date()
            if subscribe_request.target_value is not None:
                target_value_override = float(subscribe_request.target_value)
        
        result = instances_repo.subscribe_template(user_id, template_id, start_date, target_date, target_value_override)
        
        return {"status": "success", **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error subscribing to template: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to subscribe: {str(e)}")


@router.get("/instances/active")
async def list_active_instances(
    request: Request,
    user_id: int = Depends(get_current_user)
):
    """List active template instances for the user."""
    try:
        instances_repo = InstancesRepository(request.app.state.root_dir)
        instances = instances_repo.list_active_instances(user_id)
        return {"instances": instances}
    except Exception as e:
        logger.exception(f"Error listing instances: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list instances: {str(e)}")
