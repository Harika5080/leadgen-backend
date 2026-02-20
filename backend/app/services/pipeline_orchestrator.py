# backend/app/services/pipeline_orchestrator.py - WITH SMART ENRICHMENT
"""
Pipeline Orchestrator with Smart Enrichment Strategy

FEATURES:
- Smart enrichment based on source quality (Apollo vs scrapers)
- Time-based refresh (90 days for high-quality, 60 for medium, 30 for low)
- Skip enrichment for pre-enriched sources (Apollo, Hunter, etc.)
- Enrichment tracking in leads table (not raw_leads)
- Cost optimization through conditional enrichment
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
import logging

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models import (
    Lead,
    LeadICPAssignment,
    RawLead,
    ICP,
    LeadRejectionTracking
)
from app.services.icp_scoring_engine import ICPScoringEngine
from app.services.activity_logger import ActivityLogger
from app.services.enrichment_service import create_enrichment_service
from app.services.email_verification_service import create_verification_service
from app.services.enrichment_strategy import create_enrichment_strategy_service

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    Orchestrates complete lead processing pipeline
    
    Flow:
    1. Create/Find Lead
    2. Create LeadICPAssignment
    3. SMART Enrich (conditional based on source & age)
    4. Score → Verify → Auto-Qualify
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.scoring_engine = ICPScoringEngine(db)
        self.activity_logger = ActivityLogger(db)
        self.strategy_service = create_enrichment_strategy_service()
    
    async def process_raw_lead(
        self,
        raw_lead: RawLead,
        icp: ICP,
        job_id: Optional[str] = None,
        stages_to_run: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Process raw lead for a specific ICP"""
        start_time = datetime.utcnow()
        
        try:
            # Step 1: Create or find lead
            lead, is_new = await self._create_or_find_lead(raw_lead)
            
            # Step 2: Get or create assignment
            assignment = await self._get_or_create_assignment(lead, icp, job_id)
            
            if not is_new and not stages_to_run:
                logger.info(f"Lead {lead.id} already processed for ICP {icp.id}, skipping")
                return {
                    "success": True,
                    "lead_id": str(lead.id),
                    "assignment_id": str(assignment.id),
                    "status": assignment.status,
                    "skipped": True
                }
            
            # Step 3: Run pipeline with smart enrichment
            result = await self._run_pipeline_stages(
                lead=lead,
                assignment=assignment,
                raw_lead=raw_lead,
                icp=icp,
                job_id=job_id,
                stages_to_run=stages_to_run
            )
            
            # Update raw lead tracking
            await self._update_raw_lead_tracking(raw_lead, icp, lead)
            
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"Processed lead {lead.id} for ICP {icp.name}: "
                f"status={assignment.status}, score={assignment.fit_score_percentage}, "
                f"time={elapsed:.2f}s"
            )
            
            return {
                "success": True,
                "lead_id": str(lead.id),
                "assignment_id": str(assignment.id),
                "status": assignment.status,
                "score": assignment.fit_score_percentage,
                "processing_time_seconds": elapsed,
                **result
            }
        
        except Exception as e:
            import traceback
            full_trace = traceback.format_exc()
            logger.error(f"Pipeline error for raw_lead {raw_lead.id}, ICP {icp.id}: {e}")
            logger.error(f"Full traceback:\n{full_trace}")
            print(f"\n🔴 FULL ERROR TRACEBACK:\n{full_trace}")  # Print to stdout too
            return {
                "success": False,
                "error": str(e),
                "traceback": full_trace,  # Include in result
                "lead_id": None,
                "assignment_id": None
    }
    async def _create_or_find_lead(self, raw_lead: RawLead) -> tuple[Lead, bool]:
        """Create new lead or find existing by email"""
        existing = self.db.query(Lead).filter(
            and_(
                Lead.email == raw_lead.email,
                Lead.tenant_id == raw_lead.tenant_id
            )
        ).first()
        
        if existing:
            return existing, False
        
        # Create new lead
        lead = Lead(
            tenant_id=raw_lead.tenant_id,
            raw_lead_id=raw_lead.id,
            email=raw_lead.email,
            first_name=raw_lead.first_name,
            last_name=raw_lead.last_name,
            phone=raw_lead.phone,
            job_title=raw_lead.job_title,
            linkedin_url=raw_lead.linkedin_url,
            company_name=raw_lead.company_name,
            company_domain=raw_lead.company_domain,
            company_website=raw_lead.company_website,
            company_size=raw_lead.company_size,
            company_industry=raw_lead.company_industry,
            city=raw_lead.city,
            state=raw_lead.state,
            country=raw_lead.country,
            source=raw_lead.source_name,
            source_url=raw_lead.source_url,
            processing_started_at=datetime.utcnow(),
            
            # ✅ Initialize enrichment tracking
            enrichment_status='pending'
        )
        
        self.db.add(lead)
        self.db.flush()
        
        logger.info(f"Created lead {lead.id} from raw_lead {raw_lead.id}")
        
        return lead, True
    
    async def _get_or_create_assignment(
        self,
        lead: Lead,
        icp: ICP,
        job_id: Optional[str]
    ) -> LeadICPAssignment:
        """Get existing assignment or create new one"""
        assignment = self.db.query(LeadICPAssignment).filter(
            and_(
                LeadICPAssignment.lead_id == lead.id,
                LeadICPAssignment.icp_id == icp.id
            )
        ).first()
        
        if assignment:
            return assignment
        
        assignment = LeadICPAssignment(
            lead_id=lead.id,
            icp_id=icp.id,
            tenant_id=lead.tenant_id,
            status='new',
            bucket='new'
        )
        
        self.db.add(assignment)
        self.db.flush()
        
        self.activity_logger.log_stage_transition(
            lead_id=str(lead.id),
            tenant_id=str(lead.tenant_id),
            icp_id=str(icp.id),
            assignment_id=str(assignment.id),
            from_stage=None,
            to_stage="new",
            reason="assignment_created",
            details={"job_id": job_id} if job_id else {}
        )
        
        logger.info(f"Created assignment {assignment.id} for lead {lead.id}, ICP {icp.id}")
        
        return assignment
    
    async def _run_pipeline_stages(
        self,
        lead: Lead,
        assignment: LeadICPAssignment,
        raw_lead: RawLead,
        icp: ICP,
        job_id: Optional[str],
        stages_to_run: Optional[List[str]]
    ) -> Dict[str, Any]:
        """
        Run pipeline stages with SMART ENRICHMENT
        
        Order: smart_enrich → score → verify → qualify
        """
        result = {}
        
        if not stages_to_run:
            stages_to_run = ['enrich', 'score', 'verify', 'qualify']
        
        # ✅ Stage 1: SMART Enrichment (conditional)
        if 'enrich' in stages_to_run:
            # Create enrichment plan
   
            logger.info(f"🔍 DEBUG: ICP type = {type(icp)}")
            logger.info(f"🔍 DEBUG: ICP class = {icp.__class__.__name__ if hasattr(icp, '__class__') else 'unknown'}")
            logger.info(f"🔍 DEBUG: Has scoring_rules attr? {hasattr(icp, 'scoring_rules')}")
                
            plan = self.strategy_service.create_enrichment_plan(raw_lead, lead, icp)
            
            logger.info(
                f"📋 Enrichment Plan for {lead.email}:\n"
                f"   Source: {raw_lead.source_name}\n"
                f"   Should Enrich: {plan.should_enrich}\n"
                f"   Reason: {plan.reason}\n"
                f"   Providers: {plan.providers_to_use}\n"
                f"   Fields: {plan.fields_to_enrich}\n"
                f"   Est. Cost: ${plan.estimated_cost:.4f}\n"
                f"   Priority: {plan.priority}"
            )
            
            if plan.should_enrich:
                # Run enrichment with selected providers
                enrich_result = await self._enrich_lead_with_plan(
                    lead, assignment, raw_lead, icp, job_id, plan
                )
                result['enrichment'] = enrich_result
                
                # ✅ Update lead enrichment tracking
                lead.enrichment_status = 'completed'
                lead.enriched_at = datetime.utcnow()
                lead.enrichment_source = raw_lead.source_name
                lead.enrichment_providers = plan.providers_to_use
                lead.enrichment_cost = enrich_result.get('cost', 0.0)
                lead.next_refresh_date = self.strategy_service.calculate_next_refresh(raw_lead.source_name)
                
                self.db.commit()
                
                logger.info(
                    f"✅ Enrichment complete: {len(enrich_result.get('fields_added', []))} fields added, "
                    f"cost=${enrich_result.get('cost', 0):.4f}, "
                    f"next refresh: {lead.next_refresh_date.strftime('%Y-%m-%d')}"
                )
            else:
                # ✅ Skip enrichment - track why
                lead.enrichment_status = 'skipped'
                lead.enrichment_skipped_reason = plan.reason
                lead.enrichment_source = raw_lead.source_name
                lead.enrichment_cost = 0.0
                
                # Set next refresh date even for skipped
                if raw_lead.source_name in ['apollo', 'hunter', 'peopledatalabs']:
                    lead.next_refresh_date = self.strategy_service.calculate_next_refresh(raw_lead.source_name)
                
                self.db.commit()
                
                result['enrichment'] = {
                    "skipped": True,
                    "reason": plan.reason,
                    "cost": 0.0
                }
                
                logger.info(f"⏭️  Skipped enrichment: {plan.reason}")
        
        # ✅ Stage 2: Scoring (with enriched data from Lead object)
        if 'score' in stages_to_run:
            logger.info(f"📊 STAGE 2: Scoring lead {lead.id}...")
            
            score_result = await self._score_assignment(assignment, lead, icp, job_id)
            result['scoring'] = score_result
            
            logger.info(
                f"✅ Scoring complete: {score_result.get('score')}% "
                f"(confidence: {score_result.get('confidence')}%)"
            )
            
            # Check auto-reject
            if score_result.get('rejected'):
                logger.info(f"❌ Lead rejected: score too low")
                return result
        
        # ✅ Stage 3: Verification
        if 'verify' in stages_to_run and icp.verification_enabled:
            logger.info(f"📧 STAGE 3: Verifying email {lead.email}...")
            verify_result = await self._verify_lead(lead, assignment, icp, job_id)
            result['verification'] = verify_result
            
            logger.info(
                f"✅ Verification complete: {verify_result.get('status')} "
                f"({verify_result.get('confidence')}% confidence)"
            )
        
        # ✅ Stage 4: Auto-qualification
        if 'qualify' in stages_to_run:
            logger.info(f"🎯 STAGE 4: Auto-qualifying lead {lead.id}...")
            qualify_result = await self._auto_qualify(lead, assignment, icp, job_id)
            result['qualification'] = qualify_result
            
            logger.info(
                f"✅ Qualification complete: {qualify_result.get('decision')} "
                f"(score: {qualify_result.get('score')}%)"
            )
        
        # Mark processing complete
        lead.processing_completed_at = datetime.utcnow()
        self.db.commit()
        
        return result
    
    async def _enrich_lead_with_plan(
        self,
        lead: Lead,
        assignment: LeadICPAssignment,
        raw_lead: RawLead,
        icp: ICP,
        job_id: Optional[str],
        plan
    ) -> Dict[str, Any]:
        """
        Enrich lead using the enrichment plan
        
        Maps enriched data to Lead top-level fields for scoring
        """
        start_time = datetime.utcnow()
        
        # Create enrichment service
        enrichment_service = create_enrichment_service(self.db)
        
        # Enrich with ICP-specific config
        result = await enrichment_service.enrich_lead_with_icp_config(
            email=lead.email,
            company_domain=lead.company_domain,
            company_name=lead.company_name,
            tenant_id=str(lead.tenant_id),
            icp_id=str(icp.id)
        )
        
        processing_time = self._elapsed_ms(start_time)
        
        if result.success and result.enriched_data:
            # ✅ Map enriched data to Lead top-level fields
            
            # Company description
            if "company_description" in result.enriched_data:
                lead.company_description = result.enriched_data["company_description"]
                logger.info(f"  ✅ Mapped company_description")
            
            # Company industry (map from company_type if needed)
            if "company_type" in result.enriched_data and not lead.company_industry:
                lead.company_industry = result.enriched_data["company_type"]
                logger.info(f"  ✅ Mapped company_industry from company_type")
            
            # Company employee count
            # Company employee count
            if "company_employee_count" in result.enriched_data:
                # ✅ Convert to string (database column is VARCHAR)
                employee_count = result.enriched_data["company_employee_count"]
                lead.company_employee_count = str(employee_count) if employee_count else None
                logger.info(f"  ✅ Mapped company_employee_count: {lead.company_employee_count}")
            
            # Extract country from headquarters
            if "company_headquarters" in result.enriched_data and not lead.country:
                headquarters = result.enriched_data["company_headquarters"]
                if "," in headquarters:
                    lead.country = headquarters.split(",")[-1].strip()
                    logger.info(f"  ✅ Extracted country from headquarters: {lead.country}")
            
            # Tech stack (store in enrichment_data JSONB)
            if "company_tech_stack" in result.enriched_data:
                if not lead.enrichment_data:
                    lead.enrichment_data = {}
                lead.enrichment_data["tech_stack"] = result.enriched_data["company_tech_stack"]
                logger.info(f"  ✅ Stored tech_stack in enrichment_data")
            
            # Store full enrichment data
            if not lead.enrichment_data:
                lead.enrichment_data = {}
            lead.enrichment_data.update(result.enriched_data)
            
            lead.enrichment_completeness = len(result.fields_added)
            
            # Update assignment status
            assignment.update_status('enriched')
            self.db.commit()
            
            # Log enrichment
            self.activity_logger.log_enrichment(
                lead_id=str(lead.id),
                tenant_id=str(lead.tenant_id),
                icp_id=str(icp.id),
                assignment_id=str(assignment.id),
                fields_added=result.fields_added,
                cache_hit=result.cache_hit,
                cost=result.cost,
                job_id=job_id,
                processing_time_ms=processing_time
            )
        
        return {
            "success": result.success,
            "fields_added": result.fields_added,
            "providers_used": result.providers_used,
            "cost": result.cost
        }
    
    async def _score_assignment(
        self,
        assignment: LeadICPAssignment,
        lead: Lead,
        icp: ICP,
        job_id: Optional[str]
    ) -> Dict[str, Any]:
        """Score lead against ICP"""
        start_time = datetime.utcnow()
        
        # Score using Lead (has enriched data)
        score_result = await self.scoring_engine.score_lead(lead, icp)
        
        # Update assignment
        assignment.fit_score = score_result.score
        assignment.fit_score_percentage = score_result.score
        assignment.scoring_details = score_result.breakdown
        assignment.update_status('scored')
        
        self.db.commit()
        
        processing_time = self._elapsed_ms(start_time)
        
        # Log scoring
        self.activity_logger.log_scoring(
            lead_id=str(assignment.lead_id),
            tenant_id=str(assignment.tenant_id),
            icp_id=str(icp.id),
            assignment_id=str(assignment.id),
            score=score_result.score,
            confidence=score_result.confidence,
            breakdown=score_result.breakdown,
            job_id=job_id,
            processing_time_ms=processing_time
        )
        
        # Check auto-reject threshold
        if score_result.score < float(icp.auto_reject_threshold or 30):
            await self._reject_assignment(
                assignment=assignment,
                icp=icp,
                reason="auto_rejected_low_score",
                details=f"Score {score_result.score} below threshold {icp.auto_reject_threshold}",
                job_id=job_id
            )
            return {"rejected": True, "reason": "low_score", "score": score_result.score, "confidence": score_result.confidence}
        
        return {
            "score": score_result.score,
            "confidence": score_result.confidence,
            "rejected": False
        }
    
    async def _verify_lead(
        self,
        lead: Lead,
        assignment: LeadICPAssignment,
        icp: ICP,
        job_id: Optional[str]
    ) -> Dict[str, Any]:
        """3-Pass Email Verification"""
        start_time = datetime.utcnow()
        
        try:
            verifier = create_verification_service()
            result = await verifier.verify_email(lead.email)
            
            lead.email_verified = result.is_valid
            lead.email_verification_status = result.overall_status
            lead.email_verification_confidence = Decimal(str(result.overall_confidence))
            
            if not hasattr(lead, 'verification_data') or lead.verification_data is None:
                lead.verification_data = {}
            
            lead.verification_data.update({
                "verification_timestamp": datetime.utcnow().isoformat(),
                "provider": result.provider,
                "passes_completed": result.passes_completed,
                "overall_confidence": result.overall_confidence,
                "deliverability_score": result.deliverability_score,
                "syntax_score": result.syntax_score,
                "domain_score": result.domain_score,
                "mailbox_score": result.mailbox_score,
                "is_disposable": result.is_disposable,
                "is_role_account": result.is_role_account,
                "is_free_provider": result.is_free_provider,
                "is_catch_all": result.is_catch_all,
                "pass_1_details": result.pass_1_result.to_dict() if result.pass_1_result else None,
                "pass_2_details": result.pass_2_result.to_dict() if result.pass_2_result else None,
                "pass_3_details": result.pass_3_result.to_dict() if result.pass_3_result else None,
                "all_details": result.details
            })
            
            assignment.update_status('verified')
            self.db.commit()
            
            processing_time = self._elapsed_ms(start_time)
            
            self.activity_logger.log_verification(
                lead_id=str(lead.id),
                tenant_id=str(lead.tenant_id),
                icp_id=str(icp.id),
                assignment_id=str(assignment.id),
                verification_status=result.overall_status,
                confidence=result.overall_confidence,
                cost=result.total_cost,
                cache_hit=False,
                job_id=job_id,
                processing_time_ms=processing_time
            )
            
            return {
                "verified": result.is_valid,
                "status": result.overall_status,
                "confidence": result.overall_confidence,
                "passes_completed": result.passes_completed,
                "field_scores": {
                    "syntax": result.syntax_score,
                    "domain": result.domain_score,
                    "mailbox": result.mailbox_score,
                    "deliverability": result.deliverability_score
                },
                "metadata": {
                    "is_disposable": result.is_disposable,
                    "is_role": result.is_role_account,
                    "is_free": result.is_free_provider,
                    "is_catch_all": result.is_catch_all
                },
                "cost": result.total_cost,
                "time_ms": result.total_time_ms,
                "error": result.error
            }
        
        except Exception as e:
            logger.error(f"❌ Verification error for {lead.email}: {e}")
            return {
                "verified": False,
                "status": "error",
                "confidence": 0.0,
                "error": str(e),
                "cost": 0.0
            }
    
    async def _auto_qualify(
        self,
        lead: Lead,
        assignment: LeadICPAssignment,
        icp: ICP,
        job_id: Optional[str]
    ) -> Dict[str, Any]:
        """Auto-qualify based on score and verification"""
        score = assignment.fit_score_percentage or 0.0
        verified = lead.email_verified
        
        # Auto-approve: high score + verified
        if score >= float(icp.auto_approve_threshold or 80) and verified:
            assignment.update_status('qualified')
            assignment.qualified_at = datetime.utcnow()
            self.db.commit()
            
            self.activity_logger.log_qualification(
                lead_id=str(lead.id),
                tenant_id=str(lead.tenant_id),
                icp_id=str(icp.id),
                assignment_id=str(assignment.id),
                decision="auto_approved",
                reason=f"Score {score}% >= {icp.auto_approve_threshold}% and verified",
                score=score,
                threshold_used=float(icp.auto_approve_threshold),
                job_id=job_id
            )
            
            return {
                "decision": "auto_approved",
                "reason": "High score and verified email",
                "score": score
            }
        
        # Review needed
        elif score >= float(icp.review_threshold or 50):
            assignment.update_status('pending_review')
            self.db.commit()
            
            self.activity_logger.log_qualification(
                lead_id=str(lead.id),
                tenant_id=str(lead.tenant_id),
                icp_id=str(icp.id),
                assignment_id=str(assignment.id),
                decision="pending_review",
                reason=f"Score {score}% requires manual review",
                score=score,
                threshold_used=float(icp.review_threshold),
                job_id=job_id
            )
            
            return {
                "decision": "pending_review",
                "reason": "Requires manual review",
                "score": score
            }
        
        else:
            return {
                "decision": "rejected",
                "reason": "Low score",
                "score": score
            }
    
    async def _reject_assignment(
        self,
        assignment: LeadICPAssignment,
        icp: ICP,
        reason: str,
        details: str,
        job_id: Optional[str]
    ):
        """Reject assignment with tracking"""
        assignment.update_status('rejected')
        self.db.commit()
        
        rejection = LeadRejectionTracking(
            lead_id=assignment.lead_id,
            icp_id=icp.id,
            assignment_id=assignment.id,
            tenant_id=assignment.tenant_id,
            rejection_stage=assignment.status,
            rejection_reason=reason,
            rejection_category="low_score",
            rejection_details=details,
            can_be_overridden=True,
            rejected_at=datetime.utcnow()
        )
        
        self.db.add(rejection)
        self.db.commit()
        
        self.activity_logger.log_rejection(
            lead_id=str(assignment.lead_id),
            tenant_id=str(assignment.tenant_id),
            icp_id=str(icp.id),
            assignment_id=str(assignment.id),
            reason=reason,
            details=details,
            job_id=job_id
        )
    
    async def _update_raw_lead_tracking(
        self,
        raw_lead: RawLead,
        icp: ICP,
        lead: Lead
    ):
        """Update raw lead tracking"""
        if not raw_lead.processed_by_icps:
            raw_lead.processed_by_icps = []
        
        if str(icp.id) not in raw_lead.processed_by_icps:
            raw_lead.processed_by_icps = raw_lead.processed_by_icps + [str(icp.id)]
        
        if not raw_lead.lead_id:
            raw_lead.lead_id = lead.id
            raw_lead.processed_at = datetime.utcnow()
        
        active_icps = self.db.query(ICP).filter(
            ICP.tenant_id == raw_lead.tenant_id,
            ICP.is_active == True
        ).count()
        
        if len(raw_lead.processed_by_icps) >= active_icps:
            raw_lead.processing_status = "processed"
        
        self.db.commit()
    
    def _elapsed_ms(self, start_time: datetime) -> int:
        """Calculate elapsed milliseconds"""
        return int((datetime.utcnow() - start_time).total_seconds() * 1000)