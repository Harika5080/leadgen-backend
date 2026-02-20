# backend/app/services/email_verification_service.py
"""
Complete 3-Pass Email Verification System (REST API)

Tools:
1. validator.js (via py3-validate-email) - Input validation
2. Mailchecker (via disposable-email-domains) - Syntax + MX + Disposable
3. dnspython - DNS/MX validation
4. Verifalia REST API - Deep mailbox validation

No Python SDK needed - uses direct HTTP requests
"""

import re
import logging
import smtplib
import dns.resolver
import requests
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime

# Email validation libraries
from validate_email import validate_email as validator_js_check
from disposable_email_domains import blocklist as disposable_domains

logger = logging.getLogger(__name__)


@dataclass
class VerificationPass:
    """Individual pass result"""
    pass_number: int
    pass_name: str
    passed: bool
    confidence_contribution: float
    checks_performed: List[str]
    checks_passed: List[str]
    checks_failed: List[str]
    details: Dict
    processing_time_ms: int
    cost: float = 0.0
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class EmailVerificationResult:
    """Complete verification result with field-level confidence"""
    
    email: str
    is_valid: bool
    overall_status: str
    overall_confidence: float
    passes_completed: int
    pass_1_result: Optional[VerificationPass]
    pass_2_result: Optional[VerificationPass]
    pass_3_result: Optional[VerificationPass]
    syntax_score: float
    domain_score: float
    mailbox_score: float
    deliverability_score: float
    is_disposable: bool
    is_role_account: bool
    is_free_provider: bool
    is_catch_all: bool
    details: Dict
    provider: str = "3-pass-orchestration"
    total_cost: float = 0.0
    total_time_ms: int = 0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        if self.pass_1_result:
            result['pass_1_result'] = self.pass_1_result.to_dict()
        if self.pass_2_result:
            result['pass_2_result'] = self.pass_2_result.to_dict()
        if self.pass_3_result:
            result['pass_3_result'] = self.pass_3_result.to_dict()
        return result


class ThreePassVerificationService:
    """3-Pass Email Verification using REST APIs"""
    
    def __init__(
        self,
        verifalia_username: str = None,
        verifalia_password: str = None,
        smtp_timeout: int = 10,
        enable_smtp_probe: bool = False,  # Disabled by default (can be slow)
        enable_verifalia: bool = True
    ):
        self.verifalia_username = verifalia_username
        self.verifalia_password = verifalia_password
        self.verifalia_base_url = "https://api.verifalia.com/v2.4"
        self.smtp_timeout = smtp_timeout
        self.enable_smtp_probe = enable_smtp_probe
        self.enable_verifalia = enable_verifalia
        
        if verifalia_username and verifalia_password:
            logger.info("✅ Verifalia credentials configured")
        else:
            logger.warning("⚠️ Verifalia credentials not configured")
    
    async def verify_email(self, email: str) -> EmailVerificationResult:
        """Complete 3-pass email verification"""
        start_time = datetime.utcnow()
        
        logger.info(f"🔍 Starting 3-pass verification for: {email}")
        
        passes_completed = 0
        pass_1_result = None
        pass_2_result = None
        pass_3_result = None
        total_cost = 0.0
        
        syntax_score = 0.0
        domain_score = 0.0
        mailbox_score = 0.0
        deliverability_score = 0.0
        
        is_disposable = False
        is_role_account = False
        is_free_provider = False
        is_catch_all = False
        
        try:
            # PASS 1: Syntax Validation (FREE)
            pass_1_result = await self._pass_1_syntax_validation(email)
            passes_completed = 1
            
            if not pass_1_result.passed:
                logger.info(f"❌ PASS 1 FAILED: {email}")
                return self._build_result(
                    email, False, "invalid_syntax", pass_1_result.confidence_contribution,
                    1, pass_1_result, None, None, 0, 0, 0, 0,
                    pass_1_result.details.get('is_disposable', False), False, False, False,
                    pass_1_result.details, 0.0, start_time
                )
            
            logger.info(f"✅ PASS 1 SUCCESS: {email}")
            syntax_score = pass_1_result.confidence_contribution
            is_disposable = pass_1_result.details.get('is_disposable', False)
            
            # PASS 2: Domain Validation (FREE)
            pass_2_result = await self._pass_2_domain_validation(email)
            passes_completed = 2
            
            if not pass_2_result.passed:
                logger.info(f"❌ PASS 2 FAILED: {email}")
                domain_score = pass_2_result.confidence_contribution
                return self._build_result(
                    email, False, "invalid_domain", syntax_score + domain_score,
                    2, pass_1_result, pass_2_result, None,
                    syntax_score, domain_score, 0, 0,
                    is_disposable, False, pass_2_result.details.get('is_free', False), False,
                    {**pass_1_result.details, **pass_2_result.details}, 0.0, start_time
                )
            
            logger.info(f"✅ PASS 2 SUCCESS: {email}")
            domain_score = pass_2_result.confidence_contribution
            is_free_provider = pass_2_result.details.get('is_free', False)
            
            # PASS 3: Mailbox Validation (PAID - only if Verifalia enabled)
            if self.enable_verifalia and self.verifalia_username:
                pass_3_result = await self._pass_3_mailbox_validation(email)
                passes_completed = 3
                total_cost = pass_3_result.cost
                
                mailbox_score = pass_3_result.confidence_contribution
                is_catch_all = pass_3_result.details.get('is_catch_all', False)
                is_role_account = pass_3_result.details.get('is_role', False)
                
                deliverability_score = (
                    syntax_score * 0.2 +
                    domain_score * 0.3 +
                    mailbox_score * 0.5
                )
                
                overall_confidence = syntax_score + domain_score + mailbox_score
                is_valid = pass_3_result.passed
                overall_status = pass_3_result.details.get('classification', 'Unknown')
                
                all_details = {
                    **pass_1_result.details,
                    **pass_2_result.details,
                    **pass_3_result.details
                }
            else:
                # No Pass 3 - stop at domain validation
                deliverability_score = syntax_score * 0.4 + domain_score * 0.6
                overall_confidence = syntax_score + domain_score
                is_valid = True
                overall_status = "dns_valid"
                all_details = {**pass_1_result.details, **pass_2_result.details}
                
                pass_3_result = VerificationPass(
                    pass_number=3,
                    pass_name="Mailbox Validation",
                    passed=False,
                    confidence_contribution=0.0,
                    checks_performed=['verifalia_skipped'],
                    checks_passed=[],
                    checks_failed=['verifalia_skipped'],
                    details={'skip_reason': 'Verifalia not configured'},
                    processing_time_ms=0,
                    cost=0.0
                )
                passes_completed = 2  # Only completed 2 passes
            
            return EmailVerificationResult(
                email=email,
                is_valid=is_valid,
                overall_status=overall_status,
                overall_confidence=overall_confidence,
                passes_completed=passes_completed,
                pass_1_result=pass_1_result,
                pass_2_result=pass_2_result,
                pass_3_result=pass_3_result,
                syntax_score=syntax_score,
                domain_score=domain_score,
                mailbox_score=mailbox_score,
                deliverability_score=deliverability_score,
                is_disposable=is_disposable,
                is_role_account=is_role_account,
                is_free_provider=is_free_provider,
                is_catch_all=is_catch_all,
                details=all_details,
                total_cost=total_cost,
                total_time_ms=self._elapsed_ms(start_time)
            )
        
        except Exception as e:
            logger.error(f"❌ Verification error for {email}: {e}")
            return EmailVerificationResult(
                email=email,
                is_valid=False,
                overall_status="error",
                overall_confidence=0.0,
                passes_completed=passes_completed,
                pass_1_result=pass_1_result,
                pass_2_result=pass_2_result,
                pass_3_result=pass_3_result,
                syntax_score=syntax_score,
                domain_score=domain_score,
                mailbox_score=mailbox_score,
                deliverability_score=deliverability_score,
                is_disposable=is_disposable,
                is_role_account=is_role_account,
                is_free_provider=is_free_provider,
                is_catch_all=is_catch_all,
                details={"error": str(e)},
                error=str(e),
                total_cost=total_cost,
                total_time_ms=self._elapsed_ms(start_time)
            )
    
    def _build_result(self, email, is_valid, status, confidence, passes,
                     p1, p2, p3, syn, dom, mail, deliv, disp, role, free, catch,
                     details, cost, start):
        """Helper to build result"""
        return EmailVerificationResult(
            email=email, is_valid=is_valid, overall_status=status,
            overall_confidence=confidence, passes_completed=passes,
            pass_1_result=p1, pass_2_result=p2, pass_3_result=p3,
            syntax_score=syn, domain_score=dom, mailbox_score=mail,
            deliverability_score=deliv, is_disposable=disp, is_role_account=role,
            is_free_provider=free, is_catch_all=catch, details=details,
            total_cost=cost, total_time_ms=self._elapsed_ms(start)
        )
    
    async def _pass_1_syntax_validation(self, email: str) -> VerificationPass:
        """PASS 1: Syntax validation (FREE)"""
        start_time = datetime.utcnow()
        checks_performed = []
        checks_passed = []
        checks_failed = []
        details = {}
        
        # Check 1: validator.js
        checks_performed.append("validator_js")
        try:
            is_valid = validator_js_check(email, check_format=True, check_blacklist=False, check_dns=False, check_smtp=False)
            if is_valid:
                checks_passed.append("validator_js")
            else:
                checks_failed.append("validator_js")
        except:
            is_valid = False
            checks_failed.append("validator_js")
        
        # Check 2: Regex
        checks_performed.append("regex")
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        regex_valid = bool(re.match(pattern, email))
        if regex_valid:
            checks_passed.append("regex")
        else:
            checks_failed.append("regex")
        
        # Check 3: Disposable
        checks_performed.append("disposable")
        domain = email.split("@")[1].lower() if "@" in email else ""
        is_disposable = domain in disposable_domains
        details['is_disposable'] = is_disposable
        if not is_disposable:
            checks_passed.append("disposable")
        else:
            checks_failed.append("disposable")
            details['reason'] = "Disposable email"
        
        passed = is_valid and regex_valid and not is_disposable
        confidence = 30.0 if passed else 0.0
        
        return VerificationPass(
            pass_number=1, pass_name="Syntax Validation", passed=passed,
            confidence_contribution=confidence, checks_performed=checks_performed,
            checks_passed=checks_passed, checks_failed=checks_failed,
            details=details, processing_time_ms=self._elapsed_ms(start_time), cost=0.0
        )
    
    async def _pass_2_domain_validation(self, email: str) -> VerificationPass:
        """PASS 2: Domain/MX validation (FREE)"""
        start_time = datetime.utcnow()
        checks_performed = ['mx_records']
        checks_passed = []
        checks_failed = []
        details = {}
        
        domain = email.split("@")[1] if "@" in email else None
        if not domain:
            return VerificationPass(2, "Domain Validation", False, 0.0, checks_performed, [], checks_failed, {'reason': 'No domain'}, self._elapsed_ms(start_time), 0.0)
        
        # MX check
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_list = [{"host": str(r.exchange).rstrip('.'), "priority": r.preference} for r in mx_records]
            mx_list.sort(key=lambda x: x['priority'])
            
            checks_passed.append('mx_records')
            details['has_mx'] = True
            details['mx_records'] = mx_list
            details['primary_mx'] = mx_list[0]['host'] if mx_list else None
        except:
            checks_failed.append('mx_records')
            details['has_mx'] = False
            details['reason'] = "No MX records"
        
        # Free provider check
        free_providers = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']
        is_free = domain.lower() in free_providers
        details['is_free'] = is_free
        
        passed = details.get('has_mx', False)
        confidence = 25.0 if passed else 0.0
        if passed and not is_free:
            confidence += 5.0
        
        return VerificationPass(
            pass_number=2, pass_name="Domain Validation", passed=passed,
            confidence_contribution=confidence, checks_performed=checks_performed,
            checks_passed=checks_passed, checks_failed=checks_failed,
            details=details, processing_time_ms=self._elapsed_ms(start_time), cost=0.0
        )
    
    async def _pass_3_mailbox_validation(self, email: str) -> VerificationPass:
        """PASS 3: Verifalia REST API validation (PAID - $0.005)"""
        start_time = datetime.utcnow()
        checks_performed = ['verifalia_api']
        checks_passed = []
        checks_failed = []
        details = {}
        
        if not self.verifalia_username or not self.verifalia_password:
            return VerificationPass(3, "Mailbox Validation", False, 0.0, checks_performed, [], checks_failed, {'error': 'No credentials'}, 0, 0.0)
        
        try:
            response = requests.post(
                f"{self.verifalia_base_url}/email-validations",
                auth=(self.verifalia_username, self.verifalia_password),
                json={"entries": [{"inputData": email}], "quality": "Standard", "deduplication": "Off"},
                params={"waitTime": "120s"},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=130
            )
            
            if response.status_code != 200:
                checks_failed.append('verifalia_api')
                return VerificationPass(3, "Mailbox Validation", False, 0.0, checks_performed, [], checks_failed, {'error': f'API error {response.status_code}'}, self._elapsed_ms(start_time), 0.005)
            
            data = response.json()
            overview = data.get("overview", {})
            
            if overview.get("status") != "Completed":
                checks_failed.append('verifalia_api')
                return VerificationPass(3, "Mailbox Validation", False, 0.0, checks_performed, [], checks_failed, {'error': 'Not completed'}, self._elapsed_ms(start_time), 0.005)
            
            entries = data.get("entries", {}).get("data", [])
            if not entries:
                checks_failed.append('verifalia_api')
                return VerificationPass(3, "Mailbox Validation", False, 0.0, checks_performed, [], checks_failed, {'error': 'No entries'}, self._elapsed_ms(start_time), 0.005)
            
            entry = entries[0]
            classification = entry.get("classification", "Unknown")
            
            details['classification'] = classification
            details['is_role'] = entry.get("isRoleAccount", False)
            details['is_free'] = entry.get("isFreeEmailAddress", False)
            details['is_catch_all'] = False  # Verifalia doesn't provide this directly
            
            passed = classification == "Deliverable"
            if passed:
                checks_passed.append('verifalia_api')
            else:
                checks_failed.append('verifalia_api')
            
            confidence_map = {"Deliverable": 40.0, "Risky": 20.0, "Undeliverable": 0.0, "Unknown": 10.0}
            confidence = confidence_map.get(classification, 10.0)
            
            if details.get('is_role'):
                confidence -= 5.0
            
            confidence = max(0.0, min(40.0, confidence))
            
            return VerificationPass(3, "Mailbox Validation", passed, confidence, checks_performed, checks_passed, checks_failed, details, self._elapsed_ms(start_time), 0.005)
        
        except Exception as e:
            logger.error(f"Verifalia error: {e}")
            checks_failed.append('verifalia_api')
            return VerificationPass(3, "Mailbox Validation", False, 0.0, checks_performed, [], checks_failed, {'error': str(e)}, self._elapsed_ms(start_time), 0.005)
    
    def _elapsed_ms(self, start_time: datetime) -> int:
        return int((datetime.utcnow() - start_time).total_seconds() * 1000)


def create_verification_service(username: str = None, password: str = None, enable_verifalia: bool = True) -> ThreePassVerificationService:
    """Create 3-pass verification service"""
    import os
    username = username or os.getenv("VERIFALIA_USERNAME")
    password = password or os.getenv("VERIFALIA_PASSWORD")
    return ThreePassVerificationService(username, password, enable_verifalia=enable_verifalia)
