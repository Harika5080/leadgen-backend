"""Export API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import io
import logging
from datetime import datetime

from app.database import get_db
from app.models import Lead, ExportBatch, Tenant, User
from app.auth import get_current_user
from app.services.export_service import ExportService
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response schemas
class ExportRequest(BaseModel):
    """Request to export leads."""
    lead_ids: List[str]
    platform: str  # 'instantly', 'smartlead', or 'generic'
    format: str = "csv"  # 'csv' or 'api'
    campaign_id: Optional[str] = None
    email_account_id: Optional[str] = None
    columns: Optional[List[str]] = None  # For generic CSV


class ExportResponse(BaseModel):
    """Export operation response."""
    export_id: str
    status: str
    lead_count: int
    platform: str
    download_url: Optional[str] = None
    api_result: Optional[dict] = None


class ExportStatus(BaseModel):
    """Export job status."""
    export_id: str
    status: str
    lead_count: int
    created_at: str
    completed_at: Optional[str] = None
    download_url: Optional[str] = None


@router.post("/export", response_model=ExportResponse)
async def create_export(
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),  # Fixed: User object, not dict
    db: AsyncSession = Depends(get_db)
):
    """
    Export leads to a campaign platform.
    
    Supports:
    - Instantly.ai (CSV or API)
    - Smartlead.ai (CSV or API)
    - Generic CSV export
    """
    tenant_id = current_user.tenant_id  # Fixed: Use dot notation
    
    # Fetch leads
    result = await db.execute(
        select(Lead).where(
            Lead.tenant_id == tenant_id,
            Lead.id.in_(request.lead_ids),
            Lead.lead_status == 'approved'
        )
    )
    leads = result.scalars().all()
    
    if not leads:
        raise HTTPException(
            status_code=404,
            detail="No approved leads found with provided IDs"
        )
    
    # Convert to dictionaries
    lead_dicts = []
    for lead in leads:
        lead_dict = {
            "id": str(lead.id),
            "email": lead.email,
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "phone": lead.phone,
            "job_title": lead.job_title,
            "linkedin_url": lead.linkedin_url,
            "lead_fit_score": float(lead.lead_fit_score) if lead.lead_fit_score else 0,
            "lead_status": lead.lead_status,
            "acquisition_timestamp": lead.acquisition_timestamp.isoformat() if lead.acquisition_timestamp else None,
            "company": {
                "name": lead.company.name if lead.company else "",
                "website": lead.company.website if lead.company else "",
            }
        }
        lead_dicts.append(lead_dict)
    
    # Create export batch record
    export_batch = ExportBatch(
        tenant_id=tenant_id,
        destination=request.platform,
        lead_count=len(lead_dicts),
        status='processing',
        created_by_user_id=current_user.id  # Fixed: Use dot notation
    )
    db.add(export_batch)
    await db.commit()
    await db.refresh(export_batch)
    
    export_id = str(export_batch.id)
    
    # Process export
    if request.format == "api":
        # API export (async)
        if request.platform not in ["instantly", "smartlead"]:
            raise HTTPException(
                status_code=400,
                detail="API export only supported for 'instantly' and 'smartlead'"
            )
        
        # Get tenant's API key for platform (from tenant settings)
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        tenant = tenant_result.scalar_one()
        
        # In production, store platform API keys in tenant.settings
        platform_key = tenant.settings.get(f"{request.platform}_api_key")
        
        if not platform_key:
            raise HTTPException(
                status_code=400,
                detail=f"No API key configured for {request.platform}"
            )
        
        # Export via API (run in background)
        try:
            result = await ExportService.export_to_platform(
                platform=request.platform,
                leads=lead_dicts,
                api_key=platform_key,
                campaign_id=request.campaign_id,
                email_account_id=request.email_account_id
            )
            
            # Update export batch
            export_batch.status = 'completed'
            export_batch.exported_at = datetime.utcnow()
            await db.commit()
            
            # Mark leads as exported
            for lead in leads:
                lead.exported_at = datetime.utcnow()
            await db.commit()
            
            logger.info(f"Export {export_id}: API export to {request.platform} completed")
            
            return ExportResponse(
                export_id=export_id,
                status="completed",
                lead_count=len(lead_dicts),
                platform=request.platform,
                api_result=result
            )
        
        except Exception as e:
            export_batch.status = 'failed'
            await db.commit()
            
            logger.error(f"Export {export_id}: API export failed - {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    else:  # CSV export
        # Generate CSV
        csv_content = ExportService.generate_csv_for_platform(
            platform=request.platform,
            leads=lead_dicts,
            columns=request.columns
        )
        
        # In production, save to S3 and return presigned URL
        # For now, we'll return the CSV directly
        
        export_batch.status = 'completed'
        export_batch.exported_at = datetime.utcnow()
        # export_batch.file_path = s3_path  # In production
        await db.commit()
        
        # Mark leads as exported
        for lead in leads:
            lead.exported_at = datetime.utcnow()
        await db.commit()
        
        logger.info(f"Export {export_id}: CSV export completed - {len(lead_dicts)} leads")
        
        # Return CSV as download
        filename = f"{request.platform}_export_{export_id}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
        
        return StreamingResponse(
            io.StringIO(csv_content),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )


@router.get("/export/{export_id}", response_model=ExportStatus)
async def get_export_status(
    export_id: str,
    current_user: User = Depends(get_current_user),  # Fixed: User object, not dict
    db: AsyncSession = Depends(get_db)
):
    """Get status of an export job."""
    tenant_id = current_user.tenant_id  # Fixed: Use dot notation
    
    result = await db.execute(
        select(ExportBatch).where(
            ExportBatch.id == export_id,
            ExportBatch.tenant_id == tenant_id
        )
    )
    export_batch = result.scalar_one_or_none()
    
    if not export_batch:
        raise HTTPException(status_code=404, detail="Export not found")
    
    return ExportStatus(
        export_id=str(export_batch.id),
        status=export_batch.status,
        lead_count=export_batch.lead_count,
        created_at=export_batch.created_at.isoformat(),
        completed_at=export_batch.exported_at.isoformat() if export_batch.exported_at else None,
        download_url=export_batch.file_path if export_batch.file_path else None
    )


@router.get("/export")
async def list_exports(
    current_user: User = Depends(get_current_user),  # Fixed: User object, not dict
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0
):
    """List export history for tenant."""
    tenant_id = current_user.tenant_id  # Fixed: Use dot notation
    
    result = await db.execute(
        select(ExportBatch)
        .where(ExportBatch.tenant_id == tenant_id)
        .order_by(ExportBatch.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    exports = result.scalars().all()
    
    return {
        "exports": [
            {
                "export_id": str(exp.id),
                "destination": exp.destination,
                "lead_count": exp.lead_count,
                "status": exp.status,
                "created_at": exp.created_at.isoformat(),
                "exported_at": exp.exported_at.isoformat() if exp.exported_at else None
            }
            for exp in exports
        ],
        "total": len(exports),
        "limit": limit,
        "offset": offset
    }


@router.delete("/export/{export_id}")
async def delete_export(
    export_id: str,
    current_user: User = Depends(get_current_user),  # Fixed: User object, not dict
    db: AsyncSession = Depends(get_db)
):
    """Delete an export record."""
    tenant_id = current_user.tenant_id  # Fixed: Use dot notation
    
    result = await db.execute(
        select(ExportBatch).where(
            ExportBatch.id == export_id,
            ExportBatch.tenant_id == tenant_id
        )
    )
    export_batch = result.scalar_one_or_none()
    
    if not export_batch:
        raise HTTPException(status_code=404, detail="Export not found")
    
    # In production, also delete file from S3
    # if export_batch.file_path:
    #     s3_client.delete_object(Bucket=bucket, Key=export_batch.file_path)
    
    await db.delete(export_batch)
    await db.commit()
    
    return {"message": "Export deleted successfully"}