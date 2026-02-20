#!/bin/bash

echo "🧪 ICP ENGINE - COMPREHENSIVE TESTS"
echo "===================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

test_endpoint() {
    local name=$1
    local endpoint=$2
    local expected=$3
    
    echo -n "Testing $name... "
    
    response=$(curl -s "$endpoint" 2>/dev/null)
    
    if echo "$response" | grep -q "$expected"; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC}"
        echo "  Expected: $expected"
        echo "  Got: $response" | head -c 100
        ((FAILED++))
        return 1
    fi
}

echo "1. HEALTH CHECK"
echo "---------------"
test_endpoint "Health endpoint" "http://localhost:8000/health" "healthy"
echo ""

echo "2. API TEMPLATES (Public - No Auth)"
echo "------------------------------------"
test_endpoint "List templates" "http://localhost:8000/api/v1/api-templates/" "apollo"
test_endpoint "Get providers" "http://localhost:8000/api/v1/api-templates/providers" "apollo"
test_endpoint "Get categories" "http://localhost:8000/api/v1/api-templates/categories" "b2b_data"
echo ""

echo "3. AUTHENTICATION"
echo "-----------------"
echo -n "Getting JWT token... "
TOKEN=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"AdminPassword123!"}' \
  | grep -o '"access_token":"[^"]*"' \
  | cut -d'"' -f4)

if [ -n "$TOKEN" ]; then
    echo -e "${GREEN}✓ PASS${NC}"
    echo "  Token: ${TOKEN:0:20}..."
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}"
    ((FAILED++))
fi
echo ""

echo "4. ICP ENDPOINTS (Authenticated)"
echo "---------------------------------"
if [ -n "$TOKEN" ]; then
    # Test ICP list
    echo -n "List ICPs... "
    response=$(curl -s "http://localhost:8000/api/v1/icps/" \
      -H "Authorization: Bearer $TOKEN")
    
    if [ -n "$response" ]; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAILED++))
    fi
    
    # Create test ICP
    echo -n "Create test ICP... "
    ICP_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/icps/" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "Test Tech Companies",
        "description": "B2B SaaS companies for testing",
        "qualification_threshold": 0.7,
        "auto_qualify_threshold": 0.9
      }')
    
    ICP_ID=$(echo "$ICP_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    
    if [ -n "$ICP_ID" ]; then
        echo -e "${GREEN}✓ PASS${NC}"
        echo "  ICP ID: $ICP_ID"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAILED++))
    fi
else
    echo "Skipping (no auth token)"
fi
echo ""

echo "5. DATA SOURCE ENDPOINTS"
echo "------------------------"
if [ -n "$TOKEN" ]; then
    echo -n "List data sources... "
    response=$(curl -s "http://localhost:8000/api/v1/data-sources/" \
      -H "Authorization: Bearer $TOKEN")
    
    if [ -n "$response" ]; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAILED++))
    fi
else
    echo "Skipping (no auth token)"
fi
echo ""

echo "6. INGESTION ENDPOINTS"
echo "----------------------"
if [ -n "$TOKEN" ]; then
    echo -n "List ingestion jobs... "
    response=$(curl -s "http://localhost:8000/api/v1/ingestion/jobs" \
      -H "Authorization: Bearer $TOKEN")
    
    if [ -n "$response" ]; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAILED++))
    fi
    
    echo -n "Get ingestion stats... "
    response=$(curl -s "http://localhost:8000/api/v1/ingestion/stats" \
      -H "Authorization: Bearer $TOKEN")
    
    if [ -n "$response" ]; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAILED++))
    fi
else
    echo "Skipping (no auth token)"
fi
echo ""

echo "7. API DOCUMENTATION"
echo "--------------------"
echo -n "Swagger UI... "
response=$(curl -s "http://localhost:8000/docs" 2>/dev/null)

if echo "$response" | grep -q "swagger"; then
    echo -e "${GREEN}✓ PASS${NC}"
    echo "  URL: http://localhost:8000/docs"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}"
    ((FAILED++))
fi
echo ""

echo "=================================="
echo "RESULTS"
echo "=================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Open API docs: http://localhost:8000/docs"
    echo "  2. Browse API templates"
    echo "  3. Create your first ICP"
    echo "  4. Clone a template"
    echo "  5. Trigger ingestion"
else
    echo -e "${YELLOW}⚠️  Some tests failed. Check the output above.${NC}"
fi
echo ""

# Cleanup test ICP if created
if [ -n "$ICP_ID" ] && [ -n "$TOKEN" ]; then
    echo "Cleaning up test ICP..."
    curl -s -X DELETE "http://localhost:8000/api/v1/icps/$ICP_ID" \
      -H "Authorization: Bearer $TOKEN" > /dev/null
    echo "✓ Cleaned up"
fi