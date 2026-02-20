"""Connector API routes."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import logging

from app.database import get_db
from app.models import Connector, ConnectorRun, Lead, User
from app.auth import require_admin, get_current_user
from app.services.connectors_service import ConnectorFactory

logger = logging.getLogger(__name__)
router = APIRouter()


# Schemas
class ConnectorConfigSchema(BaseModel):
    name: str
    type: str
    description: Optional[str] = None
    enabled: bool = False
    config: dict
    auto_sync: bool = False
    sync_frequency: str = 'manual'


class ConnectorResponse(BaseModel):
    id: str
    name: str
    type: str
    description: Optional[str]
    enabled: bool
    status: str
    total_leads_imported: int
    last_sync_at: Optional[str]
    config: Optional[dict] = None  # Only for admins
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class ConnectorRunResponse(BaseModel):
    id: str
    connector_id: str
    status: str
    leads_imported: int
    leads_failed: int
    leads_skipped: int
    leads_duplicate: int
    started_at: str
    completed_at: Optional[str]
    duration_seconds: Optional[int]
    error_message: Optional[str]
    triggered_by: Optional[str]
    trigger_type: str

    class Config:
        from_attributes = True


# Admin endpoints - Connector CRUD
@router.get("/connectors", response_model=List[ConnectorResponse])
async def get_connectors(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all connectors. Non-admins see only enabled ones without config."""
    
    filters = [Connector.tenant_id == current_user.tenant_id]
    
    # Non-admins only see enabled connectors
    if current_user.role != 'admin':
        filters.append(Connector.enabled == True)
    
    query = select(Connector).where(and_(*filters)).order_by(Connector.created_at)
    result = await db.execute(query)
    connectors = result.scalars().all()
    
    is_admin = current_user.role == 'admin'
    
    return [
        ConnectorResponse(
            id=str(c.id),
            name=c.name,
            type=c.type,
            description=c.description,
            enabled=c.enabled,
            status=c.status,
            total_leads_imported=c.total_leads_imported,
            last_sync_at=c.last_sync_at.isoformat() if c.last_sync_at else None,
            config=c.config if is_admin else None,  # Hide config from non-admins
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
        )
        for c in connectors
    ]


@router.post("/connectors", response_model=ConnectorResponse)
async def create_connector(
    connector_data: ConnectorConfigSchema,
    current_user: User = Depends(require_admin),  # Admin only
    db: AsyncSession = Depends(get_db)
):
    """Create new connector (admin only)."""
    
    # Validate connector type
    if connector_data.type not in ConnectorFactory.get_available_types():
        raise HTTPException(400, f"Invalid connector type: {connector_data.type}")
    
    connector = Connector(
        tenant_id=current_user.tenant_id,
        name=connector_data.name,
        type=connector_data.type,
        description=connector_data.description,
        enabled=connector_data.enabled,
        config=connector_data.config,
        auto_sync=connector_data.auto_sync,
        sync_frequency=connector_data.sync_frequency,
        status='not_configured',
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    
    db.add(connector)
    await db.commit()
    await db.refresh(connector)
    
    logger.info(f"Connector created: {connector.name} by {current_user.email}")
    
    return ConnectorResponse(
        id=str(connector.id),
        name=connector.name,
        type=connector.type,
        description=connector.description,
        enabled=connector.enabled,
        status=connector.status,
        total_leads_imported=connector.total_leads_imported,
        last_sync_at=None,
        config=connector.config,
        created_at=connector.created_at.isoformat(),
        updated_at=connector.updated_at.isoformat(),
    )


@router.put("/connectors/{connector_id}", response_model=ConnectorResponse)
async def update_connector(
    connector_id: str,
    connector_data: ConnectorConfigSchema,
    current_user: User = Depends(require_admin),  # Admin only
    db: AsyncSession = Depends(get_db)
):
    """Update connector (admin only)."""
    
    query = select(Connector).where(
        and_(
            Connector.id == connector_id,
            Connector.tenant_id == current_user.tenant_id
        )
    )
    result = await db.execute(query)
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise HTTPException(404, "Connector not found")
    
    connector.name = connector_data.name
    connector.description = connector_data.description
    connector.enabled = connector_data.enabled
    connector.config = connector_data.config
    connector.auto_sync = connector_data.auto_sync
    connector.sync_frequency = connector_data.sync_frequency
    connector.updated_by = current_user.id
    connector.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(connector)
    
    logger.info(f"Connector updated: {connector.name} by {current_user.email}")
    
    return ConnectorResponse(
        id=str(connector.id),
        name=connector.name,
        type=connector.type,
        description=connector.description,
        enabled=connector.enabled,
        status=connector.status,
        total_leads_imported=connector.total_leads_imported,
        last_sync_at=connector.last_sync_at.isoformat() if connector.last_sync_at else None,
        config=connector.config,
        created_at=connector.created_at.isoformat(),
        updated_at=connector.updated_at.isoformat(),
    )


@router.delete("/connectors/{connector_id}")
async def delete_connector(
    connector_id: str,
    current_user: User = Depends(require_admin),  # Admin only
    db: AsyncSession = Depends(get_db)
):
    """Delete connector (admin only)."""
    
    query = select(Connector).where(
        and_(
            Connector.id == connector_id,
            Connector.tenant_id == current_user.tenant_id
        )
    )
    result = await db.execute(query)
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise HTTPException(404, "Connector not found")
    
    await db.delete(connector)
    await db.commit()
    
    logger.info(f"Connector deleted: {connector.name} by {current_user.email}")
    
    return {"success": True}


# Test connection endpoint
@router.post("/connectors/{connector_id}/test")
async def test_connector(
    connector_id: str,
    current_user: User = Depends(require_admin),  # Admin only
    db: AsyncSession = Depends(get_db)
):
    """Test connector connection (admin only)."""
    
    query = select(Connector).where(
        and_(
            Connector.id == connector_id,
            Connector.tenant_id == current_user.tenant_id
        )
    )
    result = await db.execute(query)
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise HTTPException(404, "Connector not found")
    
    try:
        connector_instance = ConnectorFactory.get_connector(connector.type)
        test_result = await connector_instance.test_connection(connector.config)
        
        # Update status
        if test_result['success']:
            connector.status = 'ready'
        else:
            connector.status = 'error'
        
        await db.commit()
        
        return test_result
        
    except Exception as e:
        logger.error(f"Connector test failed: {e}")
        return {
            'success': False,
            'message': str(e)
        }


# Sync endpoint - All users can trigger
@router.post("/connectors/{connector_id}/sync")
async def sync_connector(
    connector_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),  # All users
    db: AsyncSession = Depends(get_db)
):
    """Trigger connector sync (all users)."""
    
    query = select(Connector).where(
        and_(
            Connector.id == connector_id,
            Connector.tenant_id == current_user.tenant_id,
            Connector.enabled == True  # Only enabled connectors
        )
    )
    result = await db.execute(query)
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise HTTPException(404, "Connector not found or not enabled")
    
    # Create run record
    run = ConnectorRun(
        connector_id=connector.id,
        tenant_id=current_user.tenant_id,
        status='running',
        triggered_by=current_user.id,
        trigger_type='manual',
        started_at=datetime.utcnow(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    
    # Start sync in background
    background_tasks.add_task(
        _execute_sync,
        str(run.id),
        str(connector.id),
        connector.type,
        connector.config,
        current_user.tenant_id
    )
    
    logger.info(f"Sync triggered for {connector.name} by {current_user.email}")
    
    return {
        'run_id': str(run.id),
        'status': 'running',
        'message': 'Sync started'
    }


# Get connector runs/history
@router.get("/connectors/{connector_id}/runs", response_model=List[ConnectorRunResponse])
async def get_connector_runs(
    connector_id: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get sync history for connector (all users)."""
    
    query = (
        select(ConnectorRun)
        .where(
            and_(
                ConnectorRun.connector_id == connector_id,
                ConnectorRun.tenant_id == current_user.tenant_id
            )
        )
        .order_by(ConnectorRun.started_at.desc())
        .limit(limit)
    )
    
    result = await db.execute(query)
    runs = result.scalars().all()
    
    return [
        ConnectorRunResponse(
            id=str(r.id),
            connector_id=str(r.connector_id),
            status=r.status,
            leads_imported=r.leads_imported,
            leads_failed=r.leads_failed,
            leads_skipped=r.leads_skipped,
            leads_duplicate=r.leads_duplicate,
            started_at=r.started_at.isoformat(),
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            duration_seconds=r.duration_seconds,
            error_message=r.error_message,
            triggered_by=str(r.triggered_by) if r.triggered_by else None,
            trigger_type=r.trigger_type,
        )
        for r in runs
    ]


# Get all recent runs across connectors
@router.get("/connector-runs", response_model=List[ConnectorRunResponse])
async def get_all_runs(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get recent sync runs across all connectors (all users)."""
    
    query = (
        select(ConnectorRun)
        .where(ConnectorRun.tenant_id == current_user.tenant_id)
        .order_by(ConnectorRun.started_at.desc())
        .limit(limit)
    )
    
    result = await db.execute(query)
    runs = result.scalars().all()
    
    return [
        ConnectorRunResponse(
            id=str(r.id),
            connector_id=str(r.connector_id),
            status=r.status,
            leads_imported=r.leads_imported,
            leads_failed=r.leads_failed,
            leads_skipped=r.leads_skipped,
            leads_duplicate=r.leads_duplicate,
            started_at=r.started_at.isoformat(),
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            duration_seconds=r.duration_seconds,
            error_message=r.error_message,
            triggered_by=str(r.triggered_by) if r.triggered_by else None,
            trigger_type=r.trigger_type,
        )
        for r in runs
    ]


# Background sync execution
async def _execute_sync(run_id: str, connector_id: str, connector_type: str, config: dict, tenant_id: str):
    """Execute connector sync in background."""
    from app.database import SessionLocal
    
    async with SessionLocal() as db:
        try:
            # Get connector instance
            connector = ConnectorFactory.get_connector(connector_type)
            
            # Fetch leads
            leads_data = await connector.fetch_leads(config)
            
            # Import leads to database
            imported = 0
            failed = 0
            skipped = 0
            duplicate = 0
            
            for lead_data in leads_data:
                try:
                    # Check for duplicate
                    existing = await db.execute(
                        select(Lead).where(
                            and_(
                                Lead.tenant_id == tenant_id,
                                Lead.email == lead_data['email']
                            )
                        )
                    )
                    if existing.scalar_one_or_none():
                        duplicate += 1
                        continue
                    
                    # Create lead
                    lead = Lead(
                        tenant_id=tenant_id,
                        connector_id=connector_id,
                        email=lead_data.get('email'),
                        first_name=lead_data.get('firstName'),
                        last_name=lead_data.get('lastName'),
                        phone=lead_data.get('phone'),
                        company_name=lead_data.get('companyName'),
                        job_title=lead_data.get('jobTitle'),
                        linkedin_url=lead_data.get('linkedinUrl'),
                        company_website=lead_data.get('website'),  # Fixed field name
                        source_name=lead_data.get('source_name', 'Connector'),
                        external_id=lead_data.get('external_id'),
                        status='new',
                        acquisition_timestamp=datetime.utcnow(),  # Required field
                    )
                    db.add(lead)
                    imported += 1
                    
                except Exception as e:
                    logger.error(f"Failed to import lead: {e}")
                    failed += 1
            
            await db.commit()
            
            # Update run
            run_query = select(ConnectorRun).where(ConnectorRun.id == run_id)
            run_result = await db.execute(run_query)
            run = run_result.scalar_one()
            
            run.status = 'success'
            run.leads_imported = imported
            run.leads_failed = failed
            run.leads_skipped = skipped
            run.leads_duplicate = duplicate
            run.completed_at = datetime.utcnow()
            run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
            
            # Update connector stats
            connector_query = select(Connector).where(Connector.id == connector_id)
            connector_result = await db.execute(connector_query)
            connector_obj = connector_result.scalar_one()
            
            connector_obj.last_sync_at = datetime.utcnow()
            connector_obj.total_leads_imported += imported
            connector_obj.status = 'ready'
            
            await db.commit()
            
            logger.info(f"Sync completed: {imported} imported, {duplicate} duplicates, {failed} failed")
            
        except Exception as e:
            logger.error(f"Sync execution failed: {e}")
            
            # Update run as failed
            run_query = select(ConnectorRun).where(ConnectorRun.id == run_id)
            run_result = await db.execute(run_query)
            run = run_result.scalar_one_or_none()
            
            if run:
                run.status = 'failed'
                run.error_message = str(e)
                run.completed_at = datetime.utcnow()
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
                await db.commit()