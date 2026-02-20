"""Lead processing pipeline orchestrator."""

import logging
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.models import Lead
from app.services.normalization import normalization_service
from app.services.deduplication import deduplication_service
from app.services.enrichment import enrichment_service
from app.services.verification import verification_service
from app.services.scoring import scoring_service
from typing import List, Optional, Dict, Any
from uuid import UUID


logger = logging.getLogger(__name__)


class LeadPipeline:
    """
    Orchestrate the complete lead processing pipeline.
    
    Pipeline stages:
    1. Normalize - Standardize data formats
    2. Deduplicate - Check for existing leads
    3. Enrich - Add data from external sources
    4. Verify - Validate email deliverability
    5. Score - Calculate lead quality
    6. Save - Persist to database
    """
    
    async def process_lead(
        self,
        lead: Lead,
        db: AsyncSession,
        skip_enrichment: bool = False,
        skip_verification: bool = False
    ) -> Lead:
        """
        Process a single lead through the pipeline.
        Updates the lead object in place.
        """
        try:
            # Stage 1: Normalization (already done at ingestion, but ensure completeness)
            lead_data = {
                'email': lead.email,
                'first_name': lead.first_name,
                'last_name': lead.last_name,
                'phone': lead.phone,
                'job_title': lead.job_title,
                'company_name': lead.company_name,
                'company_website': lead.company_website,
                'linkedin_url': lead.linkedin_url,
                'company_domain': lead.company_domain
            }
            
            normalized = normalization_service.normalize_lead(lead_data)
            
            # Update lead with normalized data
            for key, value in normalized.items():
                if hasattr(lead, key):
                    setattr(lead, key, value)
            
            lead.status = "normalized"
            await db.flush()
            logger.debug(f"Lead normalized: {lead.email}")
            
            # Stage 2: Enrichment
            if not skip_enrichment:
                enrichment_data = await enrichment_service.enrich_lead(
                    email=lead.email,
                    domain=lead.company_domain
                )
                
                if enrichment_data and enrichment_data.get('enriched'):
                    # Store raw enrichment data
                    lead.enrichment_data = enrichment_data
                    
                    # Extract and update lead fields from enrichment
                    if enrichment_data.get('person'):
                        person = enrichment_data['person']
                        if not lead.first_name and person.get('first_name'):
                            lead.first_name = person['first_name']
                        if not lead.last_name and person.get('last_name'):
                            lead.last_name = person['last_name']
                        if not lead.job_title and person.get('job_title'):
                            lead.job_title = person['job_title']
                        if not lead.linkedin_url and person.get('linkedin_url'):
                            lead.linkedin_url = person['linkedin_url']
                    
                    if enrichment_data.get('company'):
                        company = enrichment_data['company']
                        if not lead.company_name and company.get('name'):
                            lead.company_name = company['name']
                        if company.get('industry'):
                            lead.company_industry = company['industry']
                        if not lead.company_website and company.get('website'):
                            lead.company_website = company['website']
                    
                    lead.status = "enriched"
                    await db.flush()
                    logger.info(f"Lead enriched: {lead.email}")
            
            # Stage 3: Email Verification
            if not skip_verification:
                verification_result = await verification_service.verify_email(lead.email)
                
                lead.email_verified = verification_result['verified']
                lead.email_deliverability_score = verification_result.get('deliverability_score')
                
                # Store verification details in enrichment_data
                if not lead.enrichment_data:
                    lead.enrichment_data = {}
                lead.enrichment_data['verification'] = verification_result
                
                lead.status = "verified"
                await db.flush()
                logger.info(f"Lead verified: {lead.email} - {verification_result['verification_status']}")
            
            # Stage 4: Scoring
            updated_score = scoring_service.calculate_fit_score(
                job_title=lead.job_title,
                email_verified=lead.email_verified,
                email_deliverability_score=lead.email_deliverability_score,
                enrichment_data=lead.enrichment_data,
                source_quality=0.7,  # TODO: Get from source config
                lead_data={
                    'first_name': lead.first_name,
                    'last_name': lead.last_name,
                    'phone': lead.phone,
                    'job_title': lead.job_title,
                    'linkedin_url': lead.linkedin_url,
                    'company_name': lead.company_name,
                    'company_website': lead.company_website,
                    'company_industry': lead.company_industry
                }
            )
            
            lead.fit_score = updated_score
            lead.status = "pending_review"  # Ready for human review
            
            logger.info(f"Lead processing complete: {lead.email} - Score: {updated_score}")
            
            return lead
            
        except Exception as e:
            logger.error(f"Pipeline processing failed for {lead.email}: {e}", exc_info=True)
            lead.status = "error"
            if not lead.enrichment_data:
                lead.enrichment_data = {}
            lead.enrichment_data['pipeline_error'] = {
                'error': str(e),
                'occurred_at': datetime.utcnow().isoformat()
            }
            raise
    
    async def process_batch(
        self,
        leads: list[Lead],
        db: AsyncSession,
        skip_enrichment: bool = False,
        skip_verification: bool = False
    ) -> Dict[str, int]:
        """
        Process multiple leads through the pipeline.
        Returns statistics about the batch processing.
        """
        stats = {
            'total': len(leads),
            'successful': 0,
            'failed': 0,
            'enriched': 0,
            'verified': 0
        }
        
        for lead in leads:
            try:
                await self.process_lead(
                    lead=lead,
                    db=db,
                    skip_enrichment=skip_enrichment,
                    skip_verification=skip_verification
                )
                stats['successful'] += 1
                
                if lead.enrichment_data and lead.enrichment_data.get('enriched'):
                    stats['enriched'] += 1
                
                if lead.email_verified:
                    stats['verified'] += 1
                    
            except Exception as e:
                stats['failed'] += 1
                logger.error(f"Failed to process lead {lead.id}: {e}")
        
        await db.commit()
        
        logger.info(f"Batch processing complete: {stats}")
        return stats

async def process_raw_lead(
    self,
    raw_lead: "RawLead",
    db: AsyncSession
) -> Optional[UUID]:
    """
    Process a raw lead from the raw_leads table into the leads table.
    
    Steps:
    1. Validate email format
    2. Check for duplicates
    3. Create lead in 'raw_landing' bucket
    4. Run through processing pipeline
    5. Route to final bucket based on score
    
    Args:
        raw_lead: RawLead model instance
        db: Database session
    
    Returns:
        UUID of created lead, or None if failed
    """
    from app.models import Lead, ICP, LeadProcessingStage, LeadFitScore
    from uuid import UUID
    import re
    
    try:
        # 1. Validate email
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, raw_lead.email):
            logger.warning(f"Invalid email format: {raw_lead.email}")
            return None
        
        # 2. Check for duplicate (within tenant)
        from sqlalchemy import select
        result = await db.execute(
            select(Lead).where(
                Lead.tenant_id == raw_lead.tenant_id,
                Lead.email == raw_lead.email.lower()
            )
        )
        existing_lead = result.scalars().first()
        
        if existing_lead:
            logger.info(f"Lead {raw_lead.email} already exists, skipping")
            return existing_lead.id
        
        # 3. Get ICP configuration
        result = await db.execute(
            select(ICP).where(ICP.id == raw_lead.icp_id)
        )
        icp = result.scalars().first()
        
        if not icp:
            logger.error(f"ICP {raw_lead.icp_id} not found")
            return None
        
        # 4. Create lead in raw_landing bucket
        lead = Lead(
            tenant_id=raw_lead.tenant_id,
            icp_id=raw_lead.icp_id,
            source_id=raw_lead.source_id,
            email=raw_lead.email.lower(),
            first_name=raw_lead.first_name,
            last_name=raw_lead.last_name,
            phone=raw_lead.phone,
            job_title=raw_lead.job_title,
            company_name=raw_lead.company_name,
            linkedin_url=raw_lead.linkedin_url,
            current_bucket='raw_landing',
            bucket_entered_at=datetime.utcnow(),
            status='new',
            acquisition_timestamp=raw_lead.created_at,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Extract additional fields from scraped_data
        if raw_lead.scraped_data:
            if 'company_website' in raw_lead.scraped_data:
                lead.company_website = raw_lead.scraped_data['company_website']
            if 'company_domain' in raw_lead.scraped_data:
                lead.company_domain = raw_lead.scraped_data['company_domain']
            if 'company_size' in raw_lead.scraped_data:
                lead.company_size = raw_lead.scraped_data['company_size']
            if 'city' in raw_lead.scraped_data:
                lead.city = raw_lead.scraped_data['city']
            if 'state' in raw_lead.scraped_data:
                lead.state = raw_lead.scraped_data['state']
            if 'country' in raw_lead.scraped_data:
                lead.country = raw_lead.scraped_data['country']
            if 'address' in raw_lead.scraped_data:
                lead.address = raw_lead.scraped_data['address']
            if 'company_industry' in raw_lead.scraped_data:
                lead.company_industry = raw_lead.scraped_data['company_industry']
        
        db.add(lead)
        await db.flush()
        
        # 5. Create initial processing stage
        stage = LeadProcessingStage(
            lead_id=lead.id,
            stage_name='raw_landing',
            entered_at=datetime.utcnow(),
            metadata={'source': 'raw_leads_table', 'raw_lead_id': str(raw_lead.id)}
        )
        db.add(stage)
        await db.flush()
        
        # 6. Process through pipeline based on ICP settings
        skip_enrichment = not icp.enrichment_enabled
        skip_verification = not icp.verification_enabled
        
        # Run through existing pipeline
        lead = await self.process_lead(
            lead=lead,
            db=db,
            skip_enrichment=skip_enrichment,
            skip_verification=skip_verification
        )
        
        # 7. Update bucket tracking
        # Mark raw_landing stage as exited
        stage.exited_at = datetime.utcnow()
        stage.duration_seconds = int(
            (stage.exited_at - stage.entered_at).total_seconds()
        )
        
        # Determine current bucket based on processing status
        if skip_enrichment and skip_verification:
            current_bucket = 'scored'
        elif skip_verification:
            current_bucket = 'enriched'
            lead.enrichment_completed = True
        else:
            current_bucket = 'verified'
            lead.enrichment_completed = not skip_enrichment
            lead.verification_completed = True
        
        lead.current_bucket = current_bucket
        lead.bucket_entered_at = datetime.utcnow()
        
        # Create stage record for current bucket
        current_stage = LeadProcessingStage(
            lead_id=lead.id,
            stage_name=current_bucket,
            entered_at=datetime.utcnow(),
            metadata={
                'enrichment_completed': lead.enrichment_completed,
                'verification_completed': lead.verification_completed
            }
        )
        db.add(current_stage)
        
        # 8. Route to final bucket based on thresholds
        fit_score = lead.fit_score or 0.0
        
        if fit_score >= icp.auto_approve_threshold:
            final_bucket = 'approved'
            lead.status = 'approved'
        elif fit_score >= icp.review_threshold:
            final_bucket = 'pending_review'
            lead.status = 'pending_review'
        elif fit_score < icp.auto_reject_threshold:
            final_bucket = 'rejected'
            lead.status = 'rejected'
        else:
            # Between reject and review threshold
            final_bucket = 'pending_review'
            lead.status = 'pending_review'
        
        # If final bucket is different from current, update it
        if final_bucket != current_bucket:
            # Mark current stage as exited
            current_stage.exited_at = datetime.utcnow()
            current_stage.duration_seconds = int(
                (current_stage.exited_at - current_stage.entered_at).total_seconds()
            )
            
            # Update lead bucket
            lead.current_bucket = final_bucket
            lead.bucket_entered_at = datetime.utcnow()
            
            # Create final stage
            final_stage = LeadProcessingStage(
                lead_id=lead.id,
                stage_name=final_bucket,
                entered_at=datetime.utcnow(),
                metadata={
                    'auto_decision': True,
                    'threshold_based': True,
                    'fit_score': fit_score
                }
            )
            db.add(final_stage)
        
        # 9. Create LeadFitScore record
        lead_fit_score = LeadFitScore(
            lead_id=lead.id,
            icp_id=icp.id,
            overall_score=fit_score,
            qualified=(final_bucket in ['approved', 'pending_review']),
            auto_approved=(final_bucket == 'approved')
        )
        db.add(lead_fit_score)
        
        await db.commit()
        await db.refresh(lead)
        
        logger.info(
            f"Successfully processed raw lead {raw_lead.id} -> "
            f"lead {lead.id} (bucket: {final_bucket}, score: {fit_score})"
        )
        
        return lead.id
    
    except Exception as e:
        logger.error(f"Error processing raw lead {raw_lead.id}: {str(e)}")
        await db.rollback()
        return None


# Singleton instance
lead_pipeline = LeadPipeline()
