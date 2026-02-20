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
    TIMESTAMP, ForeignKey, BigInteger, CheckConstraint, UniqueConstraint, NUMERIC,ARRAY
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime, timezone
import uuid
import hashlib
from uuid import uuid4
from decimal import Decimal


# ============================================================================
# TENANT & USER MODELS
# ============================================================================

class Tenant(Base):
    """Tenant/customer account."""
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    domain = Column(String(255), unique=True, index=True)  # ✅ NEW: Company domain
    api_key_hash = Column(String(255), nullable=False, unique=True)
    status = Column(String(50), nullable=False, default="active")
    settings = Column(JSONB, default={})
    branding = Column(JSONB, default={})
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    users = relationship("User", foreign_keys="User.tenant_id")
    icps = relationship("ICP", foreign_keys="ICP.tenant_id")
    leads = relationship("Lead", foreign_keys="Lead.tenant_id")
    data_sources = relationship("DataSource", foreign_keys="DataSource.tenant_id")
    raw_leads = relationship("RawLead", back_populates="tenant", cascade="all, delete-orphan")
    enrichment_caches = relationship(
        "EnrichmentCache",
        back_populates="tenant",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended', 'trial')", name="chk_tenant_status"),
    )

    def __repr__(self):
        return f"<Tenant(id={self.id}, name='{self.name}', domain='{self.domain}')>"

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
    
    # ========================================================================
    # BASIC INFO
    # ========================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # ========================================================================
    # SCORING CONFIGURATION
    # ========================================================================
    # Scoring rules - how to score leads
    scoring_rules = Column(JSONB, default={})
    # Example: {
    #   "job_title_keywords": ["VP Sales", "Director Sales"],
    #   "target_industries": ["Software", "Technology"],
    #   "ideal_company_size_min": 500,
    #   "ideal_company_size_max": 2000
    # }
    
    # Filter rules - hard requirements
    filter_rules = Column(JSONB, default={})
    # Example: {
    #   "min_company_size": 100,
    #   "required_locations": ["USA", "Canada"],
    #   "excluded_industries": ["Retail"]
    # }
    
    # Weight config - importance of each dimension
    weight_config = Column(JSONB, default={})
    # Example: {
    #   "job_title": 40,
    #   "company_size": 30,
    #   "industry": 20,
    #   "seniority": 10
    # }
    
    # ========================================================================
    # AUTO-QUALIFICATION THRESHOLDS
    # ========================================================================
    auto_approve_threshold = Column(Numeric(5, 2), default=80.0)
    # Leads with score >= 80 → auto-qualified
    
    review_threshold = Column(Numeric(5, 2), default=50.0)
    # Leads with score >= 50 but < 80 → pending_review
    
    auto_reject_threshold = Column(Numeric(5, 2), default=30.0)
    # Leads with score < 30 → auto-rejected
    
    # ========================================================================
    # ENRICHMENT CONFIGURATION
    # ========================================================================
    enrichment_enabled = Column(Boolean, default=True, nullable=False)
    # Master switch for enrichment
    
    enrichment_cost_per_lead = Column(Numeric(10, 4), default=0.002)
    # Expected cost per lead for enrichment
    
    enrichment_providers = Column(JSONB, default={
        "wappalyzer": True,
        "serpapi": True,
        "google_maps": False
    })
    # Per-provider feature flags
    # Example: {"wappalyzer": true, "serpapi": true, "google_maps": false}
    
    # ========================================================================
    # EMAIL VERIFICATION CONFIGURATION
    # ========================================================================
    verification_enabled = Column(Boolean, default=True, nullable=False)
    # Master switch for email verification
    
    verification_cost_per_lead = Column(Numeric(10, 4), default=0.002)
    # Expected cost per lead for verification
    
    # ========================================================================
    # SCRAPER PREFERENCES
    # ========================================================================
    preferred_scrapers = Column(JSONB, nullable=True, default=None) 
    # List of preferred scraper types for this ICP
    # Example: ["linkedin", "google_maps", "apollo"]
    
    # ========================================================================
    # STATUS & TRACKING
    # ========================================================================
    is_active = Column(Boolean, default=True, nullable=False)
    last_processed_at = Column(DateTime(timezone=True))
    
    # ========================================================================
    # TIMESTAMPS & AUDIT
    # ========================================================================
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    lead_assignments = relationship("LeadICPAssignment", foreign_keys="LeadICPAssignment.icp_id")
    raw_leads = relationship("RawLead", foreign_keys="RawLead.icp_id")
    lead_fit_scores = relationship("LeadFitScore", foreign_keys="LeadFitScore.icp_id")
    raw_lead_processing = relationship("RawLeadProcessing", foreign_keys="RawLeadProcessing.icp_id")
    
   
    def __repr__(self):
        return f"<ICP(id={self.id}, name='{self.name}', active={self.is_active})>"
    
    # ========================================================================
    # HELPER PROPERTIES
    # ========================================================================
    
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
    
    @property
    def enrichment_config(self):
        """Get enrichment configuration summary"""
        return {
            "enabled": self.enrichment_enabled,
            "cost_per_lead": float(self.enrichment_cost_per_lead) if self.enrichment_cost_per_lead else 0.0,
            "providers": self.enrichment_providers or {}
        }
    
    @property
    def verification_config(self):
        """Get verification configuration summary"""
        return {
            "enabled": self.verification_enabled,
            "cost_per_lead": float(self.verification_cost_per_lead) if self.verification_cost_per_lead else 0.0
        }
    
    @property
    def thresholds(self):
        """Get auto-qualification thresholds"""
        return {
            "auto_approve": float(self.auto_approve_threshold) if self.auto_approve_threshold else 80.0,
            "review": float(self.review_threshold) if self.review_threshold else 50.0,
            "auto_reject": float(self.auto_reject_threshold) if self.auto_reject_threshold else 30.0
        }
    
    # ========================================================================
    # SCORING METHODS
    # ========================================================================
    
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
                "auto_qualify": float(self.auto_approve_threshold) if self.auto_approve_threshold else 85,
                "review_required": float(self.review_threshold) if self.review_threshold else 60,
                "auto_reject": float(self.auto_reject_threshold) if self.auto_reject_threshold else 30
            }
        }
        
        if not self.scoring_rules:
            return default_rules
        
        rules = default_rules.copy()
        rules.update(self.scoring_rules)
        
        # Override thresholds with column values
        rules["thresholds"] = {
            "auto_qualify": float(self.auto_approve_threshold) if self.auto_approve_threshold else 85,
            "review_required": float(self.review_threshold) if self.review_threshold else 60,
            "auto_reject": float(self.auto_reject_threshold) if self.auto_reject_threshold else 30
        }
        
        return rules
    
    def matches_filters(self, lead):
        """Check if a lead passes this ICP's filters"""
        rules = self.get_scoring_rules()
        filters = rules.get('filters', {})
        required = filters.get('required', {})
        
        # Check required job titles
        if required.get('job_titles'):
            if not lead.job_title:
                return False
            job_title_lower = lead.job_title.lower()
            if not any(jt.lower() in job_title_lower for jt in required['job_titles']):
                return False
        
        # Check required industries
        if required.get('industries'):
            if not lead.company_industry:
                return False
            if lead.company_industry not in required['industries']:
                return False
        
        # Check company size
        if lead.company_size:
            min_size = required.get('company_size_min', 1)
            max_size = required.get('company_size_max', 999999)
            if not (min_size <= lead.company_size <= max_size):
                return False
        
        # Check excluded items
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
        
        # Job title match
        if lead.job_title and rules['filters']['required'].get('job_titles'):
            job_title_lower = lead.job_title.lower()
            if any(jt.lower() in job_title_lower for jt in rules['filters']['required']['job_titles']):
                score += weights.get('job_title_match', 40)
        
        # Company size fit
        if lead.company_size:
            min_size = rules['filters']['required'].get('company_size_min', 1)
            max_size = rules['filters']['required'].get('company_size_max', 999999)
            mid_point = (min_size + max_size) / 2
            distance = abs(lead.company_size - mid_point)
            range_size = max_size - min_size
            fit_ratio = max(0, 1 - (distance / range_size)) if range_size > 0 else 1
            score += weights.get('company_size_fit', 20) * fit_ratio
        
        # Industry match
        if lead.company_industry and rules['filters']['required'].get('industries'):
            if lead.company_industry in rules['filters']['required']['industries']:
                score += weights.get('industry_match', 20)
        
        # Geographic fit
        if lead.country and rules['filters']['required'].get('countries'):
            if lead.country in rules['filters']['required']['countries']:
                score += weights.get('geographic_fit', 10)
        
        return min(100, score)
    
    def should_enrich(self):
        """Check if enrichment is enabled for this ICP"""
        return self.enrichment_enabled and self.is_active
    
    def should_verify(self):
        """Check if email verification is enabled for this ICP"""
        return self.verification_enabled and self.is_active
    
    def get_decision(self, score: float, email_verified: bool = False) -> str:
        """
        Get auto-qualification decision based on score and thresholds
        
        Args:
            score: Fit score (0-100)
            email_verified: Whether email is verified
            
        Returns:
            Decision: "qualified", "pending_review", or "rejected"
        """
        auto_approve = float(self.auto_approve_threshold) if self.auto_approve_threshold else 80.0
        review = float(self.review_threshold) if self.review_threshold else 50.0
        auto_reject = float(self.auto_reject_threshold) if self.auto_reject_threshold else 30.0
        
        # Auto-approve: high score + verified email
        if score >= auto_approve and (email_verified or not self.verification_enabled):
            return "qualified"
        
        # Review: medium score
        elif score >= review:
            return "pending_review"
        
        # Auto-reject: low score
        elif score < auto_reject:
            return "rejected"
        
        # Default: review
        else:
            return "pending_review"
    
    def estimate_cost_per_lead(self) -> float:
        """
        Estimate total cost per lead for this ICP
        
        Returns:
            Total estimated cost (enrichment + verification)
        """
        total = 0.0
        
        if self.enrichment_enabled and self.enrichment_cost_per_lead:
            total += float(self.enrichment_cost_per_lead)
        
        if self.verification_enabled and self.verification_cost_per_lead:
            total += float(self.verification_cost_per_lead)
        
        return total
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "tenant_id": str(self.tenant_id),
            "is_active": self.is_active,
            "scoring_rules": self.scoring_rules,
            "filter_rules": self.filter_rules,
            "weight_config": self.weight_config,
            "thresholds": self.thresholds,
            "enrichment": self.enrichment_config,
            "verification": self.verification_config,
            "preferred_scrapers": self.preferred_scrapers,
            "estimated_cost_per_lead": self.estimate_cost_per_lead(),
            "total_leads": self.total_leads,
            "qualified_leads": self.qualified_leads_count,
            "pending_review": self.pending_review_count,
            "last_processed_at": self.last_processed_at.isoformat() if self.last_processed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


# ============================================================================
# DATA SOURCE MODEL
# ============================================================================
class DataSource(Base):
    """Data source configuration - Multi-ICP Architecture"""
    __tablename__ = "data_sources"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name = Column(String, nullable=False)
    description = Column(Text)
    source_type = Column(String, nullable=False)
    
    # Configuration
    config = Column(JSONB, default=dict)
    http_config = Column(JSONB, default=dict)     # ← ADDED
    variables = Column(JSONB, default=dict)       # ← ADDED
    field_mappings = Column(JSONB, default=dict)
    
    # Scheduling
    schedule_enabled = Column(Boolean, default=False)
    schedule_cron = Column(String)
    per_run_limit = Column(Integer, default=1000)
    
    # Status
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True))
    last_run_status = Column(String)
    last_run_stats = Column(JSONB, default=dict)  # ← ADDED
    next_run_at = Column(DateTime(timezone=True)) # ← ADDED
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    raw_leads = relationship("RawLead", foreign_keys="RawLead.data_source_id")
        # ✅ ADD THESE RELATIONSHIPS (CRITICAL - this is what's missing):
    scraping_runs = relationship(
        "ScrapingRun",
        back_populates="data_source",
        cascade="all, delete-orphan"
    )
    
    schedules = relationship(
        "ScrapingSchedule", 
        back_populates="data_source",
        cascade="all, delete-orphan"
    )

# ADD THIS MODEL - Insert after Lead model and before LeadRejectionTracking

# ============================================================================
# LEAD MODEL
# ============================================================================

class Lead(Base):
    """
    Core lead record - NO direct icp_id
    Uses lead_icp_assignments for multi-ICP scoring
    """
    __tablename__ = "leads"
    
    # ========================================================================
    # BASIC INFO
    # ========================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_lead_id = Column(UUID(as_uuid=True), ForeignKey("raw_leads.id"), index=True)
    
    # ========================================================================
    # CONTACT INFO
    # ========================================================================
    email = Column(String(255), nullable=False, index=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone = Column(String(50))
    linkedin_url = Column(String(500))
    
    # ========================================================================
    # JOB INFO
    # ========================================================================
    job_title = Column(String(255))
    seniority_level = Column(String(50))  # C-Level, VP, Director, Manager, Individual Contributor
    
    # ========================================================================
    # COMPANY INFO
    # ========================================================================
    company_name = Column(String(255))
    company_domain = Column(String(255))
    company_website = Column(String(500))
    company_size = Column(String(50), nullable=True)
    company_industry = Column(String(255))
    company_revenue_estimate = Column(String(100))
    company_description = Column(Text)
    company_employee_count = Column(String(50))
    
    # ========================================================================
    # LOCATION
    # ========================================================================
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(100))
    zip_code = Column(String(20))
    
    # ========================================================================
    # SOURCE INFO
    # ========================================================================
    source = Column(String(100))  # linkedin, apollo, hunter, manual, etc.
    source_url = Column(String(1000))
    
    # ========================================================================
    # ENRICHMENT DATA
    # ========================================================================
    enrichment_data = Column(JSONB)  # Stores all enriched fields
    enrichment_completeness = Column(Integer, default=0)  # Percentage of fields enriched
    
    # ========================================================================
    # EMAIL VERIFICATION
    # ========================================================================
    email_verified = Column(Boolean, default=False)
    email_verification_status = Column(String(50))  # valid, invalid, risky, unknown
    email_verification_confidence = Column(Numeric(5, 2))  # 0-100
    verification_data = Column(JSONB)
    
    # ========================================================================
    # TIMESTAMPS
    # ========================================================================
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Processing timestamps (removed status and stage tracking - moved to assignments)
    processing_started_at = Column(DateTime(timezone=True))
    processing_completed_at = Column(DateTime(timezone=True))
    

    enrichment_status = Column(String(50), default='pending')
    enriched_at = Column(DateTime(timezone=True))
    enrichment_source = Column(String(100))
    enrichment_providers = Column(JSONB, default=list)
    enrichment_cost = Column(Numeric(10, 4), default=0.0)
    enrichment_skipped_reason = Column(Text)
    next_refresh_date = Column(DateTime(timezone=True))

    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    # One lead → Many ICP assignments
    icp_assignments = relationship(
        "LeadICPAssignment",
        back_populates="lead",
        foreign_keys="LeadICPAssignment.lead_id",
        cascade="all, delete-orphan"
    )
    
    # Activity history
    activities = relationship(
        "LeadStageActivity",
        back_populates="lead",
        foreign_keys="LeadStageActivity.lead_id",
        cascade="all, delete-orphan"
    )
    
    # Rejection tracking (per ICP via assignments)
    rejections = relationship(
        "LeadRejectionTracking",
        cascade="all, delete-orphan"
    )
    
    # Raw lead relationship
    raw_lead = relationship("RawLead", foreign_keys=[raw_lead_id])
    
    def __repr__(self):
        return f"<Lead(id={self.id}, email='{self.email}', company='{self.company_name}')>"
    
    # ========================================================================
    # HELPER PROPERTIES
    # ========================================================================
    
    @property
    def full_name(self):
        """Get full name"""
        parts = []
        if self.first_name:
            parts.append(self.first_name)
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts) if parts else None
    
    @property
    def is_enriched(self):
        """Check if lead has been enriched"""
        return self.enrichment_data is not None and len(self.enrichment_data) > 0
    
    @property
    def is_verified(self):
        """Check if email is verified"""
        return self.email_verified == True
    
    def get_assignment_for_icp(self, icp_id):
        """Get assignment for specific ICP"""
        for assignment in self.icp_assignments:
            if str(assignment.icp_id) == str(icp_id):
                return assignment
        return None
    
    def get_best_assignment(self):
        """Get assignment with highest score"""
        if not self.icp_assignments:
            return None
        return max(self.icp_assignments, key=lambda a: a.fit_score_percentage or 0)
    
    def get_qualified_assignments(self):
        """Get all qualified assignments"""
        return [a for a in self.icp_assignments if a.is_qualified]
    
    def get_pending_assignments(self):
        """Get all pending review assignments"""
        return [a for a in self.icp_assignments if a.is_pending_review]
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "email": self.email,
            "full_name": self.full_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "phone": self.phone,
            "job_title": self.job_title,
            "company_name": self.company_name,
            "company_domain": self.company_domain,
            "company_size": self.company_size,
            "company_industry": self.company_industry,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "source": self.source,
            "email_verified": self.email_verified,
            "enrichment_completeness": self.enrichment_completeness,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "assignments_count": len(self.icp_assignments) if self.icp_assignments else 0,
            "qualified_count": len(self.get_qualified_assignments()),
            "best_score": self.get_best_assignment().fit_score_percentage if self.get_best_assignment() else None
        }


class LeadStageActivity(Base):
    """
    Track lead stage transitions and activities per ICP assignment
    
    This replaces the old single-status tracking with multi-ICP activity tracking.
    Each stage change per assignment is logged here.
    """
    __tablename__ = "lead_stage_activity"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    icp_id = Column(UUID(as_uuid=True), ForeignKey("icps.id", ondelete="CASCADE"), index=True)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("lead_icp_assignments.id", ondelete="CASCADE"), index=True)
    
    # Stage information
    stage = Column(String(50), nullable=False, index=True)
    # Possible stages: created, scored, enriched, verified, qualified, pending_review, rejected, exported
    
    from_stage = Column(String(50))
    to_stage = Column(String(50))
    
    # Activity details
    details = Column(JSONB, default={})
    # Stores stage-specific data like:
    # - scoring: {fit_score: 85, confidence: 90, breakdown: {...}}
    # - enrichment: {provider: "wappalyzer", cost: 0.003, fields_added: [...]}
    # - verification: {valid: true, deliverable: true, provider: "zerobounce"}
    # - rejection: {reason: "low_score", score: 25}
    
    # User tracking (for manual actions)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # SIMPLIFIED: Minimal relationships
    lead = relationship("Lead", back_populates="activities", foreign_keys=[lead_id])
    
    def __repr__(self):
        return f"<LeadStageActivity(lead={self.lead_id}, icp={self.icp_id}, stage='{self.stage}')>"
    
    __table_args__ = (
        Index('idx_lead_stage_activity_lead_icp', 'lead_id', 'icp_id', 'timestamp'),
        Index('idx_lead_stage_activity_assignment', 'assignment_id', 'timestamp'),
        Index('idx_lead_stage_activity_stage', 'stage', 'timestamp'),       
    )
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "lead_id": str(self.lead_id),
            "icp_id": str(self.icp_id) if self.icp_id else None,
            "assignment_id": str(self.assignment_id) if self.assignment_id else None,
            "stage": self.stage,
            "from_stage": self.from_stage,
            "to_stage": self.to_stage,
            "details": self.details,
            "user_id": str(self.user_id) if self.user_id else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
# ============================================================================
# LEAD-ICP ASSIGNMENT MODEL
# ============================================================================

class LeadICPAssignment(Base):
    """
    Lead to ICP assignment with scoring and pipeline status
    
    Pipeline stages: new → scored → enriched → verified → qualified/review/rejected
    
    NOTE: Stage transition history is tracked in LeadStageActivity table,
    not in this table. This only stores current status.
    """
    __tablename__ = "lead_icp_assignments"
    
    # ========================================================================
    # PRIMARY KEYS
    # ========================================================================
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    icp_id = Column(UUID(as_uuid=True), ForeignKey("icps.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # ========================================================================
    # SCORING
    # ========================================================================
    fit_score = Column(Float)  # Raw score (0-100)
    fit_score_percentage = Column(Float, index=True)  # Normalized percentage
    scoring_details = Column(JSONB)  # Breakdown by dimension
    scoring_version = Column(Integer, default=1)
    icp_score_confidence = Column(Float)  # Confidence in score (0-100) - CRITICAL for ML
    
    # ========================================================================
    # PIPELINE STATUS (moved from Lead)
    # ========================================================================
    status = Column(String(50), default='new', nullable=False, index=True)
    # Possible values: new, scored, enriched, verified, qualified, pending_review, rejected, exported
    
    bucket = Column(String(50), default='new', nullable=False, index=True)
    # Legacy field - same as status for compatibility
    
    # NOTE: stage_updated_at REMOVED - redundant with LeadStageActivity.timestamp
    # Use LeadStageActivity to track when stages change
    
    # ========================================================================
    # PROCESSING METADATA
    # ========================================================================
    processed_at = Column(DateTime(timezone=True), default=func.now(), index=True)
    processing_job_id = Column(String(255), nullable=True)  # Link to batch processing job - CRITICAL for audit trail
    
    # ========================================================================
    # REVIEW TRACKING
    # ========================================================================
    qualified_at = Column(DateTime(timezone=True))
    reviewed_at = Column(DateTime(timezone=True))
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    review_notes = Column(Text)
    
    # ========================================================================
    # EXPORT TRACKING
    # ========================================================================
    exported_to_crm = Column(Boolean, default=False)
    exported_at = Column(DateTime(timezone=True))
    export_metadata = Column(JSONB)
    
    # ========================================================================
    # TIMESTAMPS
    # ========================================================================
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    lead = relationship("Lead", back_populates="icp_assignments", foreign_keys=[lead_id])
    icp = relationship("ICP", foreign_keys=[icp_id])
    processing_records = relationship("RawLeadProcessing", foreign_keys="RawLeadProcessing.assignment_id")
    
    def __repr__(self):
        return f"<LeadICPAssignment(lead={self.lead_id}, icp={self.icp_id}, status='{self.status}', score={self.fit_score_percentage})>"
# ============================================================================
# RAW LEAD MODELS
# ============================================================================

    def update_status(self, new_status: str):
        """Update assignment status and bucket"""
        self.status = new_status
        
        # Update bucket based on status
        status_to_bucket = {
            'new': 'new',
            'scored': 'score',
            'enriched': 'enriched',
            'verified': 'verified',
            'qualified': 'qualified',
            'pending_review': 'review',
            'rejected': 'rejected',
            'exported': 'exported'
        }
        
        if new_status in status_to_bucket:
            self.bucket = status_to_bucket[new_status]
    
class RawLead(Base):
    """
    Raw leads landing zone - matches actual database schema.
    
    Key fields are extracted to columns for:
    - Fast querying and indexing
    - Deduplication
    - Multi-ICP processing
    
    Full scraped data is preserved in scraped_data JSONB field.
    """
    __tablename__ = "raw_leads"
    
    # === PRIMARY FIELDS ===
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    icp_id = Column(UUID(as_uuid=True), ForeignKey('icps.id', ondelete='CASCADE'), nullable=True, index=True)
    source_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Optional reference to sources (no FK)
    data_source_id = Column(UUID(as_uuid=True), ForeignKey('data_sources.id', ondelete='SET NULL'), nullable=True)
    
    # === SOURCE INFORMATION ===
    source_name = Column(String(255), nullable=False)  # Name of the scraper/source
    source_url = Column(Text)  # URL where data was scraped from
    scraper_type = Column(String(50), nullable=False)  # crawlee, puppeteer, api, csv, etc.
    
    # === EXTRACTED CONTACT FIELDS ===
    # These are extracted from scraped_data for fast querying
    email = Column(String(255), nullable=True, index=True)  # Email can be null (enriched later)
    first_name = Column(String(100))
    last_name = Column(String(100))
    job_title = Column(String(255))
    company_name = Column(String(255))
    phone = Column(String(50))
    linkedin_url = Column(Text)
    
    # === LOCATION FIELDS (Phase 2) ===
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(100))
    zip_code = Column(String(20))
    
    # === COMPANY FIELDS (Phase 2) ===
    company_website = Column(String(255))
    company_domain = Column(String(255))
    company_industry = Column(String(100))
    company_size = Column(String(50), nullable=True)
    company_revenue_estimate = Column(String(50))
    company_linkedin_url = Column(Text)
    company_employee_count = Column(Integer)
    
    # === FULL SCRAPED DATA ===
    scraped_data = Column(JSONB, nullable=False, default=dict)  # Complete raw data from scraper
    enrichment_data = Column(JSONB, default=dict)  # Data added during enrichment
    
    # === PROCESSING STATUS ===
    status = Column(
        String(50), 
        nullable=False, 
        default='pending',
        index=True
    )  # pending, processed, failed
    
    processing_status = Column(
        String(50),
        nullable=False,
        default='pending'
    )  # pending, processing, processed, failed
    
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # === MULTI-ICP TRACKING ===
    processed_by_icps = Column(JSONB, default=list)  # Array of ICP IDs that processed this lead
    lead_id = Column(UUID(as_uuid=True), ForeignKey('leads.id', ondelete='SET NULL'), nullable=True)
    
    # === DEDUPLICATION ===
    email_hash = Column(String(64), index=True)
    company_hash = Column(String(64), index=True)
    dedupe_key = Column(String(128), index=True)
    
    # === TIMESTAMPS ===
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    processed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # === RELATIONSHIPS ===
    tenant = relationship("Tenant", back_populates="raw_leads")  
    icp = relationship("ICP", foreign_keys=[icp_id], overlaps="lead_assignments")
    lead = relationship("Lead", foreign_keys=[lead_id])
    
    # === INDEXES ===
    __table_args__ = (
        # Multi-tenant isolation
        Index('idx_raw_leads_tenant_id', 'tenant_id'),
        Index('idx_raw_leads_tenant_status', 'tenant_id', 'status'),
        
        # ICP processing
        Index('idx_raw_leads_icp_id', 'icp_id'),
        Index('idx_raw_leads_icp_status', 'icp_id', 'processing_status'),
        
        # Status queries
        Index('idx_raw_leads_processing_status', 'processing_status'),
        Index('idx_raw_leads_created_at', 'created_at'),
        
        # Deduplication
        Index('idx_raw_leads_email_hash', 'tenant_id', 'email_hash'),
        Index('idx_raw_leads_company_hash', 'tenant_id', 'company_hash'),
        Index('idx_raw_leads_dedupe_key', 'tenant_id', 'dedupe_key'),
        Index('idx_raw_leads_email', 'email'),
        
        # Universal bucket (no ICP assigned)
        Index('idx_raw_leads_universal', 'tenant_id', 'status', postgresql_where='icp_id IS NULL'),
        
        # Source tracking
        Index('idx_raw_leads_source_id', 'source_id'),
        Index('idx_raw_leads_lead_id', 'lead_id'),
        
        # GIN index for JSONB searching
        Index('idx_raw_leads_scraped_data', 'scraped_data', postgresql_using='gin'),
    )
    
    # === HELPER METHODS ===
    
    @classmethod
    def generate_email_hash(cls, email: str) -> str:
        """Generate SHA256 hash of email for deduplication."""
        if not email:
            return None
        normalized = email.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    @classmethod
    def generate_company_hash(cls, company_name: str) -> str:
        """Generate SHA256 hash of company name for deduplication."""
        if not company_name:
            return None
        normalized = company_name.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    @classmethod
    def generate_dedupe_key(cls, tenant_id: str, email: str = None, company: str = None) -> str:
        """Generate composite deduplication key."""
        key_base = email or company
        if not key_base:
            return None
        normalized = key_base.lower().strip()
        composite = f"{tenant_id}:{normalized}"
        return hashlib.sha256(composite.encode()).hexdigest()[:128]
    
    def is_processed_by_icp(self, icp_id: str) -> bool:
        """Check if this lead has been processed by a specific ICP."""
        if not self.processed_by_icps:
            return False
        return str(icp_id) in self.processed_by_icps
    
    def mark_processed_by_icp(self, icp_id: str):
        """Mark this lead as processed by an ICP."""
        if not self.processed_by_icps:
            self.processed_by_icps = []
        if str(icp_id) not in self.processed_by_icps:
            self.processed_by_icps.append(str(icp_id))
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': str(self.id),
            'tenant_id': str(self.tenant_id),
            'icp_id': str(self.icp_id) if self.icp_id else None,
            'source_name': self.source_name,
            'source_url': self.source_url,
            'scraper_type': self.scraper_type,
            
            # Contact info
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'job_title': self.job_title,
            'company_name': self.company_name,
            'phone': self.phone,
            'linkedin_url': self.linkedin_url,
            
            # Location
            'city': self.city,
            'state': self.state,
            'country': self.country,
            
            # Status
            'status': self.status,
            'processing_status': self.processing_status,
            'processed_by_icps': self.processed_by_icps,
            
            # Timestamps
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
        }


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
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey('leads.id', ondelete='CASCADE'), nullable=False, index=True)
    icp_id = Column(UUID(as_uuid=True), ForeignKey("icps.id", ondelete="CASCADE"), nullable=True, index=True)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("lead_icp_assignments.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Rejection info
    rejection_stage = Column(String(50), nullable=False)
    rejection_reason = Column(String(255), nullable=False)
    rejection_category = Column(String(100), nullable=False)
    failed_criteria = Column(JSONB, default=[])
    rejection_details = Column(JSONB)  # ✅ Already added
    can_be_overridden = Column(Boolean, default=False)  # ✅ ADD THIS
    
    # Timestamps
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
    icp_id = Column(UUID(as_uuid=True), ForeignKey("icps.id", ondelete="CASCADE"), nullable=True, index=True)
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

class EnrichmentCache(Base):
    """
    Cache for enrichment API results
    
    Purpose:
    - Reduce API costs by 85% (90-day cache, target 85% hit rate)
    - Speed up enrichment (instant cache hits vs 1-3s API calls)
    - Track API usage and costs per tenant
    
    Example:
    - First lead from "techcorp.com" → SerpApi call ($0.002) → cache
    - Next 100 leads from "techcorp.com" → instant cache hit ($0.000)
    - Savings: $0.20 per company!
    """
    __tablename__ = 'enrichment_cache'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Tenant isolation
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False, index=True)
    
    # Cache identification
    cache_type = Column(String(50), nullable=False, index=True)  
    # Options: 'company_enrichment', 'email_verification', 'tech_stack'
    
    cache_key_hash = Column(String(64), nullable=False, index=True)  
    # SHA256 hash of domain/email (e.g., hash('techcorp.com'))
    
    # Cached data
    enrichment_data = Column(JSONB, nullable=False, default=dict)
    # Stores: {company_description, tech_stack, employee_count, etc.}
    
    # Provider tracking
    provider = Column(String(100))  
    # Options: 'serpapi', 'wappalyzer', 'google_maps', 'serpapi,wappalyzer'
    
    # Cost tracking
    api_cost = Column(Numeric(10, 4), default=Decimal('0.0000'))  
    # Cost in dollars (e.g., 0.0020 for SerpApi)
    
    # Quality metrics
    completeness_score = Column(Numeric(5, 2))  
    # 0-100 score (how many fields were enriched)
    
    # Usage tracking
    hit_count = Column(Integer, default=0)  
    # How many times this cache entry was used
    
    # Expiration
    expires_at = Column(DateTime, nullable=False, index=True)  
    # 90 days from creation
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Composite index for fast lookups
    __table_args__ = (
        Index(
            'idx_enrichment_cache_lookup',
            'tenant_id', 'cache_type', 'cache_key_hash'
        ),
        Index('idx_enrichment_cache_expires', 'expires_at'),
    )
    
    # Relationships
    tenant = relationship("Tenant", back_populates="enrichment_caches")

    def __repr__(self):
        return f"<EnrichmentCache(type={self.cache_type}, provider={self.provider},"

class ScrapingRun(Base):
    """
    Tracks each scraper execution
    """
    __tablename__ = "scraping_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    data_source_id = Column(UUID(as_uuid=True), ForeignKey("data_sources.id"), nullable=False, index=True)
    
    # Run status
    status = Column(String(50), nullable=False, default="pending", index=True)
    # status: 'pending', 'running', 'completed', 'failed', 'cancelled'
    
    trigger_type = Column(String(50), nullable=False, default="manual")
    # trigger_type: 'manual', 'scheduled', 'webhook', 'api'
    
    # Timing
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    
    # Results
    leads_found = Column(Integer, default=0)
    leads_saved = Column(Integer, default=0)
    leads_duplicates = Column(Integer, default=0)
    leads_invalid = Column(Integer, default=0)
    
    # Error tracking
    error_message = Column(Text)
    error_details = Column(JSONB)
    
    # Scraper stats (for LinkedIn scraping)
    pages_scraped = Column(Integer, default=0)
    requests_made = Column(Integer, default=0)
    requests_failed = Column(Integer, default=0)
    proxy_errors = Column(Integer, default=0)
    captcha_hits = Column(Integer, default=0)
    
    # API stats (for Apollo)
    api_calls = Column(Integer, default=0)
    api_credits_used = Column(Integer, default=0)
    
    # Configuration snapshot
    config_snapshot = Column(JSONB, default={})
    
    # Metadata
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    # Relationships
    data_source = relationship("DataSource", back_populates="scraping_runs")
    logs = relationship("ScrapingLog", back_populates="run", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ScrapingRun {self.id} - {self.status}>"


class ScrapingLog(Base):
    """
    Detailed logs for each scraping run
    """
    __tablename__ = "scraping_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    scraping_run_id = Column(UUID(as_uuid=True), ForeignKey("scraping_runs.id"), nullable=False, index=True)
    
    # Log entry
    level = Column(String(20), nullable=False, default="info", index=True)
    # level: 'debug', 'info', 'warning', 'error'
    
    message = Column(Text, nullable=False)
    details = Column(JSONB, default={})
    
    # Context
    url = Column(Text)
    page_number = Column(Integer)
    lead_email = Column(String(255))
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    
    # Relationships
    run = relationship("ScrapingRun", back_populates="logs")
    
    def __repr__(self):
        return f"<ScrapingLog {self.level}: {self.message[:50]}>"


class ScrapingSchedule(Base):
    """
    Scheduling configuration for automated scraping
    """
    __tablename__ = "scraping_schedules"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    data_source_id = Column(UUID(as_uuid=True), ForeignKey("data_sources.id"), nullable=False, index=True)
    
    enabled = Column(Boolean, default=True, index=True)
    
    # Schedule configuration
    frequency = Column(String(50), nullable=False)
    # frequency: 'hourly', 'daily', 'weekly', 'monthly', 'custom'
    
    cron_expression = Column(String(100))
    # Examples: "0 9 * * *" (daily at 9 AM), "0 */4 * * *" (every 4 hours)
    
    timezone = Column(String(50), default="UTC")
    
    # Run constraints
    max_concurrent_runs = Column(Integer, default=1)
    retry_on_failure = Column(Boolean, default=True)
    max_retries = Column(Integer, default=3)
    
    # Next/last run tracking
    next_run_at = Column(DateTime(timezone=True), index=True)
    last_run_at = Column(DateTime(timezone=True))
    last_run_status = Column(String(50))
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    # Relationships
    data_source = relationship("DataSource", back_populates="schedules")
    
    def __repr__(self):
        return f"<ScrapingSchedule {self.frequency} - {self.enabled}>"


# Update DataSource model to include scraper fields