"""
Seed database with pre-configured API templates.
Run this once to populate templates.
"""
import asyncio
from uuid import uuid4
from app.database import async_session
from app.models import APITemplate


TEMPLATES = [
    {
        "name": "Apollo.io - People Search",
        "provider": "apollo",
        "description": "Search for people by job title, company size, industry, etc.",
        "category": "b2b_data",
        "http_config": {
            "base_url": "https://api.apollo.io/v1",
            "endpoint": "/mixed_people/search",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json",
                "X-Api-Key": "{{api_key}}"
            },
            "auth_type": "header",
            "request_body": {
                "page": 1,
                "per_page": "{{per_page}}",
                "person_titles": "{{person_titles}}",
                "person_seniorities": "{{person_seniorities}}",
                "organization_num_employees_ranges": "{{company_sizes}}",
                "organization_industry_tag_ids": "{{industries}}"
            },
            "response_path": "people",
            "pagination": {
                "type": "body",
                "page_param": "page",
                "limit_param": "per_page",
                "max_pages": 10
            }
        },
        "default_field_mappings": {
            "email": "email",
            "first_name": "first_name",
            "last_name": "last_name",
            "job_title": "title",
            "linkedin_url": "linkedin_url",
            "phone": "phone_numbers[0].sanitized_number",
            "company_name": "organization.name",
            "company_website": "organization.website_url",
            "company_industry": "organization.industry",
            "company_size": "organization.estimated_num_employees",
            "seniority": "seniority"
        },
        "required_variables": ["api_key"],
        "optional_variables": {
            "per_page": 100,
            "person_titles": ["VP of Engineering", "CTO"],
            "person_seniorities": ["vp", "director"],
            "company_sizes": ["100-200", "201-500"],
            "industries": []
        },
        "setup_instructions": "1. Sign up at apollo.io\n2. Go to Settings > Integrations > API\n3. Copy your API key",
        "example_variables": {
            "api_key": "YOUR_APOLLO_API_KEY",
            "per_page": 100,
            "person_titles": ["VP of Engineering", "Head of Engineering"],
            "person_seniorities": ["vp", "director"],
            "company_sizes": ["100-200", "201-500"]
        },
        "api_docs_url": "https://apolloio.github.io/apollo-api-docs/",
        "pricing_info": "Free: 50 credits/month\nPaid: $49/month for 500 contacts"
    },
    
    {
        "name": "Hunter.io - Domain Search",
        "provider": "hunter",
        "description": "Find email addresses at specific companies/domains",
        "category": "email_finder",
        "http_config": {
            "base_url": "https://api.hunter.io/v2",
            "endpoint": "/domain-search",
            "method": "GET",
            "auth_type": "query",
            "query_params": {
                "api_key": "{{api_key}}",
                "domain": "{{domain}}",
                "limit": "{{limit}}",
                "department": "{{department}}",
                "seniority": "{{seniority}}"
            },
            "response_path": "data.emails",
            "pagination": {
                "type": "offset",
                "offset_param": "offset",
                "limit_param": "limit",
                "max_pages": 5
            }
        },
        "default_field_mappings": {
            "email": "value",
            "first_name": "first_name",
            "last_name": "last_name",
            "job_title": "position",
            "linkedin_url": "linkedin",
            "twitter_url": "twitter",
            "phone": "phone_number",
            "hunter_confidence": "confidence",
            "department": "department",
            "seniority": "seniority"
        },
        "required_variables": ["api_key", "domain"],
        "optional_variables": {
            "limit": 100,
            "department": "engineering",
            "seniority": "senior"
        },
        "setup_instructions": "1. Sign up at hunter.io\n2. Go to API settings\n3. Copy your API key",
        "example_variables": {
            "api_key": "YOUR_HUNTER_API_KEY",
            "domain": "stripe.com",
            "limit": 50,
            "department": "engineering"
        },
        "api_docs_url": "https://hunter.io/api-documentation/v2",
        "pricing_info": "Free: 25 searches/month\nPaid: $49/month for 500 searches"
    },
    
    {
        "name": "Clearbit Prospector",
        "provider": "clearbit",
        "description": "Find people at specific companies",
        "category": "b2b_data",
        "http_config": {
            "base_url": "https://prospector.clearbit.com/v1",
            "endpoint": "/people/search",
            "method": "GET",
            "headers": {
                "Authorization": "Bearer {{api_key}}"
            },
            "auth_type": "bearer",
            "query_params": {
                "domain": "{{domain}}",
                "role": "{{role}}",
                "seniority": "{{seniority}}",
                "limit": "{{limit}}"
            },
            "response_path": "results",
            "pagination": {
                "type": "page",
                "page_param": "page",
                "limit_param": "limit",
                "max_pages": 5
            }
        },
        "default_field_mappings": {
            "email": "email",
            "first_name": "name.givenName",
            "last_name": "name.familyName",
            "job_title": "title",
            "linkedin_url": "linkedin.handle",
            "twitter_url": "twitter.handle",
            "company_name": "company.name",
            "company_website": "company.domain",
            "company_industry": "company.category.industry",
            "company_size": "company.metrics.employees",
            "seniority": "seniority",
            "role": "role"
        },
        "required_variables": ["api_key"],
        "optional_variables": {
            "domain": "stripe.com",
            "role": "engineering",
            "seniority": "manager",
            "limit": 100
        },
        "setup_instructions": "1. Sign up at clearbit.com\n2. Go to Dashboard > API\n3. Copy your secret key",
        "example_variables": {
            "api_key": "YOUR_CLEARBIT_SECRET_KEY",
            "domain": "salesforce.com",
            "role": "engineering",
            "seniority": "manager",
            "limit": 50
        },
        "api_docs_url": "https://dashboard.clearbit.com/docs#prospector-api",
        "pricing_info": "Paid only: $99/month for 500 credits"
    }
]


async def seed_templates():
    """Insert API templates into database."""
    async with async_session() as db:
        for template_data in TEMPLATES:
            template = APITemplate(
                id=uuid4(),
                **template_data
            )
            db.add(template)
        
        await db.commit()
        print(f"✅ Seeded {len(TEMPLATES)} API templates")


if __name__ == "__main__":
    asyncio.run(seed_templates())