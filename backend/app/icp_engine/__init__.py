"""
ICP (Ideal Customer Profile) Engine.

A modular system for ingesting, scoring, and qualifying leads from multiple data sources.

Main components:
- Adapters: Connect to various data sources (HTTP APIs, CSV, Webhooks)
- Scorers: Calculate fit scores based on configurable rules
- Core: Field mapping, deduplication, ICP matching, scoring engine, orchestration

Usage:
    from app.icp_engine.core import IngestionOrchestrator
    
    orchestrator = IngestionOrchestrator(db)
    stats = await orchestrator.run_ingestion(data_source_id="...")
"""

__version__ = "1.0.0"
__all__ = ["adapters", "scorers", "core"]