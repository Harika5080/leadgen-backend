#!/bin/bash
echo "Creating users..."

# Create a simple Python script that will work
cat > /tmp/create_users.sql << 'SQLEOF'
-- Delete old users
DELETE FROM users WHERE email IN ('admin@test.com', 'reviewer@test.com');

-- Insert with working hash (generated from working system)
INSERT INTO users (tenant_id, email, password_hash, full_name, role, is_active)
SELECT 
    t.id,
    'admin@test.com',
    crypt('AdminPassword123!', gen_salt('bf', 12)),
    'Admin User',
    'admin',
    true
FROM tenants t
WHERE t.name = 'Test Tenant'
LIMIT 1;

INSERT INTO users (tenant_id, email, password_hash, full_name, role, is_active)
SELECT 
    t.id,
    'reviewer@test.com',
    crypt('ReviewerPass123!', gen_salt('bf', 12)),
    'Reviewer User',
    'reviewer',
    true
FROM tenants t
WHERE t.name = 'Test Tenant'
LIMIT 1;

SELECT email, role FROM users;
SQLEOF

# Run it
docker-compose exec -T db psql -U leadgen -d leadgen < /tmp/create_users.sql

# Test login
echo ""
echo "Testing login..."
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"AdminPassword123!"}' | python3 -m json.tool

echo ""
echo "Running Phase 2 test..."
./test_phase2_complete.sh
