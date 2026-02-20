# backend/app/services/activity_logger.py
"""
Activity Logger - FIXED with safe UUID conversion
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session
import uuid

from app.models import LeadStageActivity


class ActivityLogger:
    """Logs lead stage transitions"""
    
    def __init__(self, db: Session):
        self.db = db
    
    @staticmethod
    def _to_uuid(value):
        """Safely convert to UUID"""
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))
    
    def log_stage_transition(
        self,
        lead_id: str,
        tenant_id: str,
        icp_id: str,
        assignment_id: str,
        from_stage: Optional[str],
        to_stage: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ):
        """Log a stage transition"""
        
        # Build details dict
        activity_details = details or {}
        activity_details['reason'] = reason
        
        activity = LeadStageActivity(
            tenant_id=self._to_uuid(tenant_id),
            lead_id=self._to_uuid(lead_id),
            icp_id=self._to_uuid(icp_id),
            assignment_id=self._to_uuid(assignment_id),
            stage=to_stage,
            from_stage=from_stage,
            to_stage=to_stage,
            details=activity_details,
            user_id=self._to_uuid(user_id),
            timestamp=datetime.utcnow()
        )
        
        self.db.add(activity)
        self.db.flush()
        
        return activity
    
    def log_creation(self, lead_id: str, tenant_id: str, icp_id: str, assignment_id: str, job_id: Optional[str] = None):
        return self.log_stage_transition(
            lead_id=lead_id, tenant_id=tenant_id, icp_id=icp_id, assignment_id=assignment_id,
            from_stage=None, to_stage="new", reason="lead_created",
            details={"job_id": job_id} if job_id else {}
        )
    
    def log_scoring(self, lead_id: str, tenant_id: str, icp_id: str, assignment_id: str,
                    score: float, confidence: float, breakdown: Dict[str, Any],
                    job_id: Optional[str] = None, processing_time_ms: Optional[int] = None):
        details = {"score": score, "confidence": confidence, "breakdown": breakdown}
        if job_id:
            details["job_id"] = job_id
        if processing_time_ms:
            details["processing_time_ms"] = processing_time_ms
        return self.log_stage_transition(
            lead_id=lead_id, tenant_id=tenant_id, icp_id=icp_id, assignment_id=assignment_id,
            from_stage="new", to_stage="scored", reason="lead_scored", details=details
        )
    
    def log_enrichment(self, lead_id: str, tenant_id: str, icp_id: str, assignment_id: str,
                       fields_added: List[str], cache_hit: bool, cost: float,
                       job_id: Optional[str] = None, processing_time_ms: Optional[int] = None):
        details = {"fields_added": fields_added, "field_count": len(fields_added), "cache_hit": cache_hit, "cost": cost}
        if job_id:
            details["job_id"] = job_id
        if processing_time_ms:
            details["processing_time_ms"] = processing_time_ms
        return self.log_stage_transition(
            lead_id=lead_id, tenant_id=tenant_id, icp_id=icp_id, assignment_id=assignment_id,
            from_stage="scored", to_stage="enriched", reason="lead_enriched", details=details
        )
    
    def log_verification(self, lead_id: str, tenant_id: str, icp_id: str, assignment_id: str,
                        verification_status: str, confidence: float, cost: float, cache_hit: bool = False,
                        job_id: Optional[str] = None, processing_time_ms: Optional[int] = None):
        details = {"status": verification_status, "confidence": confidence, "cost": cost, "cache_hit": cache_hit}
        if job_id:
            details["job_id"] = job_id
        if processing_time_ms:
            details["processing_time_ms"] = processing_time_ms
        return self.log_stage_transition(
            lead_id=lead_id, tenant_id=tenant_id, icp_id=icp_id, assignment_id=assignment_id,
            from_stage="enriched", to_stage="verified", reason="email_verified", details=details
        )
    
    def log_qualification(self, lead_id: str, tenant_id: str, icp_id: str, assignment_id: str,
                         decision: str, reason: str, score: float, threshold_used: float,
                         job_id: Optional[str] = None):
        details = {"decision": decision, "score": score, "threshold": threshold_used}
        if job_id:
            details["job_id"] = job_id
        return self.log_stage_transition(
            lead_id=lead_id, tenant_id=tenant_id, icp_id=icp_id, assignment_id=assignment_id,
            from_stage="verified", to_stage=decision, reason=reason, details=details
        )
    
    def log_rejection(self, lead_id: str, tenant_id: str, icp_id: str, assignment_id: str,
                     reason: str, details: Optional[str] = None, job_id: Optional[str] = None):
        activity_details = {"rejection_details": details}
        if job_id:
            activity_details["job_id"] = job_id
        return self.log_stage_transition(
            lead_id=lead_id, tenant_id=tenant_id, icp_id=icp_id, assignment_id=assignment_id,
            from_stage=None, to_stage="rejected", reason=reason, details=activity_details
        )
    
    def log_export(self, lead_id: str, tenant_id: str, icp_id: str, assignment_id: str,
                  destination: str, batch_id: Optional[str] = None, job_id: Optional[str] = None):
        details = {"destination": destination}
        if batch_id:
            details["batch_id"] = batch_id
        if job_id:
            details["job_id"] = job_id
        return self.log_stage_transition(
            lead_id=lead_id, tenant_id=tenant_id, icp_id=icp_id, assignment_id=assignment_id,
            from_stage="qualified", to_stage="exported", reason="lead_exported", details=details
        )
    
    def get_lead_history(self, lead_id: str, icp_id: Optional[str] = None, assignment_id: Optional[str] = None) -> List[LeadStageActivity]:
        query = self.db.query(LeadStageActivity).filter(LeadStageActivity.lead_id == self._to_uuid(lead_id))
        if icp_id:
            query = query.filter(LeadStageActivity.icp_id == self._to_uuid(icp_id))
        if assignment_id:
            query = query.filter(LeadStageActivity.assignment_id == self._to_uuid(assignment_id))
        return query.order_by(LeadStageActivity.timestamp).all()
    
    def get_assignment_history(self, assignment_id: str) -> List[LeadStageActivity]:
        return self.db.query(LeadStageActivity).filter(
            LeadStageActivity.assignment_id == self._to_uuid(assignment_id)
        ).order_by(LeadStageActivity.timestamp).all()