"""
Pydantic schemas for ICP bucket system
These are for API request/response validation, NOT database models
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime


class BucketStats(BaseModel):
    """Statistics for a single bucket"""
    bucket: str
    lead_count: int
    avg_duration_seconds: int
    avg_score: Optional[float] = None
    
    class Config:
        from_attributes = True


class LeadInBucket(BaseModel):
    """Lead information when displayed in bucket view"""
    id: UUID
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    job_title: Optional[str]
    phone: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    
    # Company info
    company_name: Optional[str]
    company_size: Optional[str]
    company_city: Optional[str]
    company_state: Optional[str]
    company_country: Optional[str]
    
    # Lead metadata
    lead_fit_score: Optional[float]
    current_bucket: str
    bucket_entered_at: datetime
    
    # Source info
    source_id: Optional[UUID]
    source_name: Optional[str]
    
    # Processing flags
    is_enriched: bool = False
    is_verified: bool = False
    verification_status: Optional[str]
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class BucketLeadList(BaseModel):
    """Paginated list of leads in a bucket"""
    leads: List[LeadInBucket]
    total: int
    page: int
    limit: int
    total_pages: int
    bucket: str
    icp_id: UUID


class BucketLeadFilter(BaseModel):
    """Filters for querying leads in buckets"""
    icp_id: UUID
    bucket: str
    search: Optional[str] = None
    company_size: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    score_min: Optional[float] = Field(None, ge=0, le=100)
    score_max: Optional[float] = Field(None, ge=0, le=100)
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = Field(1, ge=1)
    limit: int = Field(50, ge=1, le=100)
    
    @validator('score_max')
    def score_max_must_be_greater_than_min(cls, v, values):
        if v is not None and 'score_min' in values and values['score_min'] is not None:
            if v < values['score_min']:
                raise ValueError('score_max must be greater than score_min')
        return v


class LeadBucketMove(BaseModel):
    """Request to move a lead to a different bucket"""
    lead_id: UUID
    target_bucket: str
    reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}
    
    @validator('target_bucket')
    def validate_bucket(cls, v):
        valid_buckets = [
            'raw_landing', 'scored', 'enriched', 'verified',
            'approved', 'pending_review', 'rejected'
        ]
        if v not in valid_buckets:
            raise ValueError(f'target_bucket must be one of: {", ".join(valid_buckets)}')
        return v


class ICPProcessingConfig(BaseModel):
    """ICP processing configuration"""
    icp_id: UUID
    enrichment_enabled: bool = True
    verification_enabled: bool = True
    auto_approve_threshold: float = Field(80.0, ge=0, le=100)
    review_threshold: float = Field(50.0, ge=0, le=100)
    auto_reject_threshold: float = Field(30.0, ge=0, le=100)
    preferred_scrapers: List[str] = ['crawlee', 'puppeteer']
    enrichment_cost_per_lead: float = 0.10
    verification_cost_per_lead: float = 0.008
    
    @validator('review_threshold')
    def review_must_be_greater_than_reject(cls, v, values):
        if 'auto_reject_threshold' in values and v <= values['auto_reject_threshold']:
            raise ValueError('review_threshold must be greater than auto_reject_threshold')
        return v
    
    @validator('auto_approve_threshold')
    def approve_must_be_greater_than_review(cls, v, values):
        if 'review_threshold' in values and v <= values['review_threshold']:
            raise ValueError('auto_approve_threshold must be greater than review_threshold')
        return v


class ICPProcessingConfigUpdate(BaseModel):
    """Update ICP processing configuration"""
    enrichment_enabled: Optional[bool] = None
    verification_enabled: Optional[bool] = None
    auto_approve_threshold: Optional[float] = Field(None, ge=0, le=100)
    review_threshold: Optional[float] = Field(None, ge=0, le=100)
    auto_reject_threshold: Optional[float] = Field(None, ge=0, le=100)
    preferred_scrapers: Optional[List[str]] = None
    enrichment_cost_per_lead: Optional[float] = None
    verification_cost_per_lead: Optional[float] = None


class BucketFlowAnalytics(BaseModel):
    """Analytics for lead flow through buckets"""
    icp_id: UUID
    period_days: int
    
    # Conversion rates
    raw_to_scored_rate: float
    scored_to_enriched_rate: float
    enriched_to_verified_rate: float
    verified_to_approved_rate: float
    
    # Average durations (seconds)
    avg_raw_duration: int
    avg_scored_duration: int
    avg_enriched_duration: int
    avg_verified_duration: int
    avg_review_duration: int
    
    # Rejection stats
    rejection_rate: float
    top_rejection_reasons: List[Dict[str, Any]]
    
    # Volume metrics
    total_processed: int
    currently_in_pipeline: int
    approved_count: int
    rejected_count: int
    pending_review_count: int


class ProcessingStageHistory(BaseModel):
    """History of a lead's movement through buckets"""
    id: UUID
    lead_id: UUID
    current_stage: str
    previous_stage: Optional[str]
    stage_entered_at: datetime
    stage_duration_seconds: Optional[int]
    is_enriched: bool
    is_verified: bool
    is_scored: bool
    processing_metadata: Dict[str, Any]
    
    class Config:
        from_attributes = True