# backend/app/routers/scraper_routes.py
"""
API routes for scraper management
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth import get_db
from app.auth import get_current_user
from app.models import User, DataSource, ScrapingRun, ScrapingLog

# ✅ FIXED IMPORT - Use correct function name
from app.services.scraper_engine.base_scraper import create_and_run_scraper

router = APIRouter(prefix="/api/v1/scrapers", tags=["scrapers"])


@router.post("/{scraper_id}/run")
async def trigger_scraper_run(
    scraper_id: UUID,
    batch_size: int = 50,
    max_results: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger a scraper run
    
    Args:
        scraper_id: Data source ID
        batch_size: Number of leads per batch (default 50)
        max_results: Maximum total results (optional)
    """
    
    # Verify scraper exists and belongs to user's tenant
    result = await db.execute(
        select(DataSource).where(
            DataSource.id == scraper_id,
            DataSource.tenant_id == current_user.tenant_id
        )
    )
    data_source = result.scalar_one_or_none()
    
    if not data_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scraper not found"
        )
    
    if not data_source.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scraper is not active"
        )
    
    # Check if already running
    existing_run = await db.execute(
        select(ScrapingRun).where(
            ScrapingRun.data_source_id == scraper_id,
            ScrapingRun.status == "running"
        )
    )
    if existing_run.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scraper is already running"
        )
    
    # ✅ FIXED FUNCTION CALL
    # Create and start scraping run
    run = await create_and_run_scraper(
        db=db,
        tenant_id=current_user.tenant_id,
        data_source_id=scraper_id,
        trigger_type="manual",
        user_id=current_user.id
    )
    
    return {
        "message": "Scraping run started",
        "run_id": str(run.id),
        "status": run.status,
        "data_source_id": str(run.data_source_id),
        "started_at": run.created_at.isoformat() if run.created_at else None
    }


@router.get("/{scraper_id}/runs")
async def list_scraper_runs(
    scraper_id: UUID,
    skip: int = 0,
    limit: int = 20,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all runs for a scraper"""
    
    # Build query
    query = select(ScrapingRun).where(
        ScrapingRun.data_source_id == scraper_id,
        ScrapingRun.tenant_id == current_user.tenant_id
    )
    
    if status_filter:
        query = query.where(ScrapingRun.status == status_filter)
    
    query = query.order_by(ScrapingRun.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    runs = result.scalars().all()
    
    return {
        "runs": [
            {
                "id": str(run.id),
                "status": run.status,
                "trigger_type": run.trigger_type,
                "leads_found": run.leads_found,
                "leads_saved": run.leads_saved,
                "leads_duplicates": run.leads_duplicates,
                "pages_scraped": run.pages_scraped,
                "api_calls": run.api_calls,
                "duration_seconds": run.duration_seconds,
                "error_message": run.error_message,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "created_at": run.created_at.isoformat() if run.created_at else None
            }
            for run in runs
        ],
        "total": len(runs),
        "skip": skip,
        "limit": limit
    }


@router.get("/runs/{run_id}")
async def get_run_details(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get details of a specific run"""
    
    result = await db.execute(
        select(ScrapingRun).where(
            ScrapingRun.id == run_id,
            ScrapingRun.tenant_id == current_user.tenant_id
        )
    )
    run = result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found"
        )
    
    return {
        "id": str(run.id),
        "data_source_id": str(run.data_source_id),
        "status": run.status,
        "trigger_type": run.trigger_type,
        "leads_found": run.leads_found,
        "leads_saved": run.leads_saved,
        "leads_duplicates": run.leads_duplicates,
        "leads_invalid": run.leads_invalid,
        "pages_scraped": run.pages_scraped,
        "requests_made": run.requests_made,
        "requests_failed": run.requests_failed,
        "api_calls": run.api_calls,
        "duration_seconds": run.duration_seconds,
        "error_message": run.error_message,
        "error_details": run.error_details,
        "config_snapshot": run.config_snapshot,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None
    }


@router.get("/runs/{run_id}/logs")
async def get_run_logs(
    run_id: UUID,
    level_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get logs for a specific run"""
    
    # Verify run belongs to user's tenant
    run_result = await db.execute(
        select(ScrapingRun).where(
            ScrapingRun.id == run_id,
            ScrapingRun.tenant_id == current_user.tenant_id
        )
    )
    run = run_result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found"
        )
    
    # Build logs query
    query = select(ScrapingLog).where(ScrapingLog.scraping_run_id == run_id)
    
    if level_filter:
        query = query.where(ScrapingLog.level == level_filter)
    
    query = query.order_by(ScrapingLog.created_at.asc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return {
        "logs": [
            {
                "id": str(log.id),
                "level": log.level,
                "message": log.message,
                "details": log.details,
                "url": log.url,
                "page_number": log.page_number,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
        ],
        "total": len(logs),
        "skip": skip,
        "limit": limit
    }


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel a running scraper"""
    
    result = await db.execute(
        select(ScrapingRun).where(
            ScrapingRun.id == run_id,
            ScrapingRun.tenant_id == current_user.tenant_id
        )
    )
    run = result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found"
        )
    
    if run.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel run with status: {run.status}"
        )
    
    # Update status to cancelled
    run.status = "cancelled"
    run.completed_at = datetime.utcnow()
    await db.commit()
    
    return {
        "message": "Run cancelled successfully",
        "run_id": str(run.id),
        "status": run.status
    }


@router.get("")
async def list_all_scrapers(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all data sources (scrapers)"""
    
    result = await db.execute(
        select(DataSource)
        .where(DataSource.tenant_id == current_user.tenant_id)
        .order_by(DataSource.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    
    scrapers = result.scalars().all()
    
    return {
        "scrapers": [
            {
                "id": str(scraper.id),
                "name": scraper.name,
                "source_type": scraper.source_type,
                "is_active": scraper.is_active,
                "last_run_at": scraper.last_run_at.isoformat() if scraper.last_run_at else None,
                "last_run_status": scraper.last_run_status,
                "total_runs": scraper.total_runs or 0,
                "total_leads_scraped": scraper.total_leads_scraped or 0,
                "created_at": scraper.created_at.isoformat() if scraper.created_at else None
            }
            for scraper in scrapers
        ],
        "total": len(scrapers),
        "skip": skip,
        "limit": limit
    }