"""Email verification service using ZeroBounce API."""

import logging
import re
from typing import Dict, Any, Optional
import httpx
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


class EmailVerificationService:
    """Verify email deliverability using ZeroBounce."""
    
    ZEROBOUNCE_URL = "https://api.zerobounce.net/v2/validate"
    
    # Common disposable email domains
    DISPOSABLE_DOMAINS = {
        'tempmail.com', 'guerrillamail.com', '10minutemail.com',
        'mailinator.com', 'throwaway.email', 'temp-mail.org',
        'fakeinbox.com', 'trashmail.com'
    }
    
    # Common role-based email prefixes
    ROLE_PREFIXES = {
        'info', 'admin', 'support', 'sales', 'marketing',
        'contact', 'hello', 'help', 'noreply', 'no-reply'
    }
    
    def __init__(self):
        self.api_key = settings.ZEROBOUNCE_API_KEY
        self.enabled = settings.ENABLE_VERIFICATION and bool(self.api_key)
    
    @staticmethod
    def validate_email_syntax(email: str) -> bool:
        """Validate email syntax using RFC 5322 regex."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def is_disposable(email: str) -> bool:
        """Check if email uses a disposable domain."""
        if '@' not in email:
            return False
        domain = email.split('@')[1].lower()
        return domain in EmailVerificationService.DISPOSABLE_DOMAINS
    
    @staticmethod
    def is_role_based(email: str) -> bool:
        """Check if email is role-based (info@, support@, etc)."""
        if '@' not in email:
            return False
        local_part = email.split('@')[0].lower()
        return local_part in EmailVerificationService.ROLE_PREFIXES
    
    async def verify_email(self, email: str, ip_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify email using ZeroBounce API.
        Returns verification results with deliverability score.
        """
        result = {
            'email': email,
            'verified': False,
            'verification_status': 'unknown',
            'deliverability_score': 0.0,
            'is_disposable': self.is_disposable(email),
            'is_role_based': self.is_role_based(email),
            'is_catch_all': False,
            'verified_at': datetime.utcnow().isoformat()
        }
        
        # Syntax validation (always performed)
        if not self.validate_email_syntax(email):
            result['verification_status'] = 'invalid'
            return result
        
        # If API not enabled, return basic validation
        if not self.enabled:
            result['verification_status'] = 'unknown'
            result['verified'] = True
            result['deliverability_score'] = 50.0  # Neutral score
            return result
        
        # Call ZeroBounce API
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                params = {
                    'api_key': self.api_key,
                    'email': email
                }
                if ip_address:
                    params['ip_address'] = ip_address
                
                response = await client.get(self.ZEROBOUNCE_URL, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    result = self._parse_zerobounce_response(data, email)
                    logger.info(f"Email verified: {email} - {result['verification_status']}")
                else:
                    logger.warning(f"ZeroBounce API error {response.status_code}")
                    result['verification_status'] = 'error'
                    
        except Exception as e:
            logger.error(f"Email verification failed for {email}: {e}")
            result['verification_status'] = 'error'
        
        return result
    
    def _parse_zerobounce_response(self, data: Dict, email: str) -> Dict[str, Any]:
        """Parse ZeroBounce API response."""
        status = data.get('status', 'unknown').lower()
        
        # Map ZeroBounce status to our internal status
        status_mapping = {
            'valid': ('valid', 100.0),
            'invalid': ('invalid', 0.0),
            'catch-all': ('risky', 70.0),
            'unknown': ('unknown', 50.0),
            'spamtrap': ('invalid', 0.0),
            'abuse': ('invalid', 0.0),
            'do_not_mail': ('invalid', 0.0)
        }
        
        mapped_status, base_score = status_mapping.get(status, ('unknown', 50.0))
        
        result = {
            'email': email,
            'verified': True,
            'verification_status': mapped_status,
            'deliverability_score': base_score,
            'is_disposable': data.get('disposable', False) or self.is_disposable(email),
            'is_role_based': data.get('role', False) or self.is_role_based(email),
            'is_catch_all': data.get('catch_all', False),
            'free_email': data.get('free_email', False),
            'mx_found': data.get('mx_found', False),
            'smtp_provider': data.get('smtp_provider'),
            'verified_at': datetime.utcnow().isoformat(),
            'raw_response': data  # Store full response for debugging
        }
        
        # Adjust score based on additional factors
        if result['is_disposable']:
            result['deliverability_score'] *= 0.5
        if result['is_role_based']:
            result['deliverability_score'] *= 0.8
        
        result['deliverability_score'] = round(result['deliverability_score'], 2)
        
        return result


# Singleton instance
verification_service = EmailVerificationService()
