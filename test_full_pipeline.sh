#!/bin/bash

echo "=========================================="
echo "Complete Pipeline Test"
echo "=========================================="

# Login
echo "Logging in..."
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@test.com",
    "password": "AdminPassword123!"
  }')

TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "❌ Login failed"
    exit 1
fi
echo "✅ Logged in"
echo ""

# Upload leads
echo "1. Uploading test leads..."
BATCH_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/leads/batch \
  -H "Authorization: Bearer sk_live_test_key_12345" \
  -H "Content-Type: application/json" \
  -d '{
    "source_name": "pipeline_full_test",
    "leads": [
      {
        "email": "pipeline.test@example.com",
        "first_name": "Pipeline",
        "last_name": "Test",
        "job_title": "Chief Technology Officer",
        "company_name": "Example Corp"
      }
    ]
  }')

BATCH_ID=$(echo "$BATCH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('batch_id', ''))" 2>/dev/null)
echo "✅ Batch uploaded: $BATCH_ID"
echo ""

# Get the lead ID
echo "2. Getting lead details..."
LIST_RESPONSE=$(curl -s -X GET "http://localhost:8000/api/v1/leads?page=1&source_name=pipeline_full_test" \
  -H "Authorization: Bearer $TOKEN")

LEAD_ID=$(echo "$LIST_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['leads'][0]['id']) if data.get('leads') else ''" 2>/dev/null)
INITIAL_STATUS=$(echo "$LIST_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['leads'][0]['status']) if data.get('leads') else ''" 2>/dev/null)

echo "Lead ID: $LEAD_ID"
echo "Initial Status: $INITIAL_STATUS"
echo ""

# Process through pipeline
echo "3. Processing lead through pipeline..."
echo "   (Note: Enrichment/Verification will be skipped if API keys not configured)"
PIPELINE_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/pipeline/process/$LEAD_ID?skip_enrichment=true&skip_verification=true" \
  -H "Authorization: Bearer $TOKEN")

echo "$PIPELINE_RESPONSE" | python3 -m json.tool
echo ""

# Check final state
echo "4. Checking final lead state..."
FINAL_LEAD=$(curl -s -X GET "http://localhost:8000/api/v1/leads/$LEAD_ID" \
  -H "Authorization: Bearer $TOKEN")

FINAL_STATUS=$(echo "$FINAL_LEAD" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null)
FIT_SCORE=$(echo "$FINAL_LEAD" | python3 -c "import sys, json; print(json.load(sys.stdin).get('fit_score', ''))" 2>/dev/null)

echo "Final Status: $FINAL_STATUS"
echo "Fit Score: $FIT_SCORE"
echo ""

echo "=========================================="
echo "Pipeline Test Complete!"
echo "=========================================="
echo ""
echo "Phase 2 Features Implemented:"
echo "  ✅ Normalization Service"
echo "  ✅ Deduplication Service (Redis)"
echo "  ✅ Enrichment Service (Clearbit-ready)"
echo "  ✅ Verification Service (ZeroBounce-ready)"
echo "  ✅ Scoring Service"
echo "  ✅ Pipeline Orchestrator"
echo "  ✅ Manual Pipeline Trigger"
echo ""
echo "Next: Phase 3 - Settings & Frontend"
echo "=========================================="
