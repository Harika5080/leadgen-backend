# Authentication Guide

## Overview

The Lead Generation Platform uses two authentication methods:

### 1. JWT Token Authentication (Human Users)

**Used for:** Web interface, user actions
**Obtained via:** Login endpoint
**Valid for:** 24 hours

#### Login Example:
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@test.com",
    "password": "AdminPassword123!"
  }'
```

#### Using the Token:
```bash
curl -X GET http://localhost:8000/api/v1/leads \
  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE"
```

#### Endpoints requiring JWT:
- `GET /api/v1/leads` - List leads
- `GET /api/v1/leads/{id}` - Get lead details
- `PUT /api/v1/leads/{id}/review` - Review lead
- `POST /api/v1/auth/users` - Create user (admin only)
- `GET /api/v1/auth/me` - Get current user info

### 2. API Key Authentication (Machine-to-Machine)

**Used for:** External systems, batch uploads
**Obtained via:** Tenant settings (pre-generated)
**Valid for:** No expiration (can be rotated)

#### Usage Example:
```bash
curl -X POST http://localhost:8000/api/v1/leads/batch \
  -H "Authorization: Bearer sk_live_test_key_12345" \
  -H "Content-Type: application/json" \
  -d '{
    "source_name": "my_scraper",
    "leads": [...]
  }'
```

#### Endpoints requiring API Key:
- `POST /api/v1/leads/batch` - Batch upload leads

## Test Credentials

### JWT Authentication:
- **Admin User:**
  - Email: `admin@test.com`
  - Password: `AdminPassword123!`
  - Role: admin (full access)

- **Reviewer User:**
  - Email: `reviewer@test.com`
  - Password: `ReviewerPass123!`
  - Role: reviewer (can review leads)

### API Key:
- **Test Tenant:**
  - API Key: `sk_live_test_key_12345`
  - Use for batch uploads

## Security Notes

1. API keys should be kept secret and rotated regularly
2. JWT tokens expire after 24 hours
3. Always use HTTPS in production
4. Never commit credentials to version control
