"""Main FastAPI application - FIXED with scraper routes."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRITICAL: Import database and ALL models FIRST!
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from app.database import Base, engine

# Import ALL models to register them with SQLAlchemy
from app.models import (
    # Core models
    Tenant,
    User,
    ICP,
    Lead,
    LeadICPAssignment,
    DataSource,
    
    # Raw lead models
    RawLead,
    RawLeadProcessing,
    
    # Supporting models
    ScoringRule,
    LeadNote,
    LeadProcessingStage,
    LeadRejectionTracking,
    LeadActivity,
    LeadFitScore,
    LeadConversion,
    
    # Connector models
    Connector,
    ConnectorRun,
    IngestionJob,
    
    # Workflow models
    WorkflowStatus,
    WorkflowTransition,
    
    # System models
    APITemplate,
    AuditLog,
    SystemSettings,
    TenantSettings,
    Source,
)



# Import scraper routes (FIXED - removed indentation)
from app.routers import scraper_routes

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Now imports can safely use the models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Import existing routers
from app.api import auth, leads, pipeline
from app.routers import (
    settings, 
    leads_export,
    analytics_routes,
    csv_import_routes,
    connector_routes,
    instantly_routes
)

# Import WebSocket
from app.websocket import get_socket_app

# Import scheduler
from app.scheduler import start_scheduler

from app.routers import (
    icp_routes, 
    data_source_routes, 
    ingestion_routes, 
    api_template_routes,
    lead_routes,
    processing_routes
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Lead Generation Automation API",
    description="Multi-tenant lead processing and automation platform",
    version="1.0.0",
    redirect_slashes=False  # ← CRITICAL: Prevents 307 redirects
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# ROUTER REGISTRATION (Order matters!)
# ============================================

# Authentication (must be first)
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])

# Specific /leads routes (before main leads router)
app.include_router(leads_export.router, prefix="/api/v1/leads", tags=["Export"])
app.include_router(csv_import_routes.router, prefix="/api/v1", tags=["csv-import"])

# ============================================
# SCRAPER ROUTES - Add here!
# ============================================
app.include_router(scraper_routes.router)  # Already has /api/v1/scrapers prefix

# ============================================
# PHASE 1 ROUTES
# ============================================
from app.routers import workflow_routes, activity_routes, conversion_routes
app.include_router(workflow_routes.router, tags=["workflows"])
app.include_router(activity_routes.router, tags=["activities"])
app.include_router(conversion_routes.router, tags=["conversions"])

# Other routers
app.include_router(pipeline.router, prefix="/api/v1/pipeline", tags=["Pipeline"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["Settings"])
app.include_router(analytics_routes.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(instantly_routes.router, prefix="/api/v1", tags=["instantly"])
app.include_router(connector_routes.router, prefix="/api/v1", tags=["connectors"]) 

app.include_router(icp_routes.router)
app.include_router(data_source_routes.router)
app.include_router(ingestion_routes.router)
app.include_router(api_template_routes.router)
app.include_router(lead_routes.router)  
app.include_router(processing_routes.router)



# Mount WebSocket
socket_app = get_socket_app()
app.mount("/socket.io", socket_app)

# ============================================
# HEALTH & ROOT ENDPOINTS
# ============================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "registered_tables": len(Base.metadata.tables),
        "tables": list(Base.metadata.tables.keys()),
        "features": [
            "authentication",
            "lead_processing",
            "settings_management",
            "export_services",
            "websocket_notifications",
            "workflow_management",
            "activity_tracking",
            "conversion_tracking",
            "linkedin_scraper"  # Added!
        ]
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Lead Generation Automation API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


# ============================================
# STARTUP & SHUTDOWN
# ============================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info("Starting Lead Generation Automation API...")
    logger.info("=" * 50)
    logger.info(f"Registered {len(Base.metadata.tables)} SQLAlchemy tables:")
    for table_name in sorted(Base.metadata.tables.keys()):
        logger.info(f"  ✓ {table_name}")
    logger.info("=" * 50)
    logger.info("Registered Routes:")
    for route in app.routes:
        if hasattr(route, 'path'):
            logger.info(f"  {route.path}")
    logger.info("=" * 50)
    
    # Start APScheduler
    start_scheduler()
    
    logger.info("Application started successfully!")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("Shutting down Lead Generation Automation API...")