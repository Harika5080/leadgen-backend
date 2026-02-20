"""Settings management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List
import logging

from app.database import get_db
from app.auth import get_current_user, get_current_tenant
from app.models import User, Tenant, TenantSettings, Source
from app.schemas.settings import (
    TenantSettingsResponse,
    TenantSettingsUpdate,
    UserPreferencesResponse,
    UserPreferencesUpdate,
    SourceConfigCreate,
    SourceConfigUpdate,
    SourceConfigResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ==================== Tenant Settings ====================

@router.get("/tenant", response_model=TenantSettingsResponse)
async def get_tenant_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current tenant's settings."""
    
    # Get tenant settings
    result = await db.execute(
        select(TenantSettings).where(TenantSettings.tenant_id == current_user.tenant_id)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        # Create default settings if not exist
        settings = TenantSettings(tenant_id=current_user.tenant_id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    
    return TenantSettingsResponse(
        tenant_id=str(settings.tenant_id),
        lead_retention_days=settings.lead_retention_days,
        auto_enrichment=settings.auto_enrichment,
        auto_verification=settings.auto_verification,
        review_required=settings.review_required,
        batch_size=settings.batch_size,
        batch_workers=settings.batch_workers,
        notification_email=settings.notification_email,
        webhook_url=settings.webhook_url,
        updated_at=settings.updated_at
    )


@router.put("/tenant", response_model=TenantSettingsResponse)
async def update_tenant_settings(
    settings_update: TenantSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update tenant settings. Requires admin role."""
    
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    # Get existing settings
    result = await db.execute(
        select(TenantSettings).where(TenantSettings.tenant_id == current_user.tenant_id)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = TenantSettings(tenant_id=current_user.tenant_id)
        db.add(settings)
    
    # Update fields
    update_data = settings_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)
    
    await db.commit()
    await db.refresh(settings)
    
    logger.info(f"Tenant settings updated by {current_user.email}")
    
    return TenantSettingsResponse(
        tenant_id=str(settings.tenant_id),
        lead_retention_days=settings.lead_retention_days,
        auto_enrichment=settings.auto_enrichment,
        auto_verification=settings.auto_verification,
        review_required=settings.review_required,
        batch_size=settings.batch_size,
        batch_workers=settings.batch_workers,
        notification_email=settings.notification_email,
        webhook_url=settings.webhook_url,
        updated_at=settings.updated_at
    )


# ==================== User Preferences ====================

@router.get("/user", response_model=UserPreferencesResponse)
async def get_user_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's preferences."""
    
    # User preferences are stored in JSONB field
    preferences = current_user.preferences or {}
    
    return UserPreferencesResponse(
        user_id=str(current_user.id),
        theme=preferences.get('theme', 'light'),
        items_per_page=preferences.get('items_per_page', 50),
        email_notifications=preferences.get('email_notifications', True),
        review_queue_autoload=preferences.get('review_queue_autoload', True),
        default_view=preferences.get('default_view', 'list'),
        timezone=preferences.get('timezone', 'UTC'),
        updated_at=current_user.updated_at
    )


@router.put("/user", response_model=UserPreferencesResponse)
async def update_user_preferences(
    preferences_update: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user's preferences."""
    
    # Get current preferences
    current_prefs = current_user.preferences or {}
    
    # Update with new values
    update_data = preferences_update.model_dump(exclude_unset=True)
    current_prefs.update(update_data)
    
    # Save back to user
    current_user.preferences = current_prefs
    await db.commit()
    await db.refresh(current_user)
    
    logger.info(f"User preferences updated for {current_user.email}")
    
    return UserPreferencesResponse(
        user_id=str(current_user.id),
        theme=current_prefs.get('theme', 'light'),
        items_per_page=current_prefs.get('items_per_page', 50),
        email_notifications=current_prefs.get('email_notifications', True),
        review_queue_autoload=current_prefs.get('review_queue_autoload', True),
        default_view=current_prefs.get('default_view', 'list'),
        timezone=current_prefs.get('timezone', 'UTC'),
        updated_at=current_user.updated_at
    )


# ==================== Source Management ====================

@router.get("/sources", response_model=List[SourceConfigResponse])
async def list_sources(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all configured sources."""
    
    result = await db.execute(
        select(Source).order_by(Source.created_at.desc())
    )
    sources = result.scalars().all()
    
    return [
        SourceConfigResponse(
            id=str(source.id),
            name=source.name,
            source_type=source.type,
            url=source.url,
            quality_score=source.quality_score,
            is_active=source.status == 'active',
            scrape_frequency=source.scrape_frequency,
            config=source.scrape_config or {},
            created_at=source.created_at,
            updated_at=source.updated_at,
            last_scraped_at=source.last_scraped_at,
            total_leads_imported=0  # TODO: Add count from leads table
        )
        for source in sources
    ]


@router.post("/sources", response_model=SourceConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    source_data: SourceConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new source. Requires admin role."""
    
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    # Create source
    source = Source(
        name=source_data.name,
        type=source_data.source_type,
        url=source_data.url,
        quality_score=source_data.quality_score,
        status='active' if source_data.is_active else 'inactive',
        scrape_frequency=source_data.scrape_frequency,
        scrape_config=source_data.config
    )
    
    db.add(source)
    await db.commit()
    await db.refresh(source)
    
    logger.info(f"Source created: {source.name} by {current_user.email}")
    
    return SourceConfigResponse(
        id=str(source.id),
        name=source.name,
        source_type=source.type,
        url=source.url,
        quality_score=source.quality_score,
        is_active=source.status == 'active',
        scrape_frequency=source.scrape_frequency,
        config=source.scrape_config or {},
        created_at=source.created_at,
        updated_at=source.updated_at,
        last_scraped_at=source.last_scraped_at,
        total_leads_imported=0
    )


@router.put("/sources/{source_id}", response_model=SourceConfigResponse)
async def update_source(
    source_id: str,
    source_update: SourceConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a source. Requires admin role."""
    
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    # Get source
    result = await db.execute(
        select(Source).where(Source.id == source_id)
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found"
        )
    
    # Update fields
    update_data = source_update.model_dump(exclude_unset=True)
    
    if 'is_active' in update_data:
        source.status = 'active' if update_data.pop('is_active') else 'inactive'
    
    for field, value in update_data.items():
        if field == 'config':
            source.scrape_config = value
        else:
            setattr(source, field, value)
    
    await db.commit()
    await db.refresh(source)
    
    logger.info(f"Source updated: {source.name} by {current_user.email}")
    
    return SourceConfigResponse(
        id=str(source.id),
        name=source.name,
        source_type=source.type,
        url=source.url,
        quality_score=source.quality_score,
        is_active=source.status == 'active',
        scrape_frequency=source.scrape_frequency,
        config=source.scrape_config or {},
        created_at=source.created_at,
        updated_at=source.updated_at,
        last_scraped_at=source.last_scraped_at,
        total_leads_imported=0
    )


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a source. Requires admin role."""
    
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    # Get source
    result = await db.execute(
        select(Source).where(Source.id == source_id)
    )
    source = result.scalar_one_or_none()
    
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found"
        )
    
    # Soft delete by setting status to 'deleted'
    source.status = 'deleted'
    await db.commit()
    
    logger.info(f"Source deleted: {source.name} by {current_user.email}")
    
    return None