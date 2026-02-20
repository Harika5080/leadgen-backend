#!/bin/bash

echo "🔍 COMPREHENSIVE FILTER DEBUGGING"
echo "=================================="
echo ""

# Get token
echo "Step 1: Getting auth token..."
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"AdminPassword123!"}' \
  | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
  echo "❌ Failed to get token"
  exit 1
fi
echo "✅ Token obtained"
echo ""

# Step 2: Get all leads to see total
echo "Step 2: Getting all leads (no filter)..."
ALL_RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/leads?limit=100")

TOTAL=$(echo "$ALL_RESPONSE" | jq -r '.pagination.total')
echo "✅ Total leads in database: $TOTAL"
echo ""

# Step 3: Check what sources exist in the data
echo "Step 3: Checking actual source values in database..."
SOURCES=$(echo "$ALL_RESPONSE" | jq -r '.leads[].source_name' | sort | uniq -c | sort -rn)
echo "Source distribution:"
echo "$SOURCES"
echo ""

FIRST_SOURCE=$(echo "$ALL_RESPONSE" | jq -r '.leads[0].source_name')
echo "First lead's source: '$FIRST_SOURCE'"
echo ""

# Step 4: Test filter with exact value from data
echo "Step 4: Testing filter with source='$FIRST_SOURCE'"
ENCODED_SOURCE=$(echo "$FIRST_SOURCE" | sed 's/ /%20/g')
FILTERED_RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/leads?source=$ENCODED_SOURCE&limit=100")

FILTERED_TOTAL=$(echo "$FILTERED_RESPONSE" | jq -r '.pagination.total')
FILTERS_APPLIED=$(echo "$FILTERED_RESPONSE" | jq -r '.filters_applied.source')

echo "Filtered total: $FILTERED_TOTAL"
echo "Filter applied (from response): '$FILTERS_APPLIED'"
echo ""

# Step 5: Check first few leads from filtered response
echo "Step 5: Checking if filtered leads actually match..."
FIRST_5_SOURCES=$(echo "$FILTERED_RESPONSE" | jq -r '.leads[0:5][] | .source_name')
echo "Sources of first 5 filtered leads:"
echo "$FIRST_5_SOURCES"
echo ""

# Step 6: Check email_verified filter
echo "Step 6: Testing email_verified filter..."
VERIFIED_RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/leads?email_verified=true&limit=100")

VERIFIED_TOTAL=$(echo "$VERIFIED_RESPONSE" | jq -r '.pagination.total')
echo "Email verified=true: $VERIFIED_TOTAL leads"

FIRST_3_VERIFIED=$(echo "$VERIFIED_RESPONSE" | jq -r '.leads[0:3][] | .email_verified')
echo "First 3 leads email_verified values:"
echo "$FIRST_3_VERIFIED"
echo ""

# Step 7: Check status filter
echo "Step 7: Testing status filter..."
STATUS_RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/leads?status=pending_review&limit=100")

STATUS_TOTAL=$(echo "$STATUS_RESPONSE" | jq -r '.pagination.total')
echo "Status=pending_review: $STATUS_TOTAL leads"

FIRST_3_STATUSES=$(echo "$STATUS_RESPONSE" | jq -r '.leads[0:3][] | .status')
echo "First 3 leads status values:"
echo "$FIRST_3_STATUSES"
echo ""

# Step 8: Show raw API response for debugging
echo "Step 8: Raw filtered response (first lead only)..."
echo "$FILTERED_RESPONSE" | jq '.leads[0] | {email, source_name, status, email_verified}'
echo ""

# Step 9: Diagnosis
echo "=================================="
echo "🔍 DIAGNOSIS:"
echo "=================================="
echo ""

if [ "$FILTERED_TOTAL" -eq "$TOTAL" ]; then
  echo "❌ PROBLEM CONFIRMED: Source filter NOT working"
  echo "   Expected: $FILTERED_TOTAL < $TOTAL"
  echo "   Got: $FILTERED_TOTAL = $TOTAL"
  echo ""
  echo "   Possible causes:"
  echo "   1. Filter parameter not reaching backend"
  echo "   2. SQLAlchemy query not applying filter"
  echo "   3. Database column mismatch"
  echo ""
  echo "   Next steps:"
  echo "   - Check backend logs: docker compose logs backend --tail=20"
  echo "   - Verify routes registered in main.py"
  echo "   - Check if new code is actually running"
else
  echo "✅ Source filter IS working!"
  echo "   Total: $TOTAL"
  echo "   Filtered: $FILTERED_TOTAL"
  echo ""
  
  # But check if it's filtering correctly
  WRONG_SOURCE=$(echo "$FIRST_5_SOURCES" | grep -v "^$FIRST_SOURCE$" || echo "")
  if [ -n "$WRONG_SOURCE" ]; then
    echo "⚠️  WARNING: Filtered results contain wrong sources!"
    echo "   Expected all to be: '$FIRST_SOURCE'"
    echo "   But found: '$WRONG_SOURCE'"
  else
    echo "✅ Filtered results look correct!"
  fi
fi

echo ""
echo "=================================="
echo "📋 SUMMARY:"
echo "=================================="
echo "Total leads: $TOTAL"
echo "Source filter result: $FILTERED_TOTAL"
echo "Email verified filter: $VERIFIED_TOTAL"
echo "Status filter: $STATUS_TOTAL"
echo ""
echo "Run this to see backend logs:"
echo "docker compose logs backend --tail=50 | grep -E '(Leads query|Adding.*filter|Total leads)'"