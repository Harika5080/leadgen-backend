"""
Pydantic schemas for ICP Engine.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, validator
from uuid import UUID


# ============================================================================
# ICP SCHEMAS
# ============================================================================

class ICPBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    
    # Scoring configuration
    scoring_config: Dict[str, Any] = Field(default_factory=dict)
    
    # ⭐ NEW - Auto-qualification thresholds
    auto_approve_threshold: float = Field(default=80.0, ge=0, le=100)
    review_threshold: float = Field(default=50.0, ge=0, le=100)
    auto_reject_threshold: float = Field(default=30.0, ge=0, le=100)
    
    # ⭐ NEW - Enrichment config
    enrichment_enabled: bool = True
    enrichment_cost_per_lead: float = Field(default=0.002, ge=0)
    enrichment_providers: Optional[Dict[str, bool]] = Field(
        default={"wappalyzer": True, "serpapi": True, "google_maps": False}
    )
    
    # ⭐ NEW - Verification config
    verification_enabled: bool = True
    verification_cost_per_lead: float = Field(default=0.002, ge=0)
    
    # ⭐ NEW - Scraper preferences
    preferred_scrapers: Optional[List[str]] = []
    
    # Existing fields
    is_active: bool = True


class ICPCreate(ICPBase):
    pass


class ICPUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    qualification_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    auto_qualify_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    scoring_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ICPResponse(ICPBase):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by_user_id: Optional[UUID] = None
    
    class Config:
        from_attributes = True


# ============================================================================
# DATA SOURCE SCHEMAS
# ============================================================================

# REPLACE DataSourceBase with this enhanced version

class DataSourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., description="http_api, csv, webhook")
    description: Optional[str] = None
    
    # Configuration (choose based on source_type)
    config: Dict[str, Any] = Field(default_factory=dict)  # For csv, webhook
    http_config: Dict[str, Any] = Field(default_factory=dict)  # For http_api
    variables: Dict[str, Any] = Field(default_factory=dict)  # For http_api
    
    field_mappings: Dict[str, Any] = Field(default_factory=dict)
    schedule_enabled: bool = True
    schedule_cron: Optional[str] = None
    schedule_timezone: str = "UTC"
    per_run_limit: int = Field(default=100, ge=1, le=10000)
    rate_limit_rpm: int = Field(default=60, ge=1)
    concurrent_limit: int = Field(default=5, ge=1, le=20)
    is_active: bool = True
    
    @validator('source_type')
    def validate_source_type(cls, v):
        allowed = ['http_api', 'csv', 'webhook']
        if v not in allowed:
            raise ValueError(f"source_type must be one of: {allowed}")
        return v
    
    @validator('http_config')
    def validate_http_config(cls, v, values):
        """If source_type is http_api, http_config should not be empty."""
        if values.get('source_type') == 'http_api' and not v:
            raise ValueError("http_config is required when source_type is 'http_api'")
        return v


class DataSourceCreate(DataSourceBase):
    icp_id: UUID


class DataSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    http_config: Optional[Dict[str, Any]] = None
    variables: Optional[Dict[str, Any]] = None
    field_mappings: Optional[Dict[str, Any]] = None
    schedule_enabled: Optional[bool] = None
    schedule_cron: Optional[str] = None
    schedule_timezone: Optional[str] = None
    per_run_limit: Optional[int] = Field(None, ge=1, le=10000)
    rate_limit_rpm: Optional[int] = Field(None, ge=1)
    concurrent_limit: Optional[int] = Field(None, ge=1, le=20)
    is_active: Optional[bool] = None


class DataSourceResponse(DataSourceBase):
    id: UUID
    icp_id: UUID
    tenant_id: UUID
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_run_stats: Dict[str, Any] = Field(default_factory=dict)
    next_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime  # Keep non-optional

    
    class Config:
        from_attributes = True


# ============================================================================
# SCORING RULE SCHEMAS
# ============================================================================

class ScoringRuleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    field_name: str = Field(..., min_length=1, max_length=100)
    scorer_type: str = Field(..., description="range, match, text, threshold, ai")
    config: Dict[str, Any] = Field(default_factory=dict)
    weight: float = Field(default=1.0, ge=0.0, le=10.0)
    is_active: bool = True
    
    @validator('scorer_type')
    def validate_scorer_type(cls, v):
        allowed = ['range', 'match', 'text', 'threshold', 'ai']
        if v not in allowed:
            raise ValueError(f"scorer_type must be one of: {allowed}")
        return v


class ScoringRuleCreate(ScoringRuleBase):
    icp_id: UUID


class ScoringRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    field_name: Optional[str] = Field(None, min_length=1, max_length=100)
    scorer_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    weight: Optional[float] = Field(None, ge=0.0, le=10.0)
    is_active: Optional[bool] = None


class ScoringRuleResponse(ScoringRuleBase):
    id: UUID
    icp_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ============================================================================
# INGESTION JOB SCHEMAS
# ============================================================================

class IngestionJobResponse(BaseModel):
    id: UUID
    data_source_id: UUID
    tenant_id: UUID
    job_type: str
    status: str
    leads_processed: int
    leads_qualified: int
    leads_rejected: int
    leads_duplicate: int
    errors: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class IngestionTriggerRequest(BaseModel):
    data_source_id: UUID
    limit: Optional[int] = Field(None, ge=1, le=10000, description="Override per_run_limit")


class IngestionTriggerResponse(BaseModel):
    job_id: UUID
    status: str
    message: str


# ============================================================================
# LEAD FIT SCORE SCHEMAS
# ============================================================================

class LeadFitScoreResponse(BaseModel):
    id: UUID
    lead_id: UUID
    icp_id: UUID
    overall_score: float
    rule_scores: Dict[str, Any]
    score_explanation: Dict[str, Any]
    qualified: bool
    auto_approved: bool
    calculated_at: datetime
    
    class Config:
        from_attributes = True