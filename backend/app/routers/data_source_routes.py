"""
Data Source Management Routes - MULTI-ICP ARCHITECTURE
=======================================================
In the multi-ICP design:
- DataSources belong to TENANT (not ICP)
- Raw leads are scraped into raw_leads table with optional icp_id
- Leads are processed and assigned to MULTIPLE ICPs via lead_icp_assignments
- Each ICP can have different scoring/status for the same lead
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.models import DataSource, User
from app.auth import get_current_user

# Optional: Import croniter for next_run_at calculation
try:
    from croniter import croniter
    import pytz
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False


router = APIRouter(prefix="/api/v1/data-sources", tags=["Data Sources"])


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_next_run(schedule_cron: str, timezone: str = "UTC") -> Optional[datetime]:
    """Calculate next run time from cron expression."""
    if not HAS_CRONITER:
        return None
    
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        cron = croniter(schedule_cron, now)
        next_run = cron.get_next(datetime)
        # Convert to UTC for storage
        return next_run.astimezone(pytz.UTC).replace(tzinfo=None)
    except Exception as e:
        print(f"Error calculating next run: {e}")
        return None


# ============================================================================
# SCHEMAS
# ============================================================================

class DataSourceCreate(BaseModel):
    """Create a new data source for the tenant."""
    name: str
    source_type: str = Field(..., description="http_api, csv, webhook, scraper")
    description: Optional[str] = None
    
    # Configuration
    config: Dict[str, Any] = Field(default_factory=dict)
    http_config: Dict[str, Any] = Field(default_factory=dict)
    variables: Dict[str, Any] = Field(default_factory=dict)
    field_mappings: Dict[str, Any] = Field(default_factory=dict)
    
    # Scheduling
    schedule_enabled: bool = True
    schedule_cron: Optional[str] = None
    per_run_limit: int = 100
    
    is_active: bool = True


class DataSourceUpdate(BaseModel):
    """Update data source configuration."""
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    http_config: Optional[Dict[str, Any]] = None
    variables: Optional[Dict[str, Any]] = None
    field_mappings: Optional[Dict[str, Any]] = None
    schedule_enabled: Optional[bool] = None
    schedule_cron: Optional[str] = None
    per_run_limit: Optional[int] = None
    is_active: Optional[bool] = None


class DataSourceResponse(BaseModel):
    """Data source response without sensitive config."""
    id: UUID
    tenant_id: UUID
    name: str
    source_type: str
    description: Optional[str] = None
    is_active: bool
    
    # Status
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_run_stats: Dict[str, Any] = Field(default_factory=dict)
    next_run_at: Optional[datetime] = None
    
    # Config flags (sensitive data hidden)
    has_http_config: bool = False
    has_variables: bool = False
    has_field_mappings: bool = False
    
    schedule_enabled: bool
    schedule_cron: Optional[str] = None
    per_run_limit: int
    
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class DataSourceDetailResponse(DataSourceResponse):
    """Includes full configuration - only for authenticated users."""
    config: Dict[str, Any] = Field(default_factory=dict)
    http_config: Dict[str, Any] = Field(default_factory=dict)
    variables: Dict[str, Any] = Field(default_factory=dict)  # API keys will be masked
    field_mappings: Dict[str, Any] = Field(default_factory=dict)


class TestConnectionRequest(BaseModel):
    """Test connection to data source."""
    source_type: str
    config: Dict[str, Any] = Field(default_factory=dict)
    http_config: Dict[str, Any] = Field(default_factory=dict)
    variables: Dict[str, Any] = Field(default_factory=dict)


class TestConnectionResponse(BaseModel):
    """Connection test result."""
    success: bool
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# ROUTES
# ============================================================================

@router.post("", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_data_source(
    data_source: DataSourceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new data source for the tenant.
    
    Data sources belong to the tenant and scrape raw leads.
    Raw leads can optionally be tagged with an ICP during scraping,
    but the multi-ICP assignment happens during processing.
    """
    
    # Validate source_type
    valid_types = ['http_api', 'csv', 'webhook', 'scraper']
    if data_source.source_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_type. Must be one of: {', '.join(valid_types)}"
        )
    
    new_data_source = DataSource(
        tenant_id=current_user.tenant_id,
        name=data_source.name,
        source_type=data_source.source_type,
        description=data_source.description,
        config=data_source.config,
        http_config=data_source.http_config,
        variables=data_source.variables,
        field_mappings=data_source.field_mappings,
        schedule_enabled=data_source.schedule_enabled,
        schedule_cron=data_source.schedule_cron,
        per_run_limit=data_source.per_run_limit,
        is_active=data_source.is_active
    )
    
    # Calculate next_run_at if schedule is enabled
    if new_data_source.schedule_enabled and new_data_source.schedule_cron and HAS_CRONITER:
        new_data_source.next_run_at = calculate_next_run(new_data_source.schedule_cron)
    
    db.add(new_data_source)
    await db.commit()
    await db.refresh(new_data_source)
    
    # Build response
    response = DataSourceResponse.model_validate(new_data_source)
    response.has_http_config = bool(new_data_source.http_config)
    response.has_variables = bool(new_data_source.variables)
    response.has_field_mappings = bool(new_data_source.field_mappings)
    
    return response


@router.get("/", response_model=List[DataSourceResponse])
async def list_data_sources(
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all data sources for current tenant.
    
    In multi-ICP architecture, data sources belong to tenant, not ICP.
    """
    stmt = select(DataSource).where(DataSource.tenant_id == current_user.tenant_id)
    
    if is_active is not None:
        stmt = stmt.where(DataSource.is_active == is_active)
    
    stmt = stmt.order_by(DataSource.created_at.desc())
    
    result = await db.execute(stmt)
    data_sources = result.scalars().all()
    
    # Build responses
    responses = []
    for ds in data_sources:
        response = DataSourceResponse.model_validate(ds)
        response.has_http_config = bool(ds.http_config)
        response.has_variables = bool(ds.variables)
        response.has_field_mappings = bool(ds.field_mappings)
        responses.append(response)
    
    return responses


@router.get("/{data_source_id}", response_model=DataSourceDetailResponse)
async def get_data_source(
    data_source_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get data source details including configuration.
    """
    stmt = select(DataSource).where(
        DataSource.id == data_source_id,
        DataSource.tenant_id == current_user.tenant_id
    )
    result = await db.execute(stmt)
    data_source = result.scalars().first()
    
    if not data_source:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # Build response (mask sensitive data in variables)
    response = DataSourceDetailResponse.model_validate(data_source)
    response.has_http_config = bool(data_source.http_config)
    response.has_variables = bool(data_source.variables)
    response.has_field_mappings = bool(data_source.field_mappings)
    
    # Mask API keys in variables
    if data_source.variables:
        masked_vars = {}
        for key, value in data_source.variables.items():
            if 'key' in key.lower() or 'token' in key.lower() or 'secret' in key.lower():
                # Mask sensitive values
                if isinstance(value, str) and len(value) > 8:
                    masked_vars[key] = value[:4] + '****' + value[-4:]
                else:
                    masked_vars[key] = '****'
            else:
                masked_vars[key] = value
        response.variables = masked_vars
    
    return response


@router.put("/{data_source_id}", response_model=DataSourceResponse)
async def update_data_source(
    data_source_id: UUID,
    data_source_update: DataSourceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update data source configuration.
    """
    stmt = select(DataSource).where(
        DataSource.id == data_source_id,
        DataSource.tenant_id == current_user.tenant_id
    )
    result = await db.execute(stmt)
    data_source = result.scalars().first()
    
    if not data_source:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # Update fields
    update_data = data_source_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(data_source, key, value)
    
    # Recalculate next_run_at if schedule changed
    if ('schedule_enabled' in update_data or 'schedule_cron' in update_data) and HAS_CRONITER:
        if data_source.schedule_enabled and data_source.schedule_cron:
            data_source.next_run_at = calculate_next_run(data_source.schedule_cron)
        else:
            data_source.next_run_at = None
    
    data_source.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(data_source)
    
    # Build response
    response = DataSourceResponse.model_validate(data_source)
    response.has_http_config = bool(data_source.http_config)
    response.has_variables = bool(data_source.variables)
    response.has_field_mappings = bool(data_source.field_mappings)
    
    return response


@router.delete("/{data_source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_source(
    data_source_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete data source.
    
    Note: This will not delete raw_leads or leads created by this source.
    """
    stmt = select(DataSource).where(
        DataSource.id == data_source_id,
        DataSource.tenant_id == current_user.tenant_id
    )
    result = await db.execute(stmt)
    data_source = result.scalars().first()
    
    if not data_source:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    await db.delete(data_source)
    await db.commit()
    
    return None


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    test_request: TestConnectionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Test connection to a data source without saving it.
    Useful for validating configuration before creating.
    """
    try:
        # For now, just validate the config structure
        # You can implement actual adapter testing here
        
        if not test_request.source_type:
            raise ValueError("source_type is required")
        
        valid_types = ['http_api', 'csv', 'webhook', 'scraper']
        if test_request.source_type not in valid_types:
            raise ValueError(f"Invalid source_type. Must be one of: {', '.join(valid_types)}")
        
        # Basic validation passed
        return TestConnectionResponse(
            success=True,
            message="Configuration is valid",
            details={
                "source_type": test_request.source_type,
                "has_config": bool(test_request.config),
                "has_http_config": bool(test_request.http_config),
                "has_variables": bool(test_request.variables)
            }
        )
    
    except Exception as e:
        return TestConnectionResponse(
            success=False,
            message=f"Configuration test failed: {str(e)}",
            details={"error": str(e)}
        )


# ============================================================================
# STATS ENDPOINT (Optional - for dashboard)
# ============================================================================

@router.get("/stats/overview")
async def get_data_source_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get overview statistics for all data sources.
    """
    stmt = select(DataSource).where(DataSource.tenant_id == current_user.tenant_id)
    result = await db.execute(stmt)
    sources = result.scalars().all()
    
    total = len(sources)
    active = sum(1 for s in sources if s.is_active)
    scheduled = sum(1 for s in sources if s.schedule_enabled)
    
    # Get stats by type
    by_type = {}
    for source in sources:
        source_type = source.source_type
        by_type[source_type] = by_type.get(source_type, 0) + 1
    
    return {
        "total_sources": total,
        "active_sources": active,
        "scheduled_sources": scheduled,
        "by_type": by_type,
        "sources": [
            {
                "id": str(s.id),
                "name": s.name,
                "type": s.source_type,
                "is_active": s.is_active,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
                "last_run_status": s.last_run_status,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None
            }
            for s in sources
        ]
    }