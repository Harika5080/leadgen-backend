# Add these imports at the top of enrichment_service.py

from app.services.google_kg_service import create_google_kg_service
from app.services.apollo_service import create_apollo_service

# Add this method to EnrichmentService class:

async def _enrich_with_multiple_sources(
    self,
    company_domain: str,
    company_name: str
) -> Dict[str, Any]:
    """
    Waterfall enrichment from multiple sources
    
    Order:
    1. Wappalyzer (tech stack) - FREE
    2. SerpApi (company info) - $0.002
    3. Google KG (employee count) - FREE
    4. Apollo (complete data) - Uses quota
    
    Returns all enriched data combined
    """
    all_enriched = {}
    providers_used = []
    total_cost = 0.0
    
    # 1️⃣ Wappalyzer (tech stack)
    if company_domain:
        wapp_result = await self._enrich_from_wappalyzer(company_domain)
        if wapp_result:
            all_enriched.update(wapp_result)
            providers_used.append("wappalyzer")
            logger.info("  ✅ Wappalyzer: Added tech stack")
    
    # 2️⃣ SerpApi (company info)
    if company_name:
        serp_result = await self._enrich_from_serpapi(company_name)
        if serp_result:
            all_enriched.update(serp_result)
            providers_used.append("serpapi")
            total_cost += 0.002
            logger.info("  ✅ SerpApi: Added company info")
    
    # 3️⃣ Google Knowledge Graph (employee count, FREE)
    if company_name and not all_enriched.get('company_employee_count'):
        google_kg = create_google_kg_service()
        kg_result = await google_kg.enrich_company(company_name, company_domain)
        if kg_result:
            # Only add fields we don't already have
            for key, value in kg_result.items():
                if key not in all_enriched or not all_enriched[key]:
                    all_enriched[key] = value
            providers_used.append("google_kg")
            logger.info(f"  ✅ Google KG: Added {list(kg_result.keys())}")
    
    # 4️⃣ Apollo (fallback for missing critical data)
    critical_missing = []
    if not all_enriched.get('company_employee_count'):
        critical_missing.append('employee_count')
    if not all_enriched.get('company_industry'):
        critical_missing.append('industry')
    
    if critical_missing and company_domain:
        logger.info(f"  ℹ️ Missing critical fields: {critical_missing}, trying Apollo...")
        apollo = create_apollo_service()
        apollo_result = await apollo.enrich_company(company_domain, company_name)
        if apollo_result:
            # Only add missing fields from Apollo
            for key, value in apollo_result.items():
                if key not in all_enriched or not all_enriched[key]:
                    all_enriched[key] = value
            providers_used.append("apollo")
            logger.info(f"  ✅ Apollo: Added {list(apollo_result.keys())}")
    
    return {
        "enriched_data": all_enriched,
        "providers_used": providers_used,
        "cost": total_cost
    }
