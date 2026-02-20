"""Settings schemas for tenant and user preferences."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TenantSettingsBase(BaseModel):
    """Base tenant settings schema."""
    lead_retention_days: int = Field(default=365, ge=1, le=3650)
    auto_enrichment: bool = Field(default=True)
    auto_verification: bool = Field(default=True)
    review_required: bool = Field(default=True)
    batch_size: int = Field(default=1000, ge=100, le=10000)
    batch_workers: int = Field(default=4, ge=1, le=20)
    notification_email: Optional[str] = None
    webhook_url: Optional[str] = None


class TenantSettingsUpdate(TenantSettingsBase):
    """Schema for updating tenant settings."""
    lead_retention_days: Optional[int] = Field(default=None, ge=1, le=3650)
    auto_enrichment: Optional[bool] = None
    auto_verification: Optional[bool] = None
    review_required: Optional[bool] = None
    batch_size: Optional[int] = Field(default=None, ge=100, le=10000)
    batch_workers: Optional[int] = Field(default=None, ge=1, le=20)


class TenantSettingsResponse(TenantSettingsBase):
    """Response schema for tenant settings."""
    tenant_id: str
    updated_at: datetime

    class Config:
        from_attributes = True


class UserPreferencesBase(BaseModel):
    """Base user preferences schema."""
    theme: str = Field(default="light")
    items_per_page: int = Field(default=50, ge=10, le=100)
    email_notifications: bool = Field(default=True)
    review_queue_autoload: bool = Field(default=True)
    default_view: str = Field(default="list")
    timezone: str = Field(default="UTC")


class UserPreferencesUpdate(UserPreferencesBase):
    """Schema for updating user preferences."""
    theme: Optional[str] = None
    items_per_page: Optional[int] = Field(default=None, ge=10, le=100)
    email_notifications: Optional[bool] = None
    review_queue_autoload: Optional[bool] = None
    default_view: Optional[str] = None
    timezone: Optional[str] = None


class UserPreferencesResponse(UserPreferencesBase):
    """Response schema for user preferences."""
    user_id: str
    updated_at: datetime

    class Config:
        from_attributes = True


class SourceConfigBase(BaseModel):
    """Base source configuration schema."""
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., description="Type: scraper, api, upload, n8n, partner")
    url: Optional[str] = None
    quality_score: float = Field(default=0.5, ge=0.0, le=1.0)
    is_active: bool = Field(default=True)
    scrape_frequency: Optional[str] = None
    config: Optional[dict] = Field(default_factory=dict)


class SourceConfigCreate(SourceConfigBase):
    """Schema for creating a new source."""
    pass


class SourceConfigUpdate(BaseModel):
    """Schema for updating a source."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    url: Optional[str] = None
    quality_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    is_active: Optional[bool] = None
    scrape_frequency: Optional[str] = None
    config: Optional[dict] = None


class SourceConfigResponse(SourceConfigBase):
    """Response schema for source configuration."""
    id: str
    created_at: datetime
    updated_at: datetime
    last_scraped_at: Optional[datetime] = None
    total_leads_imported: int = 0

    class Config:
        from_attributes = True


class IntegrationConfigBase(BaseModel):
    """Base integration configuration schema."""
    platform: str = Field(..., description="Platform: instantly, smartlead, salesforce")
    api_key: Optional[str] = None
    campaign_id: Optional[str] = None
    is_active: bool = Field(default=True)
    config: Optional[dict] = Field(default_factory=dict)


class IntegrationConfigCreate(IntegrationConfigBase):
    """Schema for creating integration config."""
    pass


class IntegrationConfigUpdate(BaseModel):
    """Schema for updating integration config."""
    api_key: Optional[str] = None
    campaign_id: Optional[str] = None
    is_active: Optional[bool] = None
    config: Optional[dict] = None


class IntegrationConfigResponse(IntegrationConfigBase):
    """Response schema for integration configuration."""
    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True