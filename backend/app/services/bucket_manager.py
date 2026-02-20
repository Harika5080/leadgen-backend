"""
Bucket Manager Service
Handles lead bucket operations, filtering, and analytics
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, cast, String
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta

from app.models import Lead, LeadProcessingStage, ICP, Source
from app.schemas import (
    BucketStats,
    LeadInBucket,
    BucketLeadList,
    BucketFlowAnalytics,
)


class BucketManager:
    """Manages lead bucket operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def get_bucket_stats(self, icp_id: UUID) -> List[BucketStats]:
        """Get statistics for all buckets in an ICP."""
        buckets = ['raw_landing', 'scored', 'enriched', 'verified', 
                   'approved', 'pending_review', 'rejected']
        
        stats = []
        
        for bucket in buckets:
            # Count leads in bucket
            lead_count = self.db.query(func.count(Lead.id)).filter(
                Lead.icp_id == icp_id,
                Lead.current_bucket == bucket
            ).scalar() or 0
            
            # Average score
            avg_score = self.db.query(func.avg(Lead.fit_score)).filter(
                Lead.icp_id == icp_id,
                Lead.current_bucket == bucket,
                Lead.fit_score.isnot(None)
            ).scalar()
            
            # Average duration in bucket
            avg_duration = self.db.query(
                func.avg(
                    func.extract('epoch', func.now() - Lead.bucket_entered_at)
                )
            ).filter(
                Lead.icp_id == icp_id,
                Lead.current_bucket == bucket,
                Lead.bucket_entered_at.isnot(None)
            ).scalar()
            
            stats.append(BucketStats(
                bucket=bucket,
                lead_count=lead_count,
                avg_score=float(avg_score) if avg_score else None,
                avg_duration_seconds=float(avg_duration) if avg_duration else None
            ))
        
        return stats
    
    async def get_filtered_leads(
        self,
        icp_id: UUID,
        bucket: str,
        search: Optional[str] = None,
        company_size: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        score_min: Optional[float] = None,
        score_max: Optional[float] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        limit: int = 50
    ) -> BucketLeadList:
        """Get filtered and paginated leads in a bucket."""
        query = self.db.query(Lead).filter(
            Lead.icp_id == icp_id,
            Lead.current_bucket == bucket
        )
        
        # Apply filters
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Lead.email.ilike(search_term),
                    Lead.first_name.ilike(search_term),
                    Lead.last_name.ilike(search_term),
                    Lead.company_name.ilike(search_term)
                )
            )
        
        if company_size:
            query = query.filter(Lead.company_size == company_size)
        
        if city:
            query = query.filter(Lead.city.ilike(f"%{city}%"))
        
        if state:
            query = query.filter(Lead.state == state)
        
        if country:
            query = query.filter(Lead.country == country)
        
        if score_min is not None:
            query = query.filter(Lead.fit_score >= score_min)
        
        if score_max is not None:
            query = query.filter(Lead.fit_score <= score_max)
        
        if date_from:
            query = query.filter(Lead.created_at >= date_from)
        
        if date_to:
            query = query.filter(Lead.created_at <= date_to)
        
        # Get total count
        total = query.count()
        
        # Paginate
        offset = (page - 1) * limit
        leads = query.order_by(Lead.created_at.desc()).offset(offset).limit(limit).all()
        
        # Convert to LeadInBucket schema
        lead_list = []
        for lead in leads:
            # Get source name
            source_name = None
            if lead.source_id:
                source = self.db.query(Source).filter(Source.id == lead.source_id).first()
                if source:
                    source_name = source.name
            
            lead_list.append(LeadInBucket(
                id=lead.id,
                email=lead.email,
                first_name=lead.first_name,
                last_name=lead.last_name,
                phone=lead.phone,
                job_title=lead.job_title,
                linkedin_url=lead.linkedin_url,
                company_name=lead.company_name,
                company_website=lead.company_website,
                company_domain=lead.company_domain,
                company_industry=lead.company_industry,
                company_size=lead.company_size,
                company_revenue_estimate=lead.company_revenue_estimate,
                address=lead.address,
                city=lead.city,
                state=lead.state,
                country=lead.country,
                zip_code=lead.zip_code,
                company_address=lead.company_address,
                company_city=lead.company_city,
                company_state=lead.company_state,
                company_country=lead.company_country,
                company_phone=lead.company_phone,
                current_bucket=lead.current_bucket,
                bucket_entered_at=lead.bucket_entered_at,
                fit_score=float(lead.fit_score) if lead.fit_score else None,
                email_verified=lead.email_verified,
                email_deliverability_score=float(lead.email_deliverability_score) if lead.email_deliverability_score else None,
                enrichment_completed=lead.enrichment_completed,
                verification_completed=lead.verification_completed,
                source_name=source_name,
                acquisition_timestamp=lead.acquisition_timestamp,
                created_at=lead.created_at
            ))
        
        return BucketLeadList(
            leads=lead_list,
            total=total,
            page=page,
            page_size=limit,
            total_pages=(total + limit - 1) // limit
        )
    
    async def move_lead_to_bucket(
        self,
        lead_id: UUID,
        target_bucket: str,
        reason: Optional[str] = None,
        user_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Move a lead to a different bucket and track the transition."""
        lead = self.db.query(Lead).filter(Lead.id == lead_id).first()
        
        if not lead:
            raise ValueError("Lead not found")
        
        # Validate target bucket
        valid_buckets = ['raw_landing', 'scored', 'enriched', 'verified', 
                         'approved', 'pending_review', 'rejected']
        if target_bucket not in valid_buckets:
            raise ValueError(f"Invalid target bucket: {target_bucket}")
        
        old_bucket = lead.current_bucket
        
        # Update lead bucket
        lead.current_bucket = target_bucket
        lead.bucket_entered_at = datetime.utcnow()
        lead.updated_at = datetime.utcnow()
        
        # Create processing stage record
        stage = LeadProcessingStage(
            lead_id=lead_id,
            stage_name=target_bucket,
            entered_at=datetime.utcnow(),
            metadata=metadata or {}
        )
        
        if reason:
            stage.metadata['move_reason'] = reason
        
        if user_id:
            stage.metadata['moved_by_user_id'] = str(user_id)
        
        stage.metadata['previous_bucket'] = old_bucket
        
        self.db.add(stage)
        self.db.commit()
        self.db.refresh(lead)
        
        return {
            "moved_at": stage.entered_at,
            "old_bucket": old_bucket,
            "new_bucket": target_bucket
        }
    
    async def get_flow_analytics(
        self,
        icp_id: UUID,
        period_days: int = 30
    ) -> BucketFlowAnalytics:
        """Get analytics for lead flow through buckets."""
        cutoff_date = datetime.utcnow() - timedelta(days=period_days)
        
        # Get transition counts between buckets
        transitions = self.db.query(
            LeadProcessingStage.stage_name,
            func.count(LeadProcessingStage.id).label('count')
        ).join(Lead).filter(
            Lead.icp_id == icp_id,
            LeadProcessingStage.entered_at >= cutoff_date
        ).group_by(LeadProcessingStage.stage_name).all()
        
        # Calculate conversion rates
        conversion_rates = {}
        for stage_name, count in transitions:
            conversion_rates[stage_name] = count
        
        # Get average durations
        avg_durations = {}
        for stage in ['scored', 'enriched', 'verified', 'approved', 'pending_review']:
            avg_duration = self.db.query(
                func.avg(
                    func.extract('epoch', LeadProcessingStage.exited_at - LeadProcessingStage.entered_at)
                )
            ).join(Lead).filter(
                Lead.icp_id == icp_id,
                LeadProcessingStage.stage_name == stage,
                LeadProcessingStage.entered_at >= cutoff_date,
                LeadProcessingStage.exited_at.isnot(None)
            ).scalar()
            
            avg_durations[stage] = float(avg_duration) if avg_duration else 0.0
        
        # Rejection stats
        rejected_count = self.db.query(func.count(Lead.id)).filter(
            Lead.icp_id == icp_id,
            Lead.current_bucket == 'rejected',
            Lead.created_at >= cutoff_date
        ).scalar() or 0
        
        # Top rejection reasons
        rejection_reasons = self.db.query(
            cast(LeadProcessingStage.metadata['move_reason'], String).label('reason'),
            func.count(LeadProcessingStage.id).label('count')
        ).join(Lead).filter(
            Lead.icp_id == icp_id,
            LeadProcessingStage.stage_name == 'rejected',
            LeadProcessingStage.entered_at >= cutoff_date
        ).group_by('reason').order_by(func.count(LeadProcessingStage.id).desc()).limit(5).all()
        
        rejection_reasons_dict = {
            reason: count for reason, count in rejection_reasons if reason
        }
        
        # Volume metrics
        total_leads = self.db.query(func.count(Lead.id)).filter(
            Lead.icp_id == icp_id,
            Lead.created_at >= cutoff_date
        ).scalar() or 0
        
        approved_count = self.db.query(func.count(Lead.id)).filter(
            Lead.icp_id == icp_id,
            Lead.current_bucket == 'approved',
            Lead.created_at >= cutoff_date
        ).scalar() or 0
        
        pending_review_count = self.db.query(func.count(Lead.id)).filter(
            Lead.icp_id == icp_id,
            Lead.current_bucket == 'pending_review'
        ).scalar() or 0
        
        return BucketFlowAnalytics(
            conversion_rates=conversion_rates,
            avg_bucket_durations=avg_durations,
            rejection_count=rejected_count,
            rejection_reasons=rejection_reasons_dict,
            total_leads_period=total_leads,
            approved_count=approved_count,
            pending_review_count=pending_review_count
        )