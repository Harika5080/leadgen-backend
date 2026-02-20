# backend/app/models.py - SIMPLIFIED VERSION
"""
SQLAlchemy ORM models - Simplified with minimal back_populates to avoid circular dependencies.

KEY CHANGES FROM ORIGINAL:
1. Removed most back_populates relationships
2. Kept foreign keys intact (data integrity preserved)
3. Used explicit foreign_keys parameter where needed
4. One-way relationships only (parent → child)
"""

from sqlalchemy import (
    Column, String, Boolean, Integer, Numeric, Text, DateTime, Float, JSON, Index,
    TIMESTAMP, ForeignKey, BigInteger, CheckConstraint, UniqueConstraint, NUMERIC
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime, timezone
import uuid
import hashlib


# ============================================================================
# TENANT & USER MODELS
# ============================================================================

class Tenant(Base):
    """Tenant/customer account."""
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    api_key_hash = Column(String(255), nullable=False, unique=True)
    status = Column(String(50), nullable=False, default="active")
    settings = Column(JSONB, default={})
    branding = Column(JSONB, default={})
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # SIMPLIFIED: One-way relationships only
    users = relationship("User", foreign_keys="User.tenant_id")
    icps = relationship("ICP", foreign_keys="ICP.tenant_id")
    leads = relationship("Lead", foreign_keys="Lead.tenant_id")
    data_sources = relationship("DataSource", foreign_keys="DataSource.tenant_id")
    
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended', 'trial')", name="chk_tenant_status"),
    )


class User(Base):
    """User account for web interface."""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(String(50), nullable=False, default="reviewer")
    is_active = Column(Boolean, default=True)
    preferences = Column(JSONB, default={})
    last_login = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # SIMPLIFIED: No relationships
    
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'reviewer', 'viewer')", name="chk_user_role"),
    )


# ============================================================================
# ICP MODEL
# ============================================================================

class ICP(Base):
    """Ideal Customer Profile."""
    __tablename__ = "icps"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Scoring rules
    scoring_rules = Column(JSONB, default={})
    filter_rules = Column(JSONB, default={})
    weight_config = Column(JSONB, default={})
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    last_processed_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    # SIMPLIFIED: One-way relationship only
    lead_assignments = relationship("LeadICPAssignment", foreign_keys="LeadICPAssignment.icp_id")
    raw_leads = relationship("RawLead", foreign_keys="RawLead.icp_id")
    lead_fit_scores = relationship("LeadFitScore", foreign_keys="LeadFitScore.icp_id")
    raw_lead_processing = relationship("RawLeadProcessing", foreign_keys="RawLeadProcessing.icp_id")
    
    def __repr__(self):
        return f"<ICP(id={self.id}, name='{self.name}', active={self.is_active})>"
    
    @property
    def total_leads(self):
        """Total leads assigned to this ICP"""
        return len(self.lead_assignments) if self.lead_assignments else 0
    
    @property
    def qualified_leads_count(self):
        """Count of qualified leads"""
        if not self.lead_assignments:
            return 0
        return len([la for la in self.lead_assignments if la.bucket == 'qualified'])
    
    @property
    def pending_review_count(self):
        """Count of leads pending review"""
        if not self.lead_assignments:
            return 0
        return len([la for la in self.lead_assignments if la.bucket == 'review'])
    
    def get_scoring_rules(self):
        """Get scoring rules with defaults"""
        default_rules = {
            "filters": {
                "required": {
                    "job_titles": [],
                    "industries": [],
                    "countries": [],
                    "company_size_min": 1,
                    "company_size_max": 999999
                },
                "excluded": {
                    "job_titles": [],
                    "industries": [],
                    "domains": []
                }
            },
            "weights": {
                "job_title_match": 40,
                "company_size_fit": 20,
                "industry_match": 20,
                "geographic_fit": 10,
                "technographic_signals": 10
            },
            "thresholds": {
                "auto_qualify": 85,
                "review_required": 60,
                "auto_reject": 59
            }
        }
        
        if not self.scoring_rules:
            return default_rules
        
        rules = default_rules.copy()
        rules.update(self.scoring_rules)
        return rules
    
    def matches_filters(self, lead):
        """Check if a lead passes this ICP's filters"""
        rules = self.get_scoring_rules()
        filters = rules.get('filters', {})
        required = filters.get('required', {})
        
        if required.get('job_titles'):
            if not lead.job_title:
                return False
            job_title_lower = lead.job_title.lower()
            if not any(jt.lower() in job_title_lower for jt in required['job_titles']):
                return False
        
        if required.get('industries'):
            if not lead.company_industry:
                return False
            if lead.company_industry not in required['industries']:
                return False
        
        if lead.company_size:
            min_size = required.get('company_size_min', 1)
            max_size = required.get('company_size_max', 999999)
            if not (min_size <= lead.company_size <= max_size):
                return False
        
        excluded = filters.get('excluded', {})
        
        if excluded.get('job_titles') and lead.job_title:
            job_title_lower = lead.job_title.lower()
            if any(jt.lower() in job_title_lower for jt in excluded['job_titles']):
                return False
        
        if excluded.get('domains') and lead.email:
            email_domain = lead.email.split('@')[-1] if '@' in lead.email else ''
            if email_domain in excluded['domains']:
                return False
        
        return True
    
    def calculate_fit_score(self, lead):
        """Calculate fit score for a lead (0-100)"""
        rules = self.get_scoring_rules()
        weights = rules.get('weights', {})
        score = 0.0
        
        if lead.job_title and rules['filters']['required'].get('job_titles'):
            job_title_lower = lead.job_title.lower()
            if any(jt.lower() in job_title_lower for jt in rules['filters']['required']['job_titles']):
                score += weights.get('job_title_match', 40)
        
        if lead.company_size:
            min_size = rules['filters']['required'].get('company_size_min', 1)
            max_size = rules['filters']['required'].get('company_size_max', 999999)
            mid_point = (min_size + max_size) / 2
            distance = abs(lead.company_size - mid_point)
            range_size = max_size - min_size
            fit_ratio = max(0, 1 - (distance / range_size)) if range_size > 0 else 1
            score += weights.get('company_size_fit', 20) * fit_ratio
        
        if lead.company_industry and rules['filters']['required'].get('industries'):
            if lead.company_industry in rules['filters']['required']['industries']:
                score += weights.get('industry_match', 20)
        
        if lead.country and rules['filters']['required'].get('countries'):
            if lead.country in rules['filters']['required']['countries']:
                score += weights.get('geographic_fit', 10)
        
        return min(100, score)


# ============================================================================
# DATA SOURCE MODEL
# ============================================================================

class DataSource(Base):
    """Data source configuration."""
    __tablename__ = "data_sources"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text)
    source_type = Column(String, nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    config = Column(JSONB)
    field_mappings = Column(JSONB)
    
    schedule_enabled = Column(Boolean, default=False)
    schedule_cron = Column(String)
    per_run_limit = Column(Integer, default=1000)
    
    is_active = Column(Boolean, default=True)
    last_run_error = Column(Text)
    last_run_count = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    # Scraper-specific fields
    source_type = Column(String(50), default='api')
    # source_type: 'scraper', 'api', 'csv_upload', 'webhook'

    scraper_config = Column(JSONB, default={})
    # Platform-specific configuration (search URLs, selectors, filters)

    schedule_config = Column(JSONB, default={})
    # Scheduling configuration

    proxy_config = Column(JSONB, default={})
    # Proxy credentials (Oxylabs for LinkedIn, API keys for Apollo)

    # Run tracking
    last_run_at = Column(DateTime(timezone=True))
    last_run_status = Column(String(50))
    next_run_at = Column(DateTime(timezone=True))
    total_runs = Column(Integer, default=0)
    total_leads_scraped = Column(Integer, default=0)

    # Relationships
    scraping_runs = relationship("ScrapingRun", back_populates="data_source")
    schedules = relationship("ScrapingSchedule", back_populates="data_source")
        
    # SIMPLIFIED: One-way relationships
    leads = relationship("Lead", foreign_keys="Lead.data_source_id")
    raw_leads = relationship("RawLead", foreign_keys="RawLead.data_source_id")
    
    def __repr__(self):
        return f"<DataSource(id={self.id}, name='{self.name}', type='{self.source_type}')>"


# ============================================================================
# LEAD MODEL
# ============================================================================

class Lead(Base):
    """Lead model - NO icp_id, universal leads."""
    __tablename__ = "leads"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    data_source_id = Column(UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="SET NULL"), index=True)
    source_metadata = Column(JSONB)
    
    # Contact info
    email = Column(String, nullable=False, index=True)
    first_name = Column(String)
    last_name = Column(String)
    full_name = Column(String)
    phone = Column(String)
    job_title = Column(String, index=True)
    linkedin_url = Column(String)
    
    # Location
    address = Column(String)
    city = Column(String)
    state = Column(String)
    zip_code = Column(String)
    country = Column(String, index=True)
    
    # Company info
    company_name = Column(String, index=True)
    company_website = Column(String)
    company_domain = Column(String)
    company_industry = Column(String, index=True)
    company_phone = Column(String)
    company_address = Column(String)
    company_city = Column(String)
    company_state = Column(String)
    company_country = Column(String)
    company_size = Column(Integer)
    company_revenue_estimate = Column(Float)
    
    # Enrichment
    enrichment_data = Column(JSONB)
    enriched_at = Column(DateTime(timezone=True))
    
    # Email verification
    email_verified = Column(Boolean, default=False)
    email_deliverable = Column(Boolean)
    email_deliverability_score = Column(Float)
    verified_at = Column(DateTime(timezone=True))
    
    # Source tracking
    source_name = Column(String)
    source_url = Column(String)
    acquisition_timestamp = Column(DateTime(timezone=True))
    
    # Connector tracking
    connector_id = Column(UUID(as_uuid=True))
    external_id = Column(String)
    
    # Processing status
    processing_status = Column(String, default='raw', index=True)
    last_processed_at = Column(DateTime(timezone=True), index=True)
    processing_error = Column(Text)
    icp_match_count = Column(Integer, default=0, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    # SIMPLIFIED: One-way relationships only
    icp_assignments = relationship("LeadICPAssignment", foreign_keys="LeadICPAssignment.lead_id")
    notes = relationship("LeadNote", foreign_keys="LeadNote.lead_id")
    processing_stages = relationship("LeadProcessingStage", foreign_keys="LeadProcessingStage.lead_id")
    rejection_tracking = relationship("LeadRejectionTracking", foreign_keys="LeadRejectionTracking.lead_id")
    activities = relationship("LeadActivity", foreign_keys="LeadActivity.lead_id")
    fit_scores = relationship("LeadFitScore", foreign_keys="LeadFitScore.lead_id")
    conversion = relationship("LeadConversion", foreign_keys="LeadConversion.lead_id", uselist=False)
    
    __table_args__ = (
        {'schema': 'public'}
    )
    
    def __repr__(self):
        return f"<Lead(id={self.id}, email='{self.email}', status='{self.processing_status}')>"
    
    @property
    def is_raw(self):
        return self.processing_status == 'raw'
    
    @property
    def is_processed(self):
        return self.processing_status == 'processed'
    
    @property
    def matched_any_icp(self):
        return self.icp_match_count > 0
    
    @property
    def display_name(self):
        if self.full_name:
            return self.full_name
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        if self.first_name:
            return self.first_name
        return self.email.split('@')[0]
    
    def get_icp_assignment(self, icp_id):
        if not self.icp_assignments:
            return None
        return next((a for a in self.icp_assignments if a.icp_id == icp_id), None)
    
    def mark_as_processing(self):
        self.processing_status = 'processing'
        self.last_processed_at = func.now()
    
    def mark_as_processed(self):
        self.processing_status = 'processed'
        self.last_processed_at = func.now()
        self.processing_error = None
    
    def mark_as_error(self, error_message):
        self.processing_status = 'error'
        self.last_processed_at = func.now()
        self.processing_error = error_message


# ============================================================================
# LEAD-ICP ASSIGNMENT MODEL
# ============================================================================

class LeadICPAssignment(Base):
    """Lead to ICP assignment."""
    __tablename__ = "lead_icp_assignments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    icp_id = Column(UUID(as_uuid=True), ForeignKey("icps.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Scoring
    fit_score = Column(Float)
    fit_score_percentage = Column(Float, index=True)
    scoring_details = Column(JSONB)
    
    # Pipeline stage
    bucket = Column(String(50), default='new', nullable=False, index=True)
    processed_at = Column(DateTime(timezone=True), default=func.now(), index=True)
    scoring_version = Column(Integer, default=1)
    
    # Status
    status = Column(String, default='pending_review', index=True)
    
    # Review tracking
    qualified_at = Column(DateTime(timezone=True))
    reviewed_at = Column(DateTime(timezone=True))
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    review_notes = Column(Text)
    
    # Export tracking
    exported_to_crm = Column(Boolean, default=False)
    exported_at = Column(DateTime(timezone=True))
    export_metadata = Column(JSONB)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # SIMPLIFIED: NO relationships to avoid circular dependencies
    processing_records = relationship("RawLeadProcessing", foreign_keys="RawLeadProcessing.assignment_id")
    
    __table_args__ = (
        {'schema': 'public'}
    )
    
    def __repr__(self):
        return f"<LeadICPAssignment(lead={self.lead_id}, icp={self.icp_id}, bucket='{self.bucket}', score={self.fit_score_percentage})>"
    
    @property
    def is_qualified(self):
        return self.bucket == 'qualified' or self.status == 'qualified'
    
    @property
    def is_rejected(self):
        return self.bucket == 'rejected' or self.status == 'rejected'
    
    @property
    def is_pending_review(self):
        return self.bucket == 'review' or self.status == 'pending_review'
    
    @property
    def is_exported(self):
        return self.exported_to_crm or self.bucket == 'exported'
    
    def approve(self, user_id, notes=None):
        self.status = 'qualified'
        self.bucket = 'qualified'
        self.reviewed_at = func.now()
        self.reviewed_by = user_id
        self.qualified_at = func.now()
        if notes:
            self.review_notes = notes
    
    def reject(self, user_id, notes=None):
        self.status = 'rejected'
        self.bucket = 'rejected'
        self.reviewed_at = func.now()
        self.reviewed_by = user_id
        if notes:
            self.review_notes = notes
    
    def move_to_bucket(self, bucket_name):
        valid_buckets = ['new', 'score', 'enriched', 'verified', 'review', 'qualified', 'rejected', 'exported']
        if bucket_name not in valid_buckets:
            raise ValueError(f"Invalid bucket: {bucket_name}")
        
        self.bucket = bucket_name
        
        bucket_to_status = {
            'new': 'pending_review',
            'score': 'pending_review',
            'enriched': 'pending_review',
            'verified': 'pending_review',
            'review': 'pending_review',
            'qualified': 'qualified',
            'rejected': 'rejected',
            'exported': 'exported'
        }
        self.status = bucket_to_status.get(bucket_name, 'pending_review')
    
    def mark_as_exported(self, crm_name, crm_record_id):
        self.exported_to_crm = True
        self.exported_at = func.now()
        self.bucket = 'exported'
        self.export_metadata = {
            'crm': crm_name,
            'record_id': crm_record_id,
            'exported_at': func.now().isoformat() if hasattr(func.now(), 'isoformat') else str(func.now())
        }
    
    def get_bucket_display_name(self):
        bucket_names = {
            'new': 'New',
            'score': 'Scored',
            'enriched': 'Enriched',
            'verified': 'Verified',
            'review': 'Pending Review',
            'qualified': 'Qualified',
            'rejected': 'Rejected',
            'exported': 'Exported'
        }
        return bucket_names.get(self.bucket, self.bucket.title())


# ============================================================================
# RAW LEAD MODELS
# ============================================================================

class RawLead(Base):
    """Universal raw leads bucket."""
    __tablename__ = "raw_leads"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    icp_id = Column(UUID(as_uuid=True), ForeignKey('icps.id'), nullable=True, index=True)
    data_source_id = Column(UUID(as_uuid=True), ForeignKey("data_sources.id"), nullable=True)
    
    raw_data = Column(JSONB, nullable=False, default={})
    mapped_data = Column(JSONB)
    source_url = Column(Text)
    
    status = Column(String(50), default='pending')
    processed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    processed_by_icps = Column(JSONB, default=[])
    
    email_hash = Column(String(64), index=True)
    company_hash = Column(String(64), index=True)
    dedupe_key = Column(String(128))
    # ✅ ONLY track source info (minimal)
    source_name = Column(String(100))   # "apollo", "linkedin_scraper", "csv"
    source_type = Column(String(50))    # "api", "scraper", "manual"
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # SIMPLIFIED: One-way relationship only
    processing_records = relationship("RawLeadProcessing", foreign_keys="RawLeadProcessing.raw_lead_id")
    
    __table_args__ = (
        Index('idx_raw_leads_tenant', 'tenant_id'),
        Index('idx_raw_leads_status', 'status'),
        Index('idx_raw_leads_created', 'created_at'),
        Index('idx_raw_leads_universal', 'tenant_id', 'status'),
        Index('idx_raw_leads_email_hash', 'tenant_id', 'email_hash'),
        Index('idx_raw_leads_company_hash', 'tenant_id', 'company_hash'),
    )
    
    @classmethod
    def generate_email_hash(cls, email: str) -> str:
        if not email:
            return None
        normalized = email.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    @classmethod
    def generate_company_hash(cls, company_name: str) -> str:
        if not company_name:
            return None
        normalized = company_name.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    @classmethod
    def generate_dedupe_key(cls, tenant_id: str, email: str = None, company: str = None) -> str:
        key_base = email or company
        if not key_base:
            return None
        normalized = key_base.lower().strip()
        composite = f"{tenant_id}:{normalized}"
        return hashlib.sha256(composite.encode()).hexdigest()[:128]
    
    def is_processed_by_icp(self, icp_id: str) -> bool:
        if not self.processed_by_icps:
            return False
        return str(icp_id) in self.processed_by_icps
    
    def mark_processed_by_icp(self, icp_id: str):
        if not self.processed_by_icps:
            self.processed_by_icps = []
        if str(icp_id) not in self.processed_by_icps:
            self.processed_by_icps.append(str(icp_id))


class RawLeadProcessing(Base):
    """Track processing of raw leads for each ICP."""
    __tablename__ = "raw_lead_processing"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_lead_id = Column(UUID(as_uuid=True), ForeignKey("raw_leads.id", ondelete="CASCADE"), nullable=False)
    icp_id = Column(UUID(as_uuid=True), ForeignKey("icps.id", ondelete="CASCADE"), nullable=False)
    
    processed_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    result_lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"))
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("lead_icp_assignments.id", ondelete="SET NULL"))
    
    status = Column(String(50), default='completed', nullable=False)
    score = Column(Float)
    decision = Column(String(50))
    error_message = Column(Text)
    
    processing_duration_ms = Column(Integer)
    enrichment_attempted = Column(Boolean, default=False)
    verification_attempted = Column(Boolean, default=False)
    
    # SIMPLIFIED: NO relationships
    
    __table_args__ = (
        UniqueConstraint('raw_lead_id', 'icp_id', name='uq_raw_lead_icp_processing'),
        Index('idx_raw_lead_processing_icp', 'icp_id', 'status', 'processed_at'),
        Index('idx_raw_lead_processing_raw_lead', 'raw_lead_id'),
        Index('idx_raw_lead_processing_assignment', 'assignment_id'),
    )


# ============================================================================
# SUPPORTING MODELS
# ============================================================================

class ScoringRule(Base):
    """Individual scoring rule for an ICP."""
    __tablename__ = "scoring_rules"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    icp_id = Column(UUID(as_uuid=True), ForeignKey("icps.id"), nullable=False)
    name = Column(String(255), nullable=False)
    field_name = Column(String(100), nullable=False)
    rule_type = Column(String(50), nullable=False)
    condition = Column(JSONB, default={})
    weight = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LeadNote(Base):
    """User notes on leads."""
    __tablename__ = "lead_notes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class LeadProcessingStage(Base):
    """Tracks a lead's movement through processing buckets."""
    __tablename__ = "lead_processing_stages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey('leads.id', ondelete='CASCADE'), nullable=False, index=True)
    current_stage = Column(String(50), nullable=False, index=True)
    previous_stage = Column(String(50))
    stage_entered_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    processing_metadata = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class LeadRejectionTracking(Base):
    """Tracks why leads were rejected."""
    __tablename__ = "lead_rejection_tracking"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey('leads.id', ondelete='CASCADE'), nullable=False, index=True)
    rejection_stage = Column(String(50), nullable=False)
    rejection_reason = Column(String(255), nullable=False)
    rejection_category = Column(String(100), nullable=False)
    failed_criteria = Column(JSONB, default=[])
    rejected_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Connector(Base):
    """External data source connector configuration."""
    __tablename__ = "connectors"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False)
    description = Column(Text)
    enabled = Column(Boolean, default=False)
    status = Column(String(20), default='not_configured')
    config = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AuditLog(Base):
    """Audit log for tracking all user actions and system events."""
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    user_email = Column(String(255), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=False, index=True)
    resource_id = Column(String(100), nullable=True, index=True)
    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    request_method = Column(String(10), nullable=True)
    request_path = Column(String(500), nullable=True)
    meta = Column(JSON, nullable=True)
    status = Column(String(20), default='success')
    error_message = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    __table_args__ = (
        Index('idx_audit_tenant_created', 'tenant_id', 'created_at'),
        Index('idx_audit_user_created', 'user_id', 'created_at'),
        Index('idx_audit_action_created', 'action', 'created_at'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
    )


class SystemSettings(Base):
    """System-wide settings."""
    __tablename__ = "system_settings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category = Column(String(100), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(JSONB, nullable=False)
    description = Column(Text)
    is_sensitive = Column(Boolean, default=False)
    updated_by = Column(String(255))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint("category", "key", name="uq_category_key"),
    )


class TenantSettings(Base):
    """Tenant-specific configuration settings."""
    __tablename__ = "tenant_settings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)
    lead_retention_days = Column(Integer, default=365)
    auto_enrichment = Column(Boolean, default=True)
    auto_verification = Column(Boolean, default=True)
    review_required = Column(Boolean, default=True)
    batch_size = Column(Integer, default=1000)
    batch_workers = Column(Integer, default=4)
    notification_email = Column(String(255))
    webhook_url = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Source(Base):
    """Data source configuration."""
    __tablename__ = "sources"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    url = Column(Text)
    type = Column(String(50), nullable=False)
    quality_score = Column(Float, default=0.5)
    status = Column(String(50), default='active')
    scrape_frequency = Column(String(50))
    scrape_config = Column(JSONB)
    last_scraped_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LeadActivity(Base):
    """Complete audit trail of all lead interactions."""
    __tablename__ = 'lead_activities'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    lead_id = Column(UUID(as_uuid=True), ForeignKey('leads.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'))
    
    activity_type = Column(String(50), nullable=False)
    old_status = Column(String(50))
    new_status = Column(String(50))
    title = Column(String(255))
    description = Column(Text)
    activity_metadata = Column(JSONB)
    
    source = Column(String(100))
    ip_address = Column(INET)
    user_agent = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    __table_args__ = (
        CheckConstraint(
            "activity_type IN ('status_change', 'note', 'email', 'call', 'task', "
            "'conversion', 'assignment', 'score_change', 'enrichment', "
            "'import', 'export', 'merge', 'delete')",
            name='valid_activity_type'
        ),
        Index('idx_lead_activities_lead', 'lead_id', 'created_at'),
        Index('idx_lead_activities_tenant', 'tenant_id'),
        Index('idx_lead_activities_user', 'user_id'),
        Index('idx_lead_activities_type', 'activity_type'),
    )


class WorkflowStatus(Base):
    """Tenant-specific workflow statuses."""
    __tablename__ = 'workflow_statuses'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    
    name = Column(String(100), nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(Text)
    color = Column(String(7), default='#667eea')
    icon = Column(String(50))
    order = Column(Integer, nullable=False, default=0)
    is_initial = Column(Boolean, default=False)
    is_final = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    # SIMPLIFIED: One-way relationships
    transitions_from = relationship("WorkflowTransition", foreign_keys="WorkflowTransition.from_status_id")
    transitions_to = relationship("WorkflowTransition", foreign_keys="WorkflowTransition.to_status_id")
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='uq_tenant_status_name'),
        CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name='valid_hex_color'),
        Index('idx_workflow_statuses_tenant', 'tenant_id'),
        Index('idx_workflow_statuses_order', 'tenant_id', 'order'),
    )


class ConnectorRun(Base):
    """Track connector sync runs."""
    __tablename__ = "connector_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_id = Column(UUID(as_uuid=True), ForeignKey("connectors.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False)
    triggered_by = Column(UUID(as_uuid=True), nullable=True)
    trigger_type = Column(String(20), default='manual')
    leads_imported = Column(Integer, default=0)
    leads_failed = Column(Integer, default=0)
    leads_skipped = Column(Integer, default=0)
    leads_duplicate = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)
    run_meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_runs_connector', 'connector_id'),
        Index('idx_runs_tenant', 'tenant_id'),
        Index('idx_runs_started', 'started_at'),
    )


class IngestionJob(Base):
    """Track ingestion job runs and their results."""
    __tablename__ = "ingestion_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_source_id = Column(UUID(as_uuid=True), ForeignKey("data_sources.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    job_type = Column(String(50), default="scheduled")
    status = Column(String(50), default="pending")
    leads_processed = Column(Integer, default=0)
    leads_qualified = Column(Integer, default=0)
    leads_rejected = Column(Integer, default=0)
    leads_duplicate = Column(Integer, default=0)
    errors = Column(JSONB, default=[])
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LeadFitScore(Base):
    """Calculated fit score for a lead against an ICP."""
    __tablename__ = "lead_fit_scores"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    icp_id = Column(UUID(as_uuid=True), ForeignKey("icps.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    overall_score = Column(Float, nullable=False)
    rule_scores = Column(JSONB, default={})
    score_explanation = Column(JSONB, default={})
    qualified = Column(Boolean, default=False)
    auto_approved = Column(Boolean, default=False)
    calculated_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_lead_fit_scores_lead_id', 'lead_id'),
        Index('idx_lead_fit_scores_icp_id', 'icp_id'),
        Index('idx_lead_fit_scores_tenant_id', 'tenant_id'),
        Index('idx_lead_fit_scores_overall_score', 'overall_score'),
        Index('idx_lead_fit_scores_qualified', 'qualified'),
        UniqueConstraint('lead_id', 'icp_id', name='uq_lead_icp_score'),
    )


class APITemplate(Base):
    """Pre-configured API templates for common data sources."""
    __tablename__ = "api_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    provider = Column(String(100), nullable=False)
    category = Column(String(50), default='leads')
    description = Column(Text)
    http_config = Column(JSONB, nullable=False)
    default_field_mappings = Column(JSONB, default={})
    required_variables = Column(JSONB, default=[])
    optional_variables = Column(JSONB, default=[])
    setup_instructions = Column(Text)
    example_variables = Column(JSONB, default={})
    api_docs_url = Column(String(500))
    pricing_info = Column(Text)
    is_public = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_api_templates_provider', 'provider'),
        Index('idx_api_templates_category', 'category'),
        Index('idx_api_templates_is_public', 'is_public'),
    )


class WorkflowTransition(Base):
    """Defines allowed status changes in workflow."""
    __tablename__ = 'workflow_transitions'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    from_status_id = Column(UUID(as_uuid=True), ForeignKey('workflow_statuses.id', ondelete='CASCADE'), nullable=False)
    to_status_id = Column(UUID(as_uuid=True), ForeignKey('workflow_statuses.id', ondelete='CASCADE'), nullable=False)
    is_automatic = Column(Boolean, default=False)
    require_note = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('tenant_id', 'from_status_id', 'to_status_id', name='uq_tenant_transition'),
        Index('idx_workflow_transitions_tenant', 'tenant_id'),
    )


class LeadConversion(Base):
    """Detailed conversion tracking."""
    __tablename__ = 'lead_conversions'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    lead_id = Column(UUID(as_uuid=True), ForeignKey('leads.id', ondelete='CASCADE'), nullable=False, unique=True)
    
    converted_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    converted_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    conversion_value = Column(Numeric(15, 2))
    conversion_currency = Column(String(3), default='USD')
    first_touch_source = Column(String(100))
    last_touch_source = Column(String(100))
    campaign_id = Column(String(100))
    time_to_conversion_seconds = Column(Integer)
    touchpoints_count = Column(Integer, default=1)
    status_changes_count = Column(Integer, default=0)
    notes = Column(Text)
    conversion_metadata = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_conversions_tenant', 'tenant_id'),
        Index('idx_conversions_user', 'converted_by'),
        Index('idx_conversions_date', 'converted_at'),
    )