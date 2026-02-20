#!/bin/bash

echo "=========================================="
echo "Infrastructure Verification"
echo "=========================================="
echo ""

# Check PostgreSQL
echo "1. PostgreSQL Status:"
docker-compose ps postgres
echo ""

# Check Redis
echo "2. Redis Status:"
docker-compose ps redis
echo ""

# Test PostgreSQL connectivity
echo "3. PostgreSQL Connectivity:"
docker exec leadgen-postgres psql -U leadgen_user -d leadgen -c "SELECT 'Connected!' as status;"
echo ""

# Count tables
echo "4. Database Tables:"
docker exec leadgen-postgres psql -U leadgen_user -d leadgen -c "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = 'public';"
docker exec leadgen-postgres psql -U leadgen_user -d leadgen -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
echo ""

# Test Redis
echo "5. Redis Connectivity:"
docker exec leadgen-redis redis-cli PING
echo ""

# Check test data
echo "6. Test Tenant:"
docker exec leadgen-postgres psql -U leadgen_user -d leadgen -c "SELECT name, status FROM tenants LIMIT 1;"
echo ""

echo "7. Test Users:"
docker exec leadgen-postgres psql -U leadgen_user -d leadgen -c "SELECT email, role FROM users;"
echo ""

echo "=========================================="
echo "Verification Complete!"
echo "=========================================="
echo ""
echo "Test Credentials:"
echo "  API Key: sk_live_test_key_12345"
echo "  Admin Email: admin@test.com"
echo "  Admin Password: AdminPassword123!"
echo "  Reviewer Email: reviewer@test.com"
echo "  Reviewer Password: ReviewerPass123!"
echo "=========================================="
