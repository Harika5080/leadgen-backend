"""Lead data normalization service."""

import re
import logging
from typing import Dict, Any, Optional
import phonenumbers
from nameparser import HumanName

logger = logging.getLogger(__name__)


class NormalizationService:
    """Normalize and standardize lead data."""
    
    @staticmethod
    def normalize_email(email: str) -> str:
        """
        Normalize email address.
        - Convert to lowercase
        - Strip whitespace
        """
        if not email:
            return ""
        return email.lower().strip()
    
    @staticmethod
    def extract_domain(email: str) -> Optional[str]:
        """Extract domain from email address."""
        if not email or '@' not in email:
            return None
        return email.split('@')[1].lower()
    
    @staticmethod
    def normalize_name(first_name: Optional[str], last_name: Optional[str], 
                       full_name: Optional[str] = None) -> Dict[str, Optional[str]]:
        """
        Normalize and parse names.
        Handles various name formats and returns standardized first/last names.
        """
        # If we have both first and last, just clean them
        if first_name and last_name:
            return {
                'first_name': first_name.strip().title() if first_name else None,
                'last_name': last_name.strip().title() if last_name else None
            }
        
        # If we have a full name, parse it
        if full_name:
            parsed = HumanName(full_name)
            return {
                'first_name': parsed.first or None,
                'last_name': parsed.last or None
            }
        
        # If we only have one name field, try to parse it
        if first_name and not last_name:
            parsed = HumanName(first_name)
            return {
                'first_name': parsed.first or first_name.strip().title(),
                'last_name': parsed.last or None
            }
        
        return {
            'first_name': first_name.strip().title() if first_name else None,
            'last_name': last_name.strip().title() if last_name else None
        }
    
    @staticmethod
    def normalize_phone(phone: Optional[str], default_region: str = "US") -> Optional[str]:
        """
        Normalize phone number to E.164 format.
        Returns None if parsing fails.
        """
        if not phone:
            return None
        
        try:
            # Remove common separators and whitespace
            cleaned = re.sub(r'[\s\-\(\)\.]', '', phone)
            
            # Parse phone number
            parsed = phonenumbers.parse(cleaned, default_region)
            
            # Format to E.164
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, 
                    phonenumbers.PhoneNumberFormat.E164
                )
        except phonenumbers.NumberParseException:
            logger.debug(f"Failed to parse phone number: {phone}")
        
        return phone  # Return original if parsing fails
    
    @staticmethod
    def normalize_job_title(title: Optional[str]) -> Optional[str]:
        """
        Normalize job title.
        - Standardize capitalization
        - Remove extra whitespace
        """
        if not title:
            return None
        
        # Remove extra whitespace
        normalized = ' '.join(title.split())
        
        # Title case for common patterns
        return normalized.title()
    
    @staticmethod
    def normalize_url(url: Optional[str]) -> Optional[str]:
        """
        Normalize URL.
        - Add https:// if missing
        - Remove trailing slashes
        - Lowercase domain
        """
        if not url:
            return None
        
        url = url.strip()
        
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        
        # Remove trailing slash
        url = url.rstrip('/')
        
        return url
    
    def normalize_lead(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize all fields in a lead record.
        Returns updated lead data with normalized fields.
        """
        normalized = lead_data.copy()
        
        # Normalize email and extract domain
        if 'email' in normalized:
            normalized['email'] = self.normalize_email(normalized['email'])
            normalized['company_domain'] = self.extract_domain(normalized['email'])
        
        # Normalize names
        name_result = self.normalize_name(
            first_name=normalized.get('first_name'),
            last_name=normalized.get('last_name')
        )
        normalized['first_name'] = name_result['first_name']
        normalized['last_name'] = name_result['last_name']
        
        # Normalize phone
        if 'phone' in normalized:
            normalized['phone'] = self.normalize_phone(normalized['phone'])
        
        # Normalize job title
        if 'job_title' in normalized:
            normalized['job_title'] = self.normalize_job_title(normalized['job_title'])
        
        # Normalize URLs
        if 'company_website' in normalized:
            normalized['company_website'] = self.normalize_url(normalized['company_website'])
        
        if 'linkedin_url' in normalized:
            normalized['linkedin_url'] = self.normalize_url(normalized['linkedin_url'])
        
        logger.debug(f"Normalized lead: {normalized.get('email')}")
        
        return normalized


# Singleton instance
normalization_service = NormalizationService()
