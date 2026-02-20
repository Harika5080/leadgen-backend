# backend/app/services/email_verification_service.py
"""
Complete 3-Pass Email Verification System

Tools:
1. validator.js (via py3-validate-email) - Input validation
2. Mailchecker (via disposable-email-domains) - Syntax + MX + Disposable  
3. dnspython - DNS/MX validation
4. Verifalia REST API - Deep mailbox validation (NO SDK NEEDED)

Architecture:
- Pass 1: Syntax validation (FREE, instant)
- Pass 2: Domain/MX validation (FREE, ~1-2s)
- Pass 3: Mailbox validation (PAID, ~20-60s)

Field-Level Confidence Scoring:
- Each check contributes to overall confidence (0-100%)
- Early failures = low confidence, stop processing
- All passes = high confidence (95-100%)
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
    
    # Input
    email: str
    
    # Overall result
    is_valid: bool
    overall_status: str
    overall_confidence: float
    
    # Pass results
    passes_completed: int
    pass_1_result: Optional[VerificationPass]
    pass_2_result: Optional[VerificationPass]
    pass_3_result: Optional[VerificationPass]
    
    # Field-level scores
    syntax_score: float
    domain_score: float
    mailbox_score: float
    deliverability_score: float
    
    # Metadata
    is_disposable: bool
    is_role_account: bool
    is_free_provider: bool
    is_catch_all: bool
    
    # Details
    details: Dict
    provider: str = "3-pass-orchestration"
    total_cost: float = 0.0
    total_time_ms: int = 0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        result = asdict(self)
        # Convert Pass objects to dicts
        if self.pass_1_result:
            result['pass_1_result'] = self.pass_1_result.to_dict()
        if self.pass_2_result:
            result['pass_2_result'] = self.pass_2_result.to_dict()
        if self.pass_3_result:
            result['pass_3_result'] = self.pass_3_result.to_dict()
        return result


class ThreePassVerificationService:
    """
    Complete 3-Pass Email Verification Orchestrator
    
    Uses all 4 tools in proper sequence:
    1. validator.js - Input validation
    2. Mailchecker - Syntax + MX + Disposable
    3. dnspython - DNS/MX validation
    4. Verifalia REST API - Deep validation (NO SDK)
    """
    
    def __init__(
        self,
        verifalia_username: str = None,
        verifalia_password: str = None,
        smtp_timeout: int = 10,
        enable_smtp_probe: bool = False,  # Disabled by default (slow/unreliable)
        enable_verifalia: bool = True
    ):
        self.verifalia_username = verifalia_username
        self.verifalia_password = verifalia_password
        self.verifalia_base_url = "https://api.verifalia.com/v2.4"
        self.smtp_timeout = smtp_timeout
        self.enable_smtp_probe = enable_smtp_probe
        self.enable_verifalia = enable_verifalia
        
        if verifalia_username and verifalia_password:
            logger.info("✅ Verifalia credentials configured (REST API)")
        else:
            logger.warning("⚠️ Verifalia credentials not configured")
    
    async def verify_email(self, email: str) -> EmailVerificationResult:
        """
        Complete 3-pass email verification
        
        Returns comprehensive result with field-level confidence scores
        """
        start_time = datetime.utcnow()
        
        logger.info(f"🔍 Starting 3-pass verification for: {email}")
        
        # Initialize result tracking
        passes_completed = 0
        pass_1_result = None
        pass_2_result = None
        pass_3_result = None
        
        total_cost = 0.0
        
        # Field-level confidence scores
        syntax_score = 0.0
        domain_score = 0.0
        mailbox_score = 0.0
        deliverability_score = 0.0
        
        # Metadata flags
        is_disposable = False
        is_role_account = False
        is_free_provider = False
        is_catch_all = False
        
        try:
            # ═══════════════════════════════════════════════════════
            # PASS 1: Syntax & Format Validation (FREE, <100ms)
            # ═══════════════════════════════════════════════════════
            
            pass_1_result = await self._pass_1_syntax_validation(email)
            passes_completed = 1
            
            if not pass_1_result.passed:
                logger.info(f"❌ PASS 1 FAILED: {email} - {pass_1_result.details.get('reason')}")
                
                return EmailVerificationResult(
                    email=email,
                    is_valid=False,
                    overall_status="invalid_syntax",
                    overall_confidence=pass_1_result.confidence_contribution,
                    passes_completed=1,
                    pass_1_result=pass_1_result,
                    pass_2_result=None,
                    pass_3_result=None,
                    syntax_score=0.0,
                    domain_score=0.0,
                    mailbox_score=0.0,
                    deliverability_score=0.0,
                    is_disposable=pass_1_result.details.get('is_disposable', False),
                    is_role_account=False,
                    is_free_provider=False,
                    is_catch_all=False,
                    details=pass_1_result.details,
                    total_cost=0.0,
                    total_time_ms=self._elapsed_ms(start_time)
                )
            
            logger.info(f"✅ PASS 1 SUCCESS: {email}")
            syntax_score = pass_1_result.confidence_contribution
            is_disposable = pass_1_result.details.get('is_disposable', False)
            
            # ═══════════════════════════════════════════════════════
            # PASS 2: Domain & MX Validation (FREE, ~1-2s)
            # ═══════════════════════════════════════════════════════
            
            pass_2_result = await self._pass_2_domain_validation(email)
            passes_completed = 2
            
            if not pass_2_result.passed:
                logger.info(f"❌ PASS 2 FAILED: {email} - {pass_2_result.details.get('reason')}")
                
                domain_score = pass_2_result.confidence_contribution
                overall_confidence = syntax_score + domain_score
                
                return EmailVerificationResult(
                    email=email,
                    is_valid=False,
                    overall_status="invalid_domain",
                    overall_confidence=overall_confidence,
                    passes_completed=2,
                    pass_1_result=pass_1_result,
                    pass_2_result=pass_2_result,
                    pass_3_result=None,
                    syntax_score=syntax_score,
                    domain_score=domain_score,
                    mailbox_score=0.0,
                    deliverability_score=0.0,
                    is_disposable=is_disposable,
                    is_role_account=False,
                    is_free_provider=pass_2_result.details.get('is_free', False),
                    is_catch_all=False,
                    details={**pass_1_result.details, **pass_2_result.details},
                    total_cost=0.0,
                    total_time_ms=self._elapsed_ms(start_time)
                )
            
            logger.info(f"✅ PASS 2 SUCCESS: {email}")
            domain_score = pass_2_result.confidence_contribution
            is_free_provider = pass_2_result.details.get('is_free', False)
            
            # ═══════════════════════════════════════════════════════
            # PASS 3: Mailbox Validation (PAID, ~20-60s)
            # ═══════════════════════════════════════════════════════
            
            pass_3_result = await self._pass_3_mailbox_validation(email)
            passes_completed = 3
            total_cost = pass_3_result.cost
            
            logger.info(
                f"{'✅' if pass_3_result.passed else '❌'} PASS 3 COMPLETE: {email} - "
                f"Status: {pass_3_result.details.get('classification', 'Unknown')}"
            )
            
            # Calculate final scores
            mailbox_score = pass_3_result.confidence_contribution
            is_catch_all = pass_3_result.details.get('is_catch_all', False)
            is_role_account = pass_3_result.details.get('is_role', False)
            
            # Overall deliverability score (weighted)
            deliverability_score = (
                syntax_score * 0.2 +      # 20% weight
                domain_score * 0.3 +      # 30% weight
                mailbox_score * 0.5       # 50% weight (most important)
            )
            
            overall_confidence = syntax_score + domain_score + mailbox_score
            
            # Determine final status
            is_valid = pass_3_result.passed
            overall_status = pass_3_result.details.get('classification', 'Unknown')
            
            # Combine all details
            all_details = {
                **pass_1_result.details,
                **pass_2_result.details,
                **pass_3_result.details
            }
            
            return EmailVerificationResult(
                email=email,
                is_valid=is_valid,
                overall_status=overall_status,
                overall_confidence=overall_confidence,
                passes_completed=3,
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
    
    async def _pass_1_syntax_validation(self, email: str) -> VerificationPass:
        """
        PASS 1: Syntax & Format Validation
        
        Tools:
        1. validator.js (via py3-validate-email) - RFC 5322 validation
        2. Mailchecker - Disposable domain detection
        3. Custom regex - Additional format checks
        
        Returns: VerificationPass with 0-30% confidence
        """
        start_time = datetime.utcnow()
        
        checks_performed = []
        checks_passed = []
        checks_failed = []
        details = {}
        
        # Check 1: validator.js - RFC 5322 compliance
        checks_performed.append("validator_js_rfc5322")
        try:
            is_valid_format = validator_js_check(
                email_address=email,
                check_format=True,
                check_blacklist=False,
                check_dns=False,
                check_smtp=False
            )
            
            if is_valid_format:
                checks_passed.append("validator_js_rfc5322")
                details['rfc5322_compliant'] = True
            else:
                checks_failed.append("validator_js_rfc5322")
                details['rfc5322_compliant'] = False
                details['reason'] = "Invalid RFC 5322 format"
        except Exception as e:
            checks_failed.append("validator_js_rfc5322")
            details['validator_js_error'] = str(e)
            is_valid_format = False
        
        # Check 2: Basic regex validation
        checks_performed.append("regex_pattern")
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        regex_valid = bool(re.match(pattern, email))
        
        if regex_valid:
            checks_passed.append("regex_pattern")
        else:
            checks_failed.append("regex_pattern")
            if not details.get('reason'):
                details['reason'] = "Failed regex pattern match"
        
        # Check 3: Mailchecker - Disposable domain detection
        checks_performed.append("disposable_check")
        if "@" in email:
            domain = email.split("@")[1].lower()
            is_disposable = domain in disposable_domains
            
            details['is_disposable'] = is_disposable
            details['domain'] = domain
            
            if is_disposable:
                checks_failed.append("disposable_check")
                details['reason'] = "Disposable email domain"
            else:
                checks_passed.append("disposable_check")
        else:
            checks_failed.append("disposable_check")
            is_disposable = True
        
        # Check 4: Additional format checks
        checks_performed.append("format_checks")
        
        has_at = "@" in email
        parts = email.split("@") if has_at else []
        has_domain = len(parts) == 2
        
        format_checks = {
            "has_at_sign": has_at,
            "has_domain": has_domain,
            "local_part": parts[0] if has_domain else None,
            "domain_part": parts[1] if has_domain else None,
            "local_length": len(parts[0]) if has_domain else 0,
            "domain_has_dot": "." in parts[1] if has_domain else False,
            "not_too_long": len(email) <= 320,
            "no_consecutive_dots": ".." not in email
        }
        
        details.update(format_checks)
        
        all_format_valid = all([
            has_at,
            has_domain,
            format_checks['domain_has_dot'],
            format_checks['not_too_long'],
            format_checks['no_consecutive_dots']
        ])
        
        if all_format_valid:
            checks_passed.append("format_checks")
        else:
            checks_failed.append("format_checks")
        
        # Determine pass/fail
        passed = (
            is_valid_format and
            regex_valid and
            not is_disposable and
            all_format_valid
        )
        
        # Calculate confidence contribution (0-30%)
        confidence = 30.0 if passed else 0.0
        
        return VerificationPass(
            pass_number=1,
            pass_name="Syntax & Format Validation",
            passed=passed,
            confidence_contribution=confidence,
            checks_performed=checks_performed,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            details=details,
            processing_time_ms=self._elapsed_ms(start_time),
            cost=0.0
        )
    
    async def _pass_2_domain_validation(self, email: str) -> VerificationPass:
        """
        PASS 2: Domain & MX Validation
        
        Tools:
        1. dnspython - DNS resolution
        2. MX record validation
        3. Free provider detection
        
        Returns: VerificationPass with 0-30% confidence
        """
        start_time = datetime.utcnow()
        
        checks_performed = []
        checks_passed = []
        checks_failed = []
        details = {}
        
        domain = email.split("@")[1] if "@" in email else None
        
        if not domain:
            return VerificationPass(
                pass_number=2,
                pass_name="Domain & MX Validation",
                passed=False,
                confidence_contribution=0.0,
                checks_performed=["domain_extraction"],
                checks_passed=[],
                checks_failed=["domain_extraction"],
                details={"reason": "No domain found"},
                processing_time_ms=self._elapsed_ms(start_time),
                cost=0.0
            )
        
        # Check 1: DNS A record (domain exists)
        checks_performed.append("dns_a_record")
        try:
            dns.resolver.resolve(domain, 'A')
            checks_passed.append("dns_a_record")
            details['has_a_record'] = True
        except Exception as e:
            checks_failed.append("dns_a_record")
            details['has_a_record'] = False
            details['dns_error'] = str(e)
        
        # Check 2: MX records (can receive email)
        checks_performed.append("mx_records")
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            
            mx_list = [
                {
                    "host": str(record.exchange).rstrip('.'),
                    "priority": record.preference
                }
                for record in mx_records
            ]
            
            # Sort by priority
            mx_list.sort(key=lambda x: x['priority'])
            
            checks_passed.append("mx_records")
            details['has_mx'] = True
            details['mx_records'] = mx_list
            details['mx_count'] = len(mx_list)
            details['primary_mx'] = mx_list[0]['host'] if mx_list else None
            
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer) as e:
            checks_failed.append("mx_records")
            details['has_mx'] = False
            details['mx_error'] = "No MX records found"
            details['reason'] = "Domain has no mail servers (no MX records)"
        except Exception as e:
            checks_failed.append("mx_records")
            details['has_mx'] = False
            details['mx_error'] = str(e)
        
        # Check 3: Free email provider detection
        checks_performed.append("free_provider_check")
        
        free_providers = [
            'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
            'aol.com', 'icloud.com', 'mail.com', 'protonmail.com',
            'zoho.com', 'yandex.com', 'gmx.com', 'live.com'
        ]
        
        is_free = domain.lower() in free_providers
        details['is_free'] = is_free
        details['provider_type'] = 'free' if is_free else 'business'
        
        checks_passed.append("free_provider_check")
        
        # Determine pass/fail
        passed = details.get('has_mx', False)
        
        # Calculate confidence contribution (0-30%)
        if not passed:
            confidence = 0.0
        else:
            # Base confidence for valid domain
            confidence = 25.0
            
            # Bonus for business email (not free)
            if not is_free:
                confidence += 5.0
        
        return VerificationPass(
            pass_number=2,
            pass_name="Domain & MX Validation",
            passed=passed,
            confidence_contribution=confidence,
            checks_performed=checks_performed,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            details=details,
            processing_time_ms=self._elapsed_ms(start_time),
            cost=0.0
        )
    
    async def _pass_3_mailbox_validation(self, email: str) -> VerificationPass:
        """
        PASS 3: Mailbox Validation using Verifalia REST API
        
        Cost: $0.005 per email
        Returns: VerificationPass with 0-40% confidence
        """
        start_time = datetime.utcnow()
        
        checks_performed = ['verifalia_rest_api']
        checks_passed = []
        checks_failed = []
        details = {}
        cost = 0.0
        
        # Check if Verifalia is enabled and configured
        if not self.enable_verifalia or not self.verifalia_username or not self.verifalia_password:
            logger.warning("Verifalia not configured - skipping Pass 3")
            return VerificationPass(
                pass_number=3,
                pass_name="Mailbox Validation",
                passed=False,
                confidence_contribution=0.0,
                checks_performed=['verifalia_skipped'],
                checks_passed=[],
                checks_failed=['verifalia_skipped'],
                details={'skip_reason': 'Verifalia not configured'},
                processing_time_ms=self._elapsed_ms(start_time),
                cost=0.0
            )
        
        try:
            # Call Verifalia REST API
            response = requests.post(
                f"{self.verifalia_base_url}/email-validations",
                auth=(self.verifalia_username, self.verifalia_password),
                json={
                    "entries": [{"inputData": email}],
                    "quality": "Standard",
                    "deduplication": "Off"
                },
                params={"waitTime": "120s"},
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                timeout=130
            )
            
            if response.status_code != 200:
                logger.error(f"Verifalia API error: {response.status_code}")
                checks_failed.append('verifalia_rest_api')
                return VerificationPass(
                    pass_number=3,
                    pass_name="Mailbox Validation",
                    passed=False,
                    confidence_contribution=0.0,
                    checks_performed=checks_performed,
                    checks_passed=[],
                    checks_failed=checks_failed,
                    details={'error': f'API error {response.status_code}'},
                    processing_time_ms=self._elapsed_ms(start_time),
                    cost=0.005  # Charged even on error
                )
            
            data = response.json()
            
            # Check completion status
            overview = data.get("overview", {})
            if overview.get("status") != "Completed":
                logger.warning(f"Verifalia not completed: {overview.get('status')}")
                checks_failed.append('verifalia_rest_api')
                return VerificationPass(
                    pass_number=3,
                    pass_name="Mailbox Validation",
                    passed=False,
                    confidence_contribution=0.0,
                    checks_performed=checks_performed,
                    checks_passed=[],
                    checks_failed=checks_failed,
                    details={'error': 'Not completed', 'status': overview.get('status')},
                    processing_time_ms=self._elapsed_ms(start_time),
                    cost=0.005
                )
            
            # Extract results
            entries_data = data.get("entries", {}).get("data", [])
            
            if not entries_data:
                logger.error("No entries in Verifalia response")
                checks_failed.append('verifalia_rest_api')
                return VerificationPass(
                    pass_number=3,
                    pass_name="Mailbox Validation",
                    passed=False,
                    confidence_contribution=0.0,
                    checks_performed=checks_performed,
                    checks_passed=[],
                    checks_failed=checks_failed,
                    details={'error': 'No entries in result'},
                    processing_time_ms=self._elapsed_ms(start_time),
                    cost=0.005
                )
            
            entry = entries_data[0]
            classification = entry.get("classification", "Unknown")
            
            # Store details
            details['classification'] = classification
            details['status'] = entry.get("status")
            details['email_address'] = entry.get("emailAddress")
            details['is_role'] = entry.get("isRoleAccount", False)
            details['is_free'] = entry.get("isFreeEmailAddress", False)
            details['has_international_domain'] = entry.get("hasInternationalDomainName", False)
            details['domain_part'] = entry.get("emailAddressDomainPart")
            details['local_part'] = entry.get("emailAddressLocalPart")
            details['is_catch_all'] = False  # Verifalia doesn't provide this in standard
            
            # Determine pass/fail
            passed = classification == "Deliverable"
            cost = 0.005
            
            if passed:
                checks_passed.append('verifalia_rest_api')
            else:
                checks_failed.append('verifalia_rest_api')
            
            # Calculate confidence (0-40%)
            confidence_map = {
                "Deliverable": 40.0,
                "Risky": 20.0,
                "Undeliverable": 0.0,
                "Unknown": 10.0
            }
            
            confidence = confidence_map.get(classification, 10.0)
            
            # Adjust for role account
            if details.get('is_role'):
                confidence -= 5.0
            
            confidence = max(0.0, min(40.0, confidence))
            
            return VerificationPass(
                pass_number=3,
                pass_name="Mailbox Validation",
                passed=passed,
                confidence_contribution=confidence,
                checks_performed=checks_performed,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                details=details,
                processing_time_ms=self._elapsed_ms(start_time),
                cost=cost
            )
        
        except requests.exceptions.Timeout:
            logger.error(f"Verifalia timeout for {email}")
            checks_failed.append('verifalia_rest_api')
            return VerificationPass(
                pass_number=3,
                pass_name="Mailbox Validation",
                passed=False,
                confidence_contribution=0.0,
                checks_performed=checks_performed,
                checks_passed=[],
                checks_failed=checks_failed,
                details={'error': 'Request timeout'},
                processing_time_ms=self._elapsed_ms(start_time),
                cost=0.005  # Charged even on timeout
            )
        except Exception as e:
            logger.error(f"Verifalia error: {e}")
            checks_failed.append('verifalia_rest_api')
            return VerificationPass(
                pass_number=3,
                pass_name="Mailbox Validation",
                passed=False,
                confidence_contribution=0.0,
                checks_performed=checks_performed,
                checks_passed=[],
                checks_failed=checks_failed,
                details={'error': str(e)},
                processing_time_ms=self._elapsed_ms(start_time),
                cost=0.005  # Charged even on error
            )
    
    def _elapsed_ms(self, start_time: datetime) -> int:
        """Calculate elapsed milliseconds"""
        return int((datetime.utcnow() - start_time).total_seconds() * 1000)


def create_verification_service(
    username: str = None,
    password: str = None,
    enable_smtp_probe: bool = False,
    enable_verifalia: bool = True
) -> ThreePassVerificationService:
    """Create 3-pass verification service"""
    import os
    
    username = username or os.getenv("VERIFALIA_USERNAME")
    password = password or os.getenv("VERIFALIA_PASSWORD")
    
    return ThreePassVerificationService(
        verifalia_username=username,
        verifalia_password=password,
        enable_smtp_probe=enable_smtp_probe,
        enable_verifalia=enable_verifalia
    )