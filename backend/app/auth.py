"""Authentication and authorization utilities."""

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import secrets
import bcrypt
import logging

from app.config import settings
from app.database import get_db
from app.models import Tenant, User

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def generate_api_key() -> str:
    """Generate a cryptographically secure API key."""
    random_part = secrets.token_urlsafe(32)
    return f"sk_live_{random_part}"


def hash_api_key(api_key: str) -> str:
    """Hash an API key for secure storage using bcrypt."""
    return bcrypt.hashpw(api_key.encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify an API key against its stored hash."""
    try:
        return bcrypt.checkpw(plain_key.encode('utf-8'), hashed_key.encode('utf-8'))
    except Exception as e:
        logger.error(f"API key verification failed: {e}")
        return False


def hash_password(password: str) -> str:
    """Hash a password for user authentication."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token with specified expiration."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """Verify API key and return the associated tenant."""
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    api_key = credentials.credentials
    
    # Query all active tenants
    result = await db.execute(
        select(Tenant).where(Tenant.status == "active")
    )
    tenants = result.scalars().all()
    
    # Verify API key against each tenant
    for tenant in tenants:
        if verify_api_key(api_key, tenant.api_key_hash):
            logger.info(f"API key authenticated for tenant: {tenant.id}")
            return tenant
    
    logger.warning(f"API key authentication failed")
    raise credentials_exception


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Verify JWT token and return the associated user."""
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        
        email: str = payload.get("sub")
        tenant_id: str = payload.get("tenant_id")
        
        if email is None or tenant_id is None:
            raise credentials_exception
        
        # Query user
        result = await db.execute(
            select(User).where(User.email == email, User.is_active == True)
        )
        user = result.scalar_one_or_none()
        
        if user is None:
            raise credentials_exception
        
        logger.info(f"User authenticated: {email}")
        return user
        
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise credentials_exception


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Verify current user has admin role."""
    
    if current_user.role != "admin":
        logger.warning(f"Admin access denied for user: {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    return current_user


# Alias for compatibility with other modules
require_admin = get_current_admin_user