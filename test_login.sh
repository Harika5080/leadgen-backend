#!/bin/bash

echo "Testing Login..."
echo "=================="

# Test admin login
echo ""
echo "1. Testing Admin Login..."
ADMIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@test.com",
    "password": "AdminPassword123!"
  }')

echo "$ADMIN_RESPONSE" | python3 -m json.tool

ADMIN_TOKEN=$(echo "$ADMIN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -n "$ADMIN_TOKEN" ]; then
    echo "✅ Admin login successful!"
    echo "Token: ${ADMIN_TOKEN:0:50}..."
else
    echo "❌ Admin login failed!"
    exit 1
fi

# Test reviewer login
echo ""
echo "2. Testing Reviewer Login..."
REVIEWER_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "reviewer@test.com",
    "password": "ReviewerPass123!"
  }')

echo "$REVIEWER_RESPONSE" | python3 -m json.tool

REVIEWER_TOKEN=$(echo "$REVIEWER_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -n "$REVIEWER_TOKEN" ]; then
    echo "✅ Reviewer login successful!"
else
    echo "❌ Reviewer login failed!"
fi

# Test API key authentication
echo ""
echo "3. Testing API Key Authentication..."
API_TEST=$(curl -s -X GET http://localhost:8000/api/v1/leads?page=1 \
  -H "Authorization: Bearer sk_live_test_key_12345")

if [[ "$API_TEST" == *"leads"* ]]; then
    echo "✅ API Key authentication successful!"
else
    echo "❌ API Key authentication failed!"
    echo "Response: $API_TEST"
fi

echo ""
echo "=================="
echo "Login tests complete!"
echo "=================="
