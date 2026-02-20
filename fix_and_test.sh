#!/bin/bash

# Check container status
echo "Checking container status..."
docker-compose ps

# Start all services
echo ""
echo "Starting all services..."
docker-compose up -d

# Wait for database to be ready
echo "Waiting for database to start..."
sleep 10

# Check if they're running
echo ""
docker-compose ps

# Verify database is accessible
echo ""
echo "Testing database connection..."
docker-compose exec -T db psql -U leadgen -d leadgen -c "SELECT 1;" || {
    echo "Database not ready, waiting more..."
    sleep 10
}

# Create test users via SQL
echo ""
echo "Creating test users..."
docker-compose exec -T db psql -U leadgen -d leadgen << 'SQLEND'
DO $$
DECLARE
    v_tenant_id UUID;
BEGIN
    SELECT id INTO v_tenant_id FROM tenants WHERE name = 'Test Tenant' LIMIT 1;
    
    IF v_tenant_id IS NULL THEN
        INSERT INTO tenants (name, api_key_hash, status)
        VALUES (
            'Test Tenant',
            '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GQFHvVJUmJdK',
            'active'
        )
        RETURNING id INTO v_tenant_id;
    END IF;
    
    DELETE FROM users WHERE email IN ('admin@test.com', 'reviewer@test.com');
    
    INSERT INTO users (tenant_id, email, password_hash, full_name, role, is_active)
    VALUES (
        v_tenant_id,
        'admin@test.com',
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GQFHvVJUmJdK',
        'Admin User',
        'admin',
        true
    );
    
    INSERT INTO users (tenant_id, email, password_hash, full_name, role, is_active)
    VALUES (
        v_tenant_id,
        'reviewer@test.com',
        '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn3.FdYUfLJmDLPa4gXPz7Jb0TfC',
        'Reviewer User',
        'reviewer',
        true
    );
    
    RAISE NOTICE 'Users created successfully';
END $$;

SELECT u.email, u.role, u.is_active, t.name as tenant_name
FROM users u
JOIN tenants t ON u.tenant_id = t.id;
SQLEND

# Wait for backend
echo ""
echo "Waiting for backend to be ready..."
sleep 5

# Test login
echo ""
echo "Testing login..."
LOGIN_RESULT=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@test.com", "password": "AdminPassword123!"}')

echo "$LOGIN_RESULT" | python3 -m json.tool

TOKEN=$(echo "$LOGIN_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -n "$TOKEN" ]; then
    echo ""
    echo "✅ Login successful!"
    echo ""
    echo "Running Phase 2 Complete Test..."
    ./test_phase2_complete.sh
else
    echo ""
    echo "❌ Login failed. Checking logs..."
    docker-compose logs --tail=20 backend
fi
