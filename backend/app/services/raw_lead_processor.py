# backend/app/services/raw_lead_processor.py - UPDATED FOR NEW SCHEMA
"""
Raw Lead Processor Service - Updated for Multi-ICP Assignment with new schema

KEY CHANGES:
1. Uses individual columns instead of raw_data/mapped_data
2. Extracts fields directly from RawLead columns
3. Uses scraped_data JSONB for complete data
4. Still supports multi-ICP processing
"""

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, not_
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
import logging

from app.models import (
    RawLead, Lead, LeadICPAssignment, ICP, 
    ScoringRule, RawLeadProcessing
)

logger = logging.getLogger(__name__)


class RawLeadProcessor:
    """Processes raw leads from scrapers with multi-ICP assignment support."""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ========================================
    # PROCESS SINGLE RAW LEAD FOR ICP
    # ========================================
    
    async def process_raw_lead_for_icp(
        self,
        raw_lead: RawLead,
        icp: ICP,
        scoring_rules: List[ScoringRule]
    ) -> Dict[str, Any]:
        """
        Process one raw lead for one ICP (multi-ICP compatible).
        Can be called multiple times for different ICPs.
        
        Returns:
            {
                "status": "processed" | "already_processed" | "skipped" | "failed",
                "lead_id": uuid,
                "assignment_id": uuid,
                "is_new_lead": bool,
                "is_new_assignment": bool,
                "fit_score": float,
                "fit_percentage": float,
                "decision": str
            }
        """
        
        start_time = datetime.utcnow()
        
        try:
            # 1. Check if already processed for this ICP
            if raw_lead.is_processed_by_icp(str(icp.id)):
                return {
                    "status": "already_processed",
                    "message": f"Raw lead already processed for ICP {icp.name}"
                }
            
            # 2. Extract lead data from raw lead (uses columns now)
            lead_data = self._extract_lead_data(raw_lead)
            
            if not lead_data.get('email'):
                return {
                    "status": "skipped",
                    "message": "No email found in raw lead"
                }
            
            # 3. Get or create universal lead (by email)
            lead, is_new_lead = await self._get_or_create_lead(
                raw_lead.tenant_id,
                lead_data
            )
            
            # 4. Score lead against ICP rules
            score_result = self._score_lead(lead, icp, scoring_rules)
            
            # 5. Determine status based on thresholds
            status = self._determine_status(
                score_result['percentage'],
                icp.auto_approve_threshold or 80.0,
                icp.review_threshold or 60.0,
                icp.auto_reject_threshold or 40.0
            )
            
            # 6. Create or update assignment
            assignment, is_new_assignment = await self._get_or_create_assignment(
                lead_id=lead.id,
                icp_id=icp.id,
                tenant_id=raw_lead.tenant_id,
                fit_score=score_result['total_score'],
                fit_percentage=score_result['percentage'],
                status=status,
                scoring_details=score_result['details']
            )
            
            # 7. Mark raw lead as processed by this ICP
            raw_lead.mark_processed_by_icp(str(icp.id))
            raw_lead.status = 'processed'
            raw_lead.processed_at = datetime.utcnow()
            raw_lead.lead_id = lead.id  # Link to created lead
            
            # 8. Create processing record
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            processing = RawLeadProcessing(
                raw_lead_id=raw_lead.id,
                icp_id=icp.id,
                result_lead_id=lead.id,
                assignment_id=assignment.id,
                status='completed',
                score=score_result['total_score'],
                decision=status,
                processing_duration_ms=duration_ms
            )
            self.db.add(processing)
            self.db.commit()
            
            logger.info(
                f"Processed raw lead {raw_lead.id} for ICP {icp.name}: "
                f"lead={lead.email}, score={score_result['percentage']}%, status={status}"
            )
            
            return {
                "status": "processed",
                "lead_id": str(lead.id),
                "assignment_id": str(assignment.id),
                "is_new_lead": is_new_lead,
                "is_new_assignment": is_new_assignment,
                "fit_score": score_result['total_score'],
                "fit_percentage": score_result['percentage'],
                "decision": status
            }
            
        except Exception as e:
            logger.error(f"Error processing raw lead {raw_lead.id}: {e}", exc_info=True)
            
            # Update raw lead status
            raw_lead.processing_status = 'failed'
            raw_lead.error_message = str(e)
            
            # Create failed processing record
            processing = RawLeadProcessing(
                raw_lead_id=raw_lead.id,
                icp_id=icp.id,
                status='failed',
                error_message=str(e)
            )
            self.db.add(processing)
            self.db.commit()
            
            return {
                "status": "failed",
                "message": str(e)
            }
    
    # ========================================
    # BATCH PROCESSING FOR ICP
    # ========================================
    
    async def process_universal_bucket_for_icp(
        self,
        icp_id: UUID,
        tenant_id: UUID,
        limit: int = 1000,
        force_reprocess: bool = False
    ) -> Dict[str, Any]:
        """
        Process universal raw bucket for a specific ICP.
        Gets unprocessed leads and creates ICP assignments.
        """
        
        # Get ICP with scoring rules
        icp = self.db.query(ICP).filter(ICP.id == icp_id).first()
        if not icp:
            raise ValueError(f"ICP {icp_id} not found")
        
        scoring_rules = self.db.query(ScoringRule).filter(
            ScoringRule.icp_id == icp_id,
            ScoringRule.is_active == True
        ).all()
        
        # Get unprocessed raw leads
        if force_reprocess:
            # Get all leads
            query = self.db.query(RawLead).filter(
                RawLead.tenant_id == tenant_id,
                RawLead.status.in_(['pending', 'processed'])
            ).limit(limit)
        else:
            # Get only leads not yet processed by this ICP
            # Check if icp_id is in processed_by_icps array
            from sqlalchemy.dialects.postgresql import JSONB
            from sqlalchemy import cast, type_coerce
            
            query = self.db.query(RawLead).filter(
                RawLead.tenant_id == tenant_id,
                RawLead.status.in_(['pending', 'processed']),
                ~RawLead.processed_by_icps.op('@>')([str(icp_id)])  # PostgreSQL JSONB contains
            ).limit(limit)
        
        raw_leads = query.all()
        
        logger.info(f"Processing {len(raw_leads)} raw leads for ICP {icp.name}")
        
        # Process each lead
        stats = {
            'processed': 0,
            'qualified': 0,
            'review': 0,
            'rejected': 0,
            'failed': 0,
            'already_processed': 0,
            'skipped': 0
        }
        
        for raw_lead in raw_leads:
            result = await self.process_raw_lead_for_icp(raw_lead, icp, scoring_rules)
            
            if result['status'] == 'processed':
                stats['processed'] += 1
                decision = result.get('decision')
                if decision == 'qualified':
                    stats['qualified'] += 1
                elif decision == 'pending_review':
                    stats['review'] += 1
                elif decision == 'rejected':
                    stats['rejected'] += 1
            elif result['status'] == 'failed':
                stats['failed'] += 1
            elif result['status'] == 'already_processed':
                stats['already_processed'] += 1
            elif result['status'] == 'skipped':
                stats['skipped'] += 1
            
            # Commit in batches
            if stats['processed'] % 100 == 0:
                self.db.commit()
        
        # Final commit
        self.db.commit()
        
        logger.info(f"Bucket processing completed for ICP {icp.name}: {stats}")
        
        return stats
    
    # ========================================
    # HELPER METHODS - UPDATED FOR NEW SCHEMA
    # ========================================
    
    def _extract_lead_data(self, raw_lead: RawLead) -> Dict:
        """
        Extract lead data from raw lead.
        UPDATED: Uses individual columns instead of raw_data/mapped_data
        """
        return {
            # Contact info (from columns)
            "email": raw_lead.email,
            "first_name": raw_lead.first_name,
            "last_name": raw_lead.last_name,
            "phone": raw_lead.phone,
            "linkedin_url": raw_lead.linkedin_url,
            
            # Professional info
            "job_title": raw_lead.job_title,
            
            # Company info
            "company_name": raw_lead.company_name,
            "company_website": raw_lead.company_website,
            "company_domain": raw_lead.company_domain,
            "company_industry": raw_lead.company_industry,
            "company_size": raw_lead.company_size,
            
            # Location info
            "city": raw_lead.city,
            "state": raw_lead.state,
            "country": raw_lead.country,
            "zip_code": raw_lead.zip_code,
            
            # Source tracking
            "source_name": raw_lead.source_name,
            "source_url": raw_lead.source_url,
            "data_source_id": raw_lead.data_source_id,
            "acquisition_timestamp": raw_lead.created_at,
            
            # Additional data from scraped_data JSONB if needed
            "scraped_data": raw_lead.scraped_data or {}
        }
    
    async def _get_or_create_lead(
        self,
        tenant_id: UUID,
        lead_data: Dict
    ) -> tuple[Lead, bool]:
        """
        Get existing lead by email or create new one.
        Returns (lead, is_new)
        
        ✅ KEY FUNCTION: Ensures one lead per email
        """
        email = lead_data.get('email')
        if not email:
            raise ValueError("Email is required")
        
        # Find existing lead by email
        lead = self.db.query(Lead).filter(
            Lead.tenant_id == tenant_id,
            Lead.email == email
        ).first()
        
        if lead:
            # Update lead with any new data (merge strategy)
            for key, value in lead_data.items():
                if key == 'scraped_data':
                    continue  # Skip scraped_data, handled separately
                    
                if value and hasattr(lead, key):
                    current_value = getattr(lead, key)
                    # Only update if current value is None/empty
                    if not current_value:
                        setattr(lead, key, value)
            
            lead.updated_at = datetime.utcnow()
            logger.info(f"Found existing lead: {email}")
            return lead, False  # existing lead
        
        # Create new lead (exclude scraped_data from direct assignment)
        lead_create_data = {k: v for k, v in lead_data.items() if k != 'scraped_data'}
        
        lead = Lead(
            tenant_id=tenant_id,
            **lead_create_data
        )
        self.db.add(lead)
        self.db.flush()  # Get ID
        
        logger.info(f"Created new lead: {email}")
        return lead, True  # new lead
    
    async def _get_or_create_assignment(
        self,
        lead_id: UUID,
        icp_id: UUID,
        tenant_id: UUID,
        fit_score: float,
        fit_percentage: float,
        status: str,
        scoring_details: Dict = None
    ) -> tuple[LeadICPAssignment, bool]:
        """
        Get existing assignment or create new one.
        Returns (assignment, is_new)
        
        ✅ KEY FUNCTION: Supports multi-ICP assignments
        """
        # Find existing assignment
        assignment = self.db.query(LeadICPAssignment).filter(
            LeadICPAssignment.lead_id == lead_id,
            LeadICPAssignment.icp_id == icp_id
        ).first()
        
        if assignment:
            # Update existing assignment with new score
            assignment.fit_score = fit_score
            assignment.fit_score_percentage = fit_percentage
            assignment.status = status
            assignment.scoring_details = scoring_details
            assignment.updated_at = datetime.utcnow()
            
            # Set qualified_at if newly qualified
            if status == 'qualified' and not assignment.qualified_at:
                assignment.qualified_at = datetime.utcnow()
            
            logger.info(f"Updated assignment for lead {lead_id} and ICP {icp_id}")
            return assignment, False
        
        # Create new assignment
        assignment = LeadICPAssignment(
            lead_id=lead_id,
            icp_id=icp_id,
            tenant_id=tenant_id,
            fit_score=fit_score,
            fit_score_percentage=fit_percentage,
            status=status,
            scoring_details=scoring_details or {},
            qualified_at=datetime.utcnow() if status == 'qualified' else None
        )
        self.db.add(assignment)
        self.db.flush()
        
        logger.info(f"Created new assignment for lead {lead_id} and ICP {icp_id}")
        return assignment, True
    
    def _score_lead(
        self,
        lead: Lead,
        icp: ICP,
        scoring_rules: List[ScoringRule]
    ) -> Dict:
        """Score a lead against ICP rules"""
        total_score = 0
        max_possible = sum(rule.weight for rule in scoring_rules if rule.is_active)
        matched_rules = []
        
        for rule in scoring_rules:
            if not rule.is_active:
                continue
            
            # Get field value
            field_value = getattr(lead, rule.field_name, None)
            
            # Check if rule matches
            matches = self._check_rule_match(rule, field_value)
            
            if matches:
                total_score += rule.weight
                matched_rules.append({
                    "rule_id": str(rule.id),
                    "field": rule.field_name,
                    "rule_type": rule.rule_type,
                    "weight": rule.weight,
                    "matched_value": str(field_value) if field_value else None
                })
        
        percentage = (total_score / max_possible * 100) if max_possible > 0 else 0
        
        return {
            "total_score": total_score,
            "max_possible": max_possible,
            "percentage": round(percentage, 2),
            "matched_rules": matched_rules,
            "details": {
                "rules_evaluated": len(scoring_rules),
                "rules_matched": len(matched_rules),
                "matched_rules": matched_rules
            }
        }
    
    def _check_rule_match(self, rule: ScoringRule, field_value) -> bool:
        """Check if a field value matches a scoring rule"""
        import re
        
        if field_value is None:
            return rule.rule_type == 'exists' and rule.condition.get('require_exists') == False
        
        condition = rule.condition or {}
        
        if rule.rule_type == 'match':
            expected = condition.get('value')
            if not expected:
                return False
            case_sensitive = condition.get('case_sensitive', False)
            if case_sensitive:
                return str(field_value) == str(expected)
            else:
                return str(field_value).lower() == str(expected).lower()
        
        elif rule.rule_type == 'range':
            try:
                value = float(field_value)
                min_val = float(condition.get('min', float('-inf')))
                max_val = float(condition.get('max', float('inf')))
                return min_val <= value <= max_val
            except (ValueError, TypeError):
                return False
        
        elif rule.rule_type == 'contains':
            search_value = condition.get('value', '')
            if not search_value:
                return False
            field_str = str(field_value).lower()
            search_values = [v.strip().lower() for v in search_value.split('|')]
            return any(sv in field_str for sv in search_values)
        
        elif rule.rule_type == 'exists':
            return field_value is not None and str(field_value).strip() != ''
        
        elif rule.rule_type == 'regex':
            pattern = condition.get('pattern')
            if not pattern:
                return False
            try:
                return bool(re.search(pattern, str(field_value), re.IGNORECASE))
            except re.error:
                return False
        
        return False
    
    def _determine_status(
        self,
        score_percentage: float,
        auto_approve_threshold: float,
        review_threshold: float,
        auto_reject_threshold: float
    ) -> str:
        """Determine lead status based on score and thresholds"""
        
        if score_percentage >= auto_approve_threshold:
            return 'qualified'
        elif score_percentage >= review_threshold:
            return 'pending_review'
        else:
            return 'rejected'
    
    # ========================================
    # LIST AND STATS METHODS
    # ========================================
    
    async def list_raw_leads(
        self,
        tenant_id: UUID,
        icp_id: Optional[UUID] = None,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 50
    ) -> Dict[str, Any]:
        """List raw leads with filters"""
        query = self.db.query(RawLead).filter(RawLead.tenant_id == tenant_id)
        
        if icp_id:
            query = query.filter(RawLead.icp_id == icp_id)
        
        if status:
            query = query.filter(RawLead.status == status)
        
        total = query.count()
        offset = (page - 1) * limit
        raw_leads = query.order_by(RawLead.created_at.desc()).offset(offset).limit(limit).all()
        
        return {
            "raw_leads": [raw_lead.to_dict() for raw_lead in raw_leads],
            "total": total,
            "page": page,
            "page_size": limit,
            "total_pages": (total + limit - 1) // limit
        }
    
    async def get_summary_stats(
        self,
        tenant_id: UUID,
        icp_id: Optional[UUID] = None,
        period_days: int = 30
    ) -> Dict:
        """Get summary statistics for raw leads"""
        cutoff_date = datetime.utcnow() - timedelta(days=period_days)
        
        query = self.db.query(RawLead).filter(
            RawLead.tenant_id == tenant_id,
            RawLead.created_at >= cutoff_date
        )
        
        if icp_id:
            query = query.filter(RawLead.icp_id == icp_id)
        
        # Count by status
        total_by_status = {}
        for status in ['pending', 'processing', 'processed', 'failed']:
            count = query.filter(RawLead.status == status).count()
            total_by_status[status] = count
        
        return {
            "total_by_status": total_by_status,
            "period_days": period_days,
            "total": sum(total_by_status.values())
        }