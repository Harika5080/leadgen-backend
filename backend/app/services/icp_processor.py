"""
ICP Processor Service - Phase 3
================================
This service handles:
1. Matching raw leads against all active ICPs
2. Calculating fit scores based on ICP rules
3. Creating lead-ICP assignments
4. Auto-assigning leads to appropriate buckets
"""

from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, not_, exists
from datetime import datetime
import logging

from app.models import Lead, ICP, LeadICPAssignment, Tenant
from app.schemas import LeadProcessingStatus

logger = logging.getLogger(__name__)


class ICPProcessor:
    """
    Processes leads against ICP scoring rules to create assignments
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def process_raw_leads(
        self, 
        tenant_id: str,
        icp_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Dict:
        """
        Process raw leads for a tenant
        
        Args:
            tenant_id: Tenant to process leads for
            icp_id: Optional - process for specific ICP only
            limit: Optional - limit number of leads to process
            
        Returns:
            Dictionary with processing statistics
        """
        logger.info(f"Starting ICP processing for tenant {tenant_id}")
        
        # Get all active ICPs for this tenant
        icps_query = self.db.query(ICP).filter(
            ICP.tenant_id == tenant_id,
            ICP.is_active == True
        )
        
        if icp_id:
            icps_query = icps_query.filter(ICP.id == icp_id)
        
        icps = icps_query.all()
        
        if not icps:
            logger.warning(f"No active ICPs found for tenant {tenant_id}")
            return {
                "status": "no_icps",
                "message": "No active ICPs found",
                "leads_processed": 0
            }
        
        # Get raw leads (not yet processed)
        raw_leads_query = self.db.query(Lead).filter(
            Lead.tenant_id == tenant_id,
            or_(
                Lead.processing_status == 'raw',
                Lead.processing_status == None
            )
        )
        
        if limit:
            raw_leads_query = raw_leads_query.limit(limit)
        
        raw_leads = raw_leads_query.all()
        
        if not raw_leads:
            logger.info(f"No raw leads found for tenant {tenant_id}")
            return {
                "status": "no_leads",
                "message": "No raw leads to process",
                "leads_processed": 0
            }
        
        # Process each lead
        stats = {
            "leads_processed": 0,
            "total_assignments": 0,
            "by_icp": {},
            "errors": []
        }
        
        for lead in raw_leads:
            try:
                # Mark as processing
                lead.processing_status = 'processing'
                self.db.commit()
                
                # Process against all ICPs
                assignments = await self.process_lead_against_icps(lead, icps)
                
                # Update lead status
                lead.icp_match_count = len(assignments)
                lead.processing_status = 'processed'
                lead.last_processed_at = datetime.utcnow()
                lead.processing_error = None
                
                stats["leads_processed"] += 1
                stats["total_assignments"] += len(assignments)
                
                # Track per-ICP stats
                for assignment in assignments:
                    icp_name = assignment.icp.name
                    if icp_name not in stats["by_icp"]:
                        stats["by_icp"][icp_name] = 0
                    stats["by_icp"][icp_name] += 1
                
                self.db.commit()
                
            except Exception as e:
                logger.error(f"Error processing lead {lead.id}: {str(e)}")
                lead.processing_status = 'error'
                lead.processing_error = str(e)
                lead.last_processed_at = datetime.utcnow()
                self.db.commit()
                
                stats["errors"].append({
                    "lead_id": str(lead.id),
                    "error": str(e)
                })
        
        # Update last_processed_at for each ICP
        for icp in icps:
            icp.last_processed_at = datetime.utcnow()
        self.db.commit()
        
        logger.info(f"Processing complete: {stats}")
        return stats
    
    async def process_lead_against_icps(
        self, 
        lead: Lead, 
        icps: List[ICP]
    ) -> List[LeadICPAssignment]:
        """
        Process a single lead against multiple ICPs
        
        Args:
            lead: Lead to process
            icps: List of ICPs to check against
            
        Returns:
            List of created LeadICPAssignment objects
        """
        assignments = []
        
        for icp in icps:
            # Check if already assigned
            existing = self.db.query(LeadICPAssignment).filter(
                LeadICPAssignment.lead_id == lead.id,
                LeadICPAssignment.icp_id == icp.id
            ).first()
            
            if existing:
                logger.debug(f"Lead {lead.id} already assigned to ICP {icp.id}")
                continue
            
            # Check if lead matches ICP filters
            if not icp.matches_filters(lead):
                logger.debug(f"Lead {lead.id} does not match filters for ICP {icp.id}")
                continue
            
            # Calculate fit score
            fit_score = icp.calculate_fit_score(lead)
            
            # Get scoring rules for thresholds
            rules = icp.get_scoring_rules()
            thresholds = rules.get('thresholds', {})
            
            # Determine bucket based on score
            bucket = self._determine_bucket(fit_score, thresholds)
            
            # Determine status based on bucket
            status = self._bucket_to_status(bucket)
            
            # Create scoring details
            scoring_details = self._create_scoring_details(lead, icp, fit_score, rules)
            
            # Create assignment
            assignment = LeadICPAssignment(
                lead_id=lead.id,
                icp_id=icp.id,
                tenant_id=lead.tenant_id,
                fit_score_percentage=fit_score,
                bucket=bucket,
                status=status,
                scoring_details=scoring_details,
                scoring_version=1,
                processed_at=datetime.utcnow()
            )
            
            self.db.add(assignment)
            assignments.append(assignment)
            
            logger.info(f"Created assignment: Lead {lead.id} → ICP {icp.id} (score: {fit_score}%, bucket: {bucket})")
        
        return assignments
    
    def _determine_bucket(self, fit_score: float, thresholds: Dict) -> str:
        """
        Determine which bucket a lead should go to based on fit score
        
        Args:
            fit_score: Fit score percentage (0-100)
            thresholds: Dictionary with auto_qualify, review_required thresholds
            
        Returns:
            Bucket name (string)
        """
        auto_qualify = thresholds.get('auto_qualify', 85)
        review_required = thresholds.get('review_required', 60)
        
        if fit_score >= auto_qualify:
            return 'qualified'  # High score - auto-qualify
        elif fit_score >= review_required:
            return 'review'  # Medium score - needs review
        else:
            return 'rejected'  # Low score - auto-reject
    
    def _bucket_to_status(self, bucket: str) -> str:
        """
        Convert bucket to status for backward compatibility
        
        Args:
            bucket: Bucket name
            
        Returns:
            Status string
        """
        bucket_to_status_map = {
            'new': 'pending_review',
            'score': 'pending_review',
            'enriched': 'pending_review',
            'verified': 'pending_review',
            'review': 'pending_review',
            'qualified': 'qualified',
            'rejected': 'rejected',
            'exported': 'exported'
        }
        return bucket_to_status_map.get(bucket, 'pending_review')
    
    def _create_scoring_details(
        self, 
        lead: Lead, 
        icp: ICP, 
        fit_score: float,
        rules: Dict
    ) -> Dict:
        """
        Create detailed breakdown of scoring
        
        Args:
            lead: Lead being scored
            icp: ICP being matched against
            fit_score: Calculated fit score
            rules: ICP scoring rules
            
        Returns:
            Dictionary with scoring breakdown
        """
        filters = rules.get('filters', {})
        weights = rules.get('weights', {})
        required = filters.get('required', {})
        
        # Determine which filters matched
        matched_filters = []
        failed_filters = []
        
        # Job title check
        if required.get('job_titles') and lead.job_title:
            job_title_lower = lead.job_title.lower()
            if any(jt.lower() in job_title_lower for jt in required['job_titles']):
                matched_filters.append('job_title')
            else:
                failed_filters.append('job_title')
        
        # Industry check
        if required.get('industries') and lead.company_industry:
            if lead.company_industry in required['industries']:
                matched_filters.append('industry')
            else:
                failed_filters.append('industry')
        
        # Company size check
        if lead.company_size:
            min_size = required.get('company_size_min', 1)
            max_size = required.get('company_size_max', 999999)
            if min_size <= lead.company_size <= max_size:
                matched_filters.append('company_size')
            else:
                failed_filters.append('company_size')
        
        # Geographic check
        if required.get('countries') and lead.country:
            if lead.country in required['countries']:
                matched_filters.append('geographic')
            else:
                failed_filters.append('geographic')
        
        # Determine recommendation
        thresholds = rules.get('thresholds', {})
        if fit_score >= thresholds.get('auto_qualify', 85):
            recommendation = 'auto_qualify'
        elif fit_score >= thresholds.get('review_required', 60):
            recommendation = 'review_required'
        else:
            recommendation = 'auto_reject'
        
        return {
            "total_score": fit_score,
            "matched_filters": matched_filters,
            "failed_filters": failed_filters,
            "recommendation": recommendation,
            "score_breakdown": {
                "job_title_match": weights.get('job_title_match', 0),
                "company_size_fit": weights.get('company_size_fit', 0),
                "industry_match": weights.get('industry_match', 0),
                "geographic_fit": weights.get('geographic_fit', 0),
                "technographic_signals": weights.get('technographic_signals', 0)
            },
            "scoring_version": 1,
            "processed_at": datetime.utcnow().isoformat(),
            "rules_used": {
                "job_titles": required.get('job_titles', []),
                "industries": required.get('industries', []),
                "company_size_range": [
                    required.get('company_size_min', 1),
                    required.get('company_size_max', 999999)
                ],
                "countries": required.get('countries', [])
            }
        }
    
    async def reprocess_leads_for_icp(
        self, 
        icp_id: str,
        force: bool = False
    ) -> Dict:
        """
        Reprocess all leads for a specific ICP
        Useful when ICP rules change
        
        Args:
            icp_id: ICP to reprocess for
            force: If True, reprocess even already-assigned leads
            
        Returns:
            Processing statistics
        """
        icp = self.db.query(ICP).filter(ICP.id == icp_id).first()
        if not icp:
            return {
                "status": "error",
                "message": "ICP not found"
            }
        
        # Get leads for this tenant
        leads_query = self.db.query(Lead).filter(
            Lead.tenant_id == icp.tenant_id
        )
        
        if not force:
            # Only get leads not yet assigned to this ICP
            leads_query = leads_query.filter(
                not_(exists().where(
                    and_(
                        LeadICPAssignment.lead_id == Lead.id,
                        LeadICPAssignment.icp_id == icp_id
                    )
                ))
            )
        else:
            # Delete existing assignments if force=True
            self.db.query(LeadICPAssignment).filter(
                LeadICPAssignment.icp_id == icp_id
            ).delete()
            self.db.commit()
        
        leads = leads_query.all()
        
        # Process each lead
        stats = {
            "leads_processed": 0,
            "assignments_created": 0,
            "errors": []
        }
        
        for lead in leads:
            try:
                assignments = await self.process_lead_against_icps(lead, [icp])
                stats["leads_processed"] += 1
                stats["assignments_created"] += len(assignments)
                self.db.commit()
            except Exception as e:
                logger.error(f"Error reprocessing lead {lead.id}: {str(e)}")
                stats["errors"].append({
                    "lead_id": str(lead.id),
                    "error": str(e)
                })
        
        icp.last_processed_at = datetime.utcnow()
        self.db.commit()
        
        return stats
    
    def get_processing_stats(self, tenant_id: str) -> Dict:
        """
        Get processing statistics for a tenant
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Statistics dictionary
        """
        total_leads = self.db.query(Lead).filter(
            Lead.tenant_id == tenant_id
        ).count()
        
        raw_leads = self.db.query(Lead).filter(
            Lead.tenant_id == tenant_id,
            or_(
                Lead.processing_status == 'raw',
                Lead.processing_status == None
            )
        ).count()
        
        processed_leads = self.db.query(Lead).filter(
            Lead.tenant_id == tenant_id,
            Lead.processing_status == 'processed'
        ).count()
        
        error_leads = self.db.query(Lead).filter(
            Lead.tenant_id == tenant_id,
            Lead.processing_status == 'error'
        ).count()
        
        orphaned_leads = self.db.query(Lead).filter(
            Lead.tenant_id == tenant_id,
            Lead.processing_status == 'processed',
            Lead.icp_match_count == 0
        ).count()
        
        return {
            "total_leads": total_leads,
            "raw_leads": raw_leads,
            "processed_leads": processed_leads,
            "error_leads": error_leads,
            "orphaned_leads": orphaned_leads,
            "processing_percentage": round((processed_leads / total_leads * 100), 2) if total_leads > 0 else 0
        }