# backend/app/routes/config.py
# API endpoints for dynamic configuration
# NO HARDCODED VALUES - Everything from database!

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime

from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/api/v1/config", tags=["configuration"])

# ============================================================================
# SCRAPER TYPES
# ============================================================================

class ScraperTypeCreate(BaseModel):
    value: str
    label: str
    category: str  # API | Scraper | Custom
    description: Optional[str] = None
    github_stars: Optional[str] = None
    github_forks: Optional[str] = None
    github_url: Optional[str] = None
    license: Optional[str] = None
    documentation_url: Optional[str] = None
    default_config_template: dict = {}
    enabled: bool = True
    display_order: int = 0

class ScraperTypeResponse(BaseModel):
    id: UUID
    value: str
    label: str
    category: str
    description: Optional[str]
    github_stars: Optional[str]
    github_forks: Optional[str]
    github_url: Optional[str]
    license: Optional[str]
    documentation_url: Optional[str]
    default_config_template: dict
    enabled: bool
    is_system: bool
    display_order: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

@router.get("/scraper-types", response_model=List[ScraperTypeResponse])
async def list_scraper_types(
    enabled: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get all scraper types (100% dynamic from database)
    No hardcoded values!
    """
    query = db.query(ScraperType)
    
    if enabled is not None:
        query = query.filter(ScraperType.enabled == enabled)
    
    if category:
        query = query.filter(ScraperType.category == category)
    
    scraper_types = query.order_by(ScraperType.display_order).all()
    return scraper_types

@router.get("/scraper-types/{scraper_type_id}", response_model=ScraperTypeResponse)
async def get_scraper_type(
    scraper_type_id: UUID,
    db: Session = Depends(get_db)
):
    """Get single scraper type"""
    scraper_type = db.query(ScraperType).filter(
        ScraperType.id == scraper_type_id
    ).first()
    
    if not scraper_type:
        raise HTTPException(status_code=404, detail="Scraper type not found")
    
    return scraper_type

@router.post("/scraper-types", response_model=ScraperTypeResponse)
async def create_scraper_type(
    data: ScraperTypeCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create new scraper type (add your own scrapers!)"""
    # Check if value already exists
    existing = db.query(ScraperType).filter(
        ScraperType.value == data.value
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Scraper type with value '{data.value}' already exists"
        )
    
    scraper_type = ScraperType(
        **data.dict(),
        created_by=current_user.id,
        is_system=False  # User-created types are not system types
    )
    
    db.add(scraper_type)
    db.commit()
    db.refresh(scraper_type)
    
    return scraper_type

@router.put("/scraper-types/{scraper_type_id}", response_model=ScraperTypeResponse)
async def update_scraper_type(
    scraper_type_id: UUID,
    data: ScraperTypeCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update existing scraper type"""
    scraper_type = db.query(ScraperType).filter(
        ScraperType.id == scraper_type_id
    ).first()
    
    if not scraper_type:
        raise HTTPException(status_code=404, detail="Scraper type not found")
    
    for key, value in data.dict().items():
        setattr(scraper_type, key, value)
    
    db.commit()
    db.refresh(scraper_type)
    
    return scraper_type

@router.delete("/scraper-types/{scraper_type_id}")
async def delete_scraper_type(
    scraper_type_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete scraper type (system types cannot be deleted)"""
    scraper_type = db.query(ScraperType).filter(
        ScraperType.id == scraper_type_id
    ).first()
    
    if not scraper_type:
        raise HTTPException(status_code=404, detail="Scraper type not found")
    
    if scraper_type.is_system:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete system scraper types"
        )
    
    # Check if in use
    in_use = db.query(DataSource).filter(
        DataSource.scraper_type_id == scraper_type_id
    ).count()
    
    if in_use > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete: {in_use} data sources use this scraper type"
        )
    
    db.delete(scraper_type)
    db.commit()
    
    return {"message": "Scraper type deleted successfully"}

# ============================================================================
# TRANSFORMATION FUNCTIONS
# ============================================================================

class TransformationCreate(BaseModel):
    value: str
    label: str
    description: Optional[str] = None
    function_type: str  # builtin | custom | javascript
    implementation: Optional[str] = None
    input_type: Optional[str] = "any"
    output_type: Optional[str] = "any"
    requires_custom_code: bool = False
    category: Optional[str] = "custom"
    enabled: bool = True
    examples: Optional[list] = []

class TransformationResponse(BaseModel):
    id: UUID
    value: str
    label: str
    description: Optional[str]
    function_type: str
    implementation: Optional[str]
    input_type: Optional[str]
    output_type: Optional[str]
    requires_custom_code: bool
    category: Optional[str]
    enabled: bool
    is_system: bool
    display_order: int
    examples: Optional[list]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

@router.get("/transformations", response_model=List[TransformationResponse])
async def list_transformations(
    enabled: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get all transformation functions (100% dynamic from database)
    No hardcoded transformations!
    """
    query = db.query(TransformationFunction)
    
    if enabled is not None:
        query = query.filter(TransformationFunction.enabled == enabled)
    
    if category:
        query = query.filter(TransformationFunction.category == category)
    
    transformations = query.order_by(TransformationFunction.display_order).all()
    return transformations

@router.post("/transformations", response_model=TransformationResponse)
async def create_transformation(
    data: TransformationCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create custom transformation function"""
    transformation = TransformationFunction(
        **data.dict(),
        is_system=False
    )
    
    db.add(transformation)
    db.commit()
    db.refresh(transformation)
    
    return transformation

@router.post("/transformations/{transformation_id}/test")
async def test_transformation(
    transformation_id: UUID,
    sample_value: str,
    db: Session = Depends(get_db)
):
    """Test a transformation with sample data"""
    transformation = db.query(TransformationFunction).filter(
        TransformationFunction.id == transformation_id
    ).first()
    
    if not transformation:
        raise HTTPException(status_code=404, detail="Transformation not found")
    
    try:
        # Execute transformation (safely)
        # In production, use sandboxed JavaScript execution
        result = apply_transformation(transformation.implementation, sample_value)
        return {"result": result, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}

# ============================================================================
# TARGET LEAD FIELDS
# ============================================================================

class TargetFieldCreate(BaseModel):
    value: str
    label: str
    field_type: str  # string | email | phone | url | number
    required: bool = False
    category: Optional[str] = "contact"
    help_text: Optional[str] = None
    validation_regex: Optional[str] = None
    enabled: bool = True

class TargetFieldResponse(BaseModel):
    id: UUID
    value: str
    label: str
    field_type: str
    required: bool
    category: Optional[str]
    help_text: Optional[str]
    validation_regex: Optional[str]
    enabled: bool
    is_system: bool
    display_order: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

@router.get("/target-fields", response_model=List[TargetFieldResponse])
async def list_target_fields(
    enabled: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    required: Optional[bool] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get all target lead fields (100% dynamic from database)
    No hardcoded fields!
    """
    query = db.query(TargetLeadField)
    
    if enabled is not None:
        query = query.filter(TargetLeadField.enabled == enabled)
    
    if category:
        query = query.filter(TargetLeadField.category == category)
    
    if required is not None:
        query = query.filter(TargetLeadField.required == required)
    
    fields = query.order_by(TargetLeadField.display_order).all()
    return fields

@router.post("/target-fields", response_model=TargetFieldResponse)
async def create_target_field(
    data: TargetFieldCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create custom target field"""
    field = TargetLeadField(
        **data.dict(),
        is_system=False
    )
    
    db.add(field)
    db.commit()
    db.refresh(field)
    
    return field

@router.post("/target-fields/reorder")
async def reorder_target_fields(
    ordered_ids: List[UUID],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reorder target fields (drag & drop)"""
    for index, field_id in enumerate(ordered_ids):
        db.query(TargetLeadField).filter(
            TargetLeadField.id == field_id
        ).update({"display_order": index})
    
    db.commit()
    return {"message": "Fields reordered successfully"}

# ============================================================================
# BULK OPERATIONS
# ============================================================================

@router.get("/export")
async def export_configuration(db: Session = Depends(get_db)):
    """Export all configuration (backup)"""
    return {
        "scraper_types": [s.to_dict() for s in db.query(ScraperType).all()],
        "transformations": [t.to_dict() for t in db.query(TransformationFunction).all()],
        "target_fields": [f.to_dict() for f in db.query(TargetLeadField).all()],
    }

@router.post("/import")
async def import_configuration(
    data: dict,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Import configuration (restore from backup)"""
    # Import logic here
    pass

@router.post("/reset-defaults")
async def reset_to_defaults(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Reset to default configuration"""
    # Re-run seed migration
    pass


# ============================================================================
# DATABASE MODELS (Add to models.py)
# ============================================================================

from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

class ScraperType(Base):
    __tablename__ = "scraper_types"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    value = Column(String(100), unique=True, nullable=False)
    label = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)
    description = Column(Text)
    github_stars = Column(String(20))
    github_forks = Column(String(20))
    github_url = Column(Text)
    license = Column(String(100))
    documentation_url = Column(Text)
    default_config_template = Column(JSONB, nullable=False, default={})
    enabled = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)
    display_order = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    # Relationships
    data_sources = relationship("DataSource", back_populates="scraper_type")

class TransformationFunction(Base):
    __tablename__ = "transformation_functions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    value = Column(String(100), unique=True, nullable=False)
    label = Column(String(255), nullable=False)
    description = Column(Text)
    function_type = Column(String(50), nullable=False)
    implementation = Column(Text)
    input_type = Column(String(50))
    output_type = Column(String(50))
    requires_custom_code = Column(Boolean, default=False)
    category = Column(String(50))
    enabled = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)
    display_order = Column(Integer, default=0)
    examples = Column(JSONB, default=[])
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

class TargetLeadField(Base):
    __tablename__ = "target_lead_fields"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    value = Column(String(100), unique=True, nullable=False)
    label = Column(String(255), nullable=False)
    field_type = Column(String(50), nullable=False)
    required = Column(Boolean, default=False)
    category = Column(String(50))
    help_text = Column(Text)
    validation_regex = Column(Text)
    enabled = Column(Boolean, default=True)
    is_system = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())