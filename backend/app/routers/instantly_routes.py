"""API routes for Instantly.ai export - Official v2 implementation."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
import logging

from app.database import get_db
from app.models import Lead, User
from app.rbac import require_export_leads
from app.services.instantly_service import get_instantly_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/instantly", tags=["instantly"])


# Request/Response Models
class TestConnectionRequest(BaseModel):
    """Request to test Instantly.ai connection."""
    api_key: Optional[str] = Field(None, description="Instantly.ai API key (Bearer token). If not provided, uses INSTANTLY_API_KEY from .env")


class CampaignResponse(BaseModel):
    """Campaign information."""
    id: str
    name: str
    status: Optional[int] = None  # 1=ACTIVE, 2=PAUSED, 3=COMPLETED, 4=DRAFTED
    daily_limit: Optional[int] = None
    timestamp_created: Optional[str] = None


class ExportRequest(BaseModel):
    """Request to export leads to Instantly.ai."""
    api_key: Optional[str] = Field(None, description="Instantly.ai API key. If not provided, uses INSTANTLY_API_KEY from .env")
    campaign_id: str = Field(..., description="Target campaign UUID")
    lead_ids: List[str] = Field(..., description="List of lead IDs to export")
    skip_if_in_workspace: bool = Field(default=True, description="Skip duplicate emails")


class ExportResult(BaseModel):
    """Result of export operation."""
    success: bool
    total: int
    added: Optional[int] = 0
    skipped: Optional[int] = 0
    failed: Optional[int] = 0
    job_id: Optional[str] = None
    status: Optional[str] = None
    message: str
    errors: Optional[List[str]] = None


class JobStatusResponse(BaseModel):
    """Background job status."""
    success: bool
    status: Optional[str] = None  # pending, completed, failed
    progress: Optional[Dict] = None
    result: Optional[Dict] = None


# Routes
@router.post("/test-connection")
async def test_connection(
    request: TestConnectionRequest,
    current_user: User = Depends(require_export_leads),
) -> Dict[str, Any]:
    """
    Test connection to Instantly.ai API.
    
    **Required Permission:** EXPORT_LEADS
    **Roles:** Admin, Reviewer
    """
    try:
        service = get_instantly_service(request.api_key)
        result = await service.test_connection()
        
        if result["success"]:
            return {
                "success": True,
                "message": "Connection successful",
                "workspace": result.get("workspace", {})
            }
        else:
            return {
                "success": False,
                "message": result.get("error", "Connection failed")
            }
    
    except Exception as e:
        logger.error(f"Connection test error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test failed: {str(e)}"
        )


@router.get("/campaigns")
async def list_campaigns(
    api_key: Optional[str] = Query(None, description="Instantly.ai API key. If not provided, uses INSTANTLY_API_KEY from .env"),
    campaign_status: Optional[str] = Query(None, description="Filter by status (ACTIVE, PAUSED, etc)"),
    limit: int = Query(50, ge=1, le=100, description="Number of campaigns to return"),
    current_user: User = Depends(require_export_leads),
) -> List[CampaignResponse]:
    """
    Get list of campaigns from Instantly.ai.
    
    **Required Permission:** EXPORT_LEADS
    **Roles:** Admin, Reviewer
    """
    try:
        service = get_instantly_service(api_key)
        result = await service.list_campaigns(status=campaign_status, limit=limit)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to fetch campaigns")
            )
        
        campaigns = result.get("campaigns", [])
        
        return [
            CampaignResponse(
                id=campaign.get("id", ""),
                name=campaign.get("name", "Unknown"),
                status=campaign.get("status"),
                daily_limit=campaign.get("daily_limit"),
                timestamp_created=campaign.get("timestamp_created")
            )
            for campaign in campaigns
        ]
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching campaigns: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch campaigns: {str(e)}"
        )


@router.post("/export", response_model=ExportResult)
async def export_leads(
    request: ExportRequest,
    current_user: User = Depends(require_export_leads),
    db: AsyncSession = Depends(get_db),
) -> ExportResult:
    """
    Export leads to Instantly.ai campaign.
    
    **Required Permission:** EXPORT_LEADS
    **Roles:** Admin, Reviewer
    
    Note: This returns a background job ID. Poll /instantly/job/{job_id} for status.
    """
    
    # Validate request
    if not request.lead_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No leads selected for export"
        )
    
    if len(request.lead_ids) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot export more than 500 leads at once"
        )
    
    try:
        # Fetch leads from database
        lead_uuids = [UUID(lead_id) for lead_id in request.lead_ids]
        
        result = await db.execute(
            select(Lead).where(
                and_(
                    Lead.tenant_id == current_user.tenant_id,
                    Lead.id.in_(lead_uuids)
                )
            )
        )
        leads = result.scalars().all()
        
        if not leads:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No leads found with provided IDs"
            )
        
        # Export to Instantly.ai
        service = get_instantly_service(request.api_key)
        export_result = await service.add_leads_to_campaign(
            campaign_id=request.campaign_id,
            leads=leads,
            skip_if_in_workspace=request.skip_if_in_workspace
        )
        
        if not export_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=export_result.get("error", "Export failed")
            )
        
        # Update exported_at timestamp
        await db.execute(
            update(Lead)
            .where(Lead.id.in_(lead_uuids))
            .values(
                exported_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        )
        await db.commit()
        
        logger.info(
            f"Exported {len(leads)} leads to Instantly.ai "
            f"campaign {request.campaign_id} by {current_user.email}. "
            f"Added: {export_result.get('added')}, "
            f"Skipped: {export_result.get('skipped')}, "
            f"Failed: {export_result.get('failed')}"
        )
        
        return ExportResult(
            success=True,
            total=export_result["total"],
            added=export_result.get("added", 0),
            skipped=export_result.get("skipped", 0),
            failed=export_result.get("failed", 0),
            job_id=export_result.get("job_id"),
            status=export_result.get("status"),
            message=export_result.get("message", "Export completed successfully"),
            errors=export_result.get("errors")
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@router.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    api_key: str = Query(..., description="Instantly.ai API key"),
    current_user: User = Depends(require_export_leads),
) -> JobStatusResponse:
    """
    Get status of a background job (like lead import).
    
    **Required Permission:** EXPORT_LEADS
    **Roles:** Admin, Reviewer
    
    Status values:
    - pending: Job is processing
    - completed: Job finished successfully
    - failed: Job failed
    """
    try:
        service = get_instantly_service(api_key)
        result = await service.get_background_job_status(job_id)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to get job status")
            )
        
        return JobStatusResponse(
            success=True,
            status=result.get("status"),
            progress=result.get("progress"),
            result=result.get("result")
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}"
        )


@router.get("/campaign/{campaign_id}/analytics")
async def get_campaign_analytics(
    campaign_id: str,
    api_key: str = Query(..., description="Instantly.ai API key"),
    current_user: User = Depends(require_export_leads),
) -> Dict[str, Any]:
    """
    Get analytics for a specific campaign.
    
    **Required Permission:** EXPORT_LEADS
    **Roles:** Admin, Reviewer
    """
    try:
        service = get_instantly_service(api_key)
        result = await service.get_campaign_analytics(campaign_id=campaign_id)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to fetch analytics")
            )
        
        return result["analytics"]
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch analytics: {str(e)}"
        )


@router.post("/campaign/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    api_key: str = Query(..., description="Instantly.ai API key"),
    current_user: User = Depends(require_export_leads),
) -> Dict[str, Any]:
    """
    Pause a campaign.
    
    **Required Permission:** EXPORT_LEADS
    **Roles:** Admin, Reviewer
    """
    try:
        service = get_instantly_service(api_key)
        result = await service.pause_campaign(campaign_id)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to pause campaign")
            )
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing campaign: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause campaign: {str(e)}"
        )


@router.post("/campaign/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: str,
    api_key: str = Query(..., description="Instantly.ai API key"),
    current_user: User = Depends(require_export_leads),
) -> Dict[str, Any]:
    """
    Activate a campaign.
    
    **Required Permission:** EXPORT_LEADS
    **Roles:** Admin, Reviewer
    """
    try:
        service = get_instantly_service(api_key)
        result = await service.activate_campaign(campaign_id)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Failed to activate campaign")
            )
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating campaign: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate campaign: {str(e)}"
        )


@router.get("/exported-leads")
async def get_exported_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_export_leads),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get list of exported leads.
    
    **Required Permission:** EXPORT_LEADS
    **Roles:** Admin, Reviewer
    """
    try:
        # Count total exported leads
        count_result = await db.execute(
            select(Lead).where(
                and_(
                    Lead.tenant_id == current_user.tenant_id,
                    Lead.exported_at.isnot(None)
                )
            )
        )
        total = len(count_result.scalars().all())
        
        # Get paginated results
        result = await db.execute(
            select(Lead)
            .where(
                and_(
                    Lead.tenant_id == current_user.tenant_id,
                    Lead.exported_at.isnot(None)
                )
            )
            .order_by(Lead.exported_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        leads = result.scalars().all()
        
        return {
            "leads": [
                {
                    "id": str(lead.id),
                    "email": lead.email,
                    "first_name": lead.first_name,
                    "last_name": lead.last_name,
                    "company_name": lead.company_name,
                    "status": lead.status,
                    "fit_score": lead.fit_score,
                    "exported_at": lead.exported_at,
                }
                for lead in leads
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    
    except Exception as e:
        logger.error(f"Error fetching exported leads: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch exported leads: {str(e)}"
        )