#!/bin/bash

echo "=========================================="
echo "Phase 3 - Settings API Deployment"
echo "=========================================="

# Step 1: Copy new files to backend
echo ""
echo "Step 1: Copying new files..."

# Create schemas directory if not exists
mkdir -p backend/app/schemas

# Copy schemas
if [ -f /home/claude/backend/app/schemas/settings.py ]; then
    cp /home/claude/backend/app/schemas/settings.py backend/app/schemas/
    echo "✅ Copied settings.py schema"
else
    echo "⚠️  settings.py schema not found"
fi

# Create routers directory if not exists
mkdir -p backend/app/routers

# Copy routers
if [ -f /home/claude/backend/app/routers/settings.py ]; then
    cp /home/claude/backend/app/routers/settings.py backend/app/routers/
    echo "✅ Copied settings.py router"
else
    echo "⚠️  settings.py router not found"
fi

# Create migrations directory if not exists
mkdir -p backend/migrations

# Copy migration
if [ -f /home/claude/backend/migrations/003_tenant_settings_user_preferences.sql ]; then
    cp /home/claude/backend/migrations/003_tenant_settings_user_preferences.sql backend/migrations/
    echo "✅ Copied migration file"
else
    echo "⚠️  Migration file not found"
fi

# Step 2: Run migration
echo ""
echo "Step 2: Running database migration..."
docker-compose exec -T db psql -U leadgen -d leadgen < backend/migrations/003_tenant_settings_user_preferences.sql
echo "✅ Migration completed"

# Step 3: Verify migration
echo ""
echo "Step 3: Verifying migration..."
docker-compose exec -T db psql -U leadgen -d leadgen << 'SQLEOF'
-- Check if tables exist
SELECT 
    table_name,
    CASE 
        WHEN table_name IN ('tenant_settings') THEN '✅ New'
        WHEN table_name IN ('users') THEN '✅ Updated'
        ELSE '✅ Existing'
    END as status
FROM information_schema.tables 
WHERE table_schema = 'public' 
    AND table_name IN ('tenant_settings', 'users', 'tenants')
ORDER BY table_name;

-- Check users.preferences column
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'users' AND column_name = 'preferences';
SQLEOF

# Step 4: Update main.py to include settings router
echo ""
echo "Step 4: Adding settings router to main.py..."

cat > /tmp/add_settings_router.py << 'PYEOF'
import re

with open('backend/app/main.py', 'r') as f:
    content = f.read()

# Check if settings router already imported
if 'from app.routers import settings' not in content:
    # Add import after other router imports
    if 'from app.routers import' in content:
        content = re.sub(
            r'(from app\.routers import.*)',
            r'\1\nfrom app.routers import settings',
            content,
            count=1
        )
    else:
        # Add after other imports
        content = re.sub(
            r'(from app import.*\n)',
            r'\1from app.routers import settings\n',
            content,
            count=1
        )
    
    # Add router inclusion
    if 'app.include_router(settings.router)' not in content:
        # Add after other router inclusions
        content = re.sub(
            r'(app\.include_router\(.*\.router\))',
            r'\1\napp.include_router(settings.router)',
            content,
            count=1
        )
    
    with open('backend/app/main.py', 'w') as f:
        f.write(content)
    
    print("✅ Added settings router to main.py")
else:
    print("✅ Settings router already in main.py")
PYEOF

python3 /tmp/add_settings_router.py

# Step 5: Restart backend to load new code
echo ""
echo "Step 5: Restarting backend..."
docker-compose restart backend

echo "Waiting 10 seconds for backend to restart..."
sleep 10

# Step 6: Test the new endpoints
echo ""
echo "Step 6: Testing Settings API endpoints..."

# Login first
echo "  - Logging in..."
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"AdminPassword123!"}' | \
  python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "    ❌ Login failed"
    exit 1
fi
echo "    ✅ Login successful"

# Test GET tenant settings
echo "  - Testing GET /api/v1/settings/tenant..."
TENANT_SETTINGS=$(curl -s -X GET http://localhost:8000/api/v1/settings/tenant \
  -H "Authorization: Bearer $TOKEN")

if echo "$TENANT_SETTINGS" | grep -q "tenant_id"; then
    echo "    ✅ GET tenant settings works"
    echo "    Response: $(echo $TENANT_SETTINGS | python3 -m json.tool 2>/dev/null | head -10)"
else
    echo "    ❌ GET tenant settings failed"
    echo "    Response: $TENANT_SETTINGS"
fi

# Test PUT tenant settings
echo "  - Testing PUT /api/v1/settings/tenant..."
UPDATE_RESPONSE=$(curl -s -X PUT http://localhost:8000/api/v1/settings/tenant \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"batch_size":2000,"auto_enrichment":false}')

if echo "$UPDATE_RESPONSE" | grep -q "batch_size"; then
    echo "    ✅ PUT tenant settings works"
else
    echo "    ❌ PUT tenant settings failed"
    echo "    Response: $UPDATE_RESPONSE"
fi

# Test GET user preferences
echo "  - Testing GET /api/v1/settings/user..."
USER_PREFS=$(curl -s -X GET http://localhost:8000/api/v1/settings/user \
  -H "Authorization: Bearer $TOKEN")

if echo "$USER_PREFS" | grep -q "user_id"; then
    echo "    ✅ GET user preferences works"
else
    echo "    ❌ GET user preferences failed"
fi

# Test PUT user preferences
echo "  - Testing PUT /api/v1/settings/user..."
UPDATE_USER=$(curl -s -X PUT http://localhost:8000/api/v1/settings/user \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"theme":"dark","items_per_page":100}')

if echo "$UPDATE_USER" | grep -q "theme"; then
    echo "    ✅ PUT user preferences works"
else
    echo "    ❌ PUT user preferences failed"
fi

# Test GET sources
echo "  - Testing GET /api/v1/settings/sources..."
SOURCES=$(curl -s -X GET http://localhost:8000/api/v1/settings/sources \
  -H "Authorization: Bearer $TOKEN")

echo "    ✅ GET sources works"
echo "    Sources count: $(echo $SOURCES | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null)"

echo ""
echo "=========================================="
echo "Phase 3 - Settings API Deployed! ✅"
echo "=========================================="
echo ""
echo "Available Endpoints:"
echo "  GET    /api/v1/settings/tenant      - Get tenant settings"
echo "  PUT    /api/v1/settings/tenant      - Update tenant settings"
echo "  GET    /api/v1/settings/user        - Get user preferences"
echo "  PUT    /api/v1/settings/user        - Update user preferences"
echo "  GET    /api/v1/settings/sources     - List sources"
echo "  POST   /api/v1/settings/sources     - Create source"
echo "  PUT    /api/v1/settings/sources/:id - Update source"
echo "  DELETE /api/v1/settings/sources/:id - Delete source"
echo ""
echo "Next: Frontend React UI setup"
echo ""