#!/bin/bash

echo "=== Checking Users in Database ==="
docker-compose exec db psql -U leadgen -d leadgen -c "SELECT email, role, is_active FROM users;"

echo ""
echo "=== Checking Tenants ==="
docker-compose exec db psql -U leadgen -d leadgen -c "SELECT id, name, status FROM tenants;"

echo ""
echo "=== Testing Login ==="
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@test.com", "password": "AdminPassword123!"}' | python3 -m json.tool

echo ""
echo "=== Checking Backend Logs ==="
docker-compose logs backend | grep -i "login\|auth" | tail -10
