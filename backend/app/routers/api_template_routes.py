# backend/app/routers/api_templates.py
# FIXED FOR ASYNCSESSION - SQLAlchemy 2.0 async syntax

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import logging

from app.database import get_db
from app.models import APITemplate

# Setup logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/api-templates", tags=["api-templates"])


@router.get("/")
async def list_api_templates(
    provider: Optional[str] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    List all public API templates.
    Uses SQLAlchemy 2.0 async syntax with select().
    """
    logger.info(f"Fetching API templates - provider: {provider}, category: {category}")
    
    try:
        # Build query using select() instead of .query()
        stmt = select(APITemplate).filter(APITemplate.is_public == True)
        
        if provider:
            stmt = stmt.filter(APITemplate.provider == provider)
        if category:
            stmt = stmt.filter(APITemplate.category == category)
        
        # Execute query (MUST use await with async session)
        result = await db.execute(stmt)
        templates = result.scalars().all()
        
        logger.info(f"Found {len(templates)} templates")
        
        if not templates:
            logger.warning("No templates found in database")
            return []
        
        # Convert to dicts
        response = []
        for idx, t in enumerate(templates):
            try:
                # Get optional_variables (could be list or dict)
                opt_vars = t.optional_variables if t.optional_variables is not None else []
                
                # If it's a dict, convert to list of keys
                if isinstance(opt_vars, dict):
                    logger.info(f"Template {t.name}: Converting optional_variables from dict to list")
                    opt_vars = list(opt_vars.keys())
                
                # Get required_variables
                req_vars = t.required_variables if t.required_variables is not None else []
                if isinstance(req_vars, dict):
                    req_vars = list(req_vars.keys())
                
                # Handle updated_at
                updated_at = t.updated_at if t.updated_at else t.created_at
                
                # Build response dict
                template_dict = {
                    "id": str(t.id),
                    "name": t.name,
                    "provider": t.provider,
                    "category": t.category or "leads",
                    "description": t.description or "",
                    "http_config": t.http_config or {},
                    "required_variables": req_vars,
                    "optional_variables": opt_vars,
                    "default_field_mappings": t.default_field_mappings or {},
                    "setup_instructions": t.setup_instructions or "",
                    "is_public": t.is_public,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": updated_at.isoformat() if updated_at else None,
                }
                
                response.append(template_dict)
                logger.debug(f"Processed template {idx + 1}/{len(templates)}: {t.name}")
                
            except Exception as e:
                logger.error(f"Error processing template {t.name}: {str(e)}")
                # Continue with other templates
                continue
        
        logger.info(f"Returning {len(response)} templates")
        return response
    
    except Exception as e:
        logger.error(f"Error fetching API templates: {str(e)}", exc_info=True)
        # Return empty array instead of crashing
        return []


@router.get("/{template_id}")
async def get_api_template(
    template_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get single API template by ID"""
    logger.info(f"Fetching API template: {template_id}")
    
    try:
        # Use select() with async session
        stmt = select(APITemplate).filter(APITemplate.id == template_id)
        result = await db.execute(stmt)
        template = result.scalar_one_or_none()
        
        if not template:
            logger.warning(f"Template not found: {template_id}")
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Same transformation as list
        opt_vars = template.optional_variables if template.optional_variables is not None else []
        if isinstance(opt_vars, dict):
            opt_vars = list(opt_vars.keys())
        
        req_vars = template.required_variables if template.required_variables is not None else []
        if isinstance(req_vars, dict):
            req_vars = list(req_vars.keys())
        
        updated_at = template.updated_at if template.updated_at else template.created_at
        
        return {
            "id": str(template.id),
            "name": template.name,
            "provider": template.provider,
            "category": template.category or "leads",
            "description": template.description or "",
            "http_config": template.http_config or {},
            "required_variables": req_vars,
            "optional_variables": opt_vars,
            "default_field_mappings": template.default_field_mappings or {},
            "setup_instructions": template.setup_instructions or "",
            "is_public": template.is_public,
            "created_at": template.created_at.isoformat() if template.created_at else None,
            "updated_at": updated_at.isoformat() if updated_at else None,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching template {template_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/raw")
async def debug_raw_templates(db: AsyncSession = Depends(get_db)):
    """
    Debug endpoint to see raw template data.
    Remove in production!
    """
    stmt = select(APITemplate)
    result = await db.execute(stmt)
    templates = result.scalars().all()
    
    return {
        "total": len(templates),
        "templates": [
            {
                "id": str(t.id),
                "name": t.name,
                "provider": t.provider,
                "is_public": t.is_public,
                "optional_vars_type": type(t.optional_variables).__name__,
                "optional_vars_raw": t.optional_variables,
                "has_updated_at": t.updated_at is not None,
            }
            for t in templates
        ]
    }