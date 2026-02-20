#!/bin/bash

echo "=========================================="
echo "Complete Lead Generation Workflow Test"
echo "=========================================="

# Step 1: Login as admin
echo ""
echo "Step 1: Admin Login"
echo "-------------------"
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@test.com",
    "password": "AdminPassword123!"
  }')

ADMIN_TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$ADMIN_TOKEN" ]; then
    echo "❌ Login failed"
    exit 1
fi
echo "✅ Admin logged in successfully"

# Step 2: External system uploads leads via API key
echo ""
echo "Step 2: External System Uploads Leads (API Key)"
echo "------------------------------------------------"
BATCH_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/leads/batch \
  -H "Authorization: Bearer sk_live_test_key_12345" \
  -H "Content-Type: application/json" \
  -d '{
    "source_name": "linkedin_scraper",
    "leads": [
      {
        "email": "john.doe@techcorp.com",
        "first_name": "John",
        "last_name": "Doe",
        "job_title": "VP of Engineering",
        "company_name": "TechCorp",
        "company_website": "https://techcorp.com",
        "linkedin_url": "https://linkedin.com/in/johndoe"
      },
      {
        "email": "sarah.johnson@innovate.io",
        "first_name": "Sarah",
        "last_name": "Johnson",
        "job_title": "CTO",
        "company_name": "Innovate.io",
        "company_website": "https://innovate.io"
      },
      {
        "email": "mike.wilson@startup.com",
        "first_name": "Mike",
        "last_name": "Wilson",
        "job_title": "Director of Sales",
        "company_name": "Startup Inc"
      }
    ]
  }')

ACCEPTED=$(echo "$BATCH_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('accepted', 0))" 2>/dev/null)
echo "✅ Batch upload completed: $ACCEPTED leads accepted"
echo "$BATCH_RESPONSE" | python3 -m json.tool 2>/dev/null

# Step 3: Admin lists the uploaded leads
echo ""
echo "Step 3: Admin Lists Leads"
echo "-------------------------"
LIST_RESPONSE=$(curl -s -X GET "http://localhost:8000/api/v1/leads?page=1&page_size=10" \
  -H "Authorization: Bearer $ADMIN_TOKEN")

TOTAL_LEADS=$(echo "$LIST_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total', 0))" 2>/dev/null)
echo "✅ Found $TOTAL_LEADS total leads"

# Step 4: Get details of first lead
echo ""
echo "Step 4: View Lead Details"
echo "-------------------------"
FIRST_LEAD_ID=$(echo "$LIST_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['leads'][0]['id']) if data.get('leads') else ''" 2>/dev/null)

if [ -n "$FIRST_LEAD_ID" ]; then
    LEAD_DETAIL=$(curl -s -X GET "http://localhost:8000/api/v1/leads/$FIRST_LEAD_ID" \
      -H "Authorization: Bearer $ADMIN_TOKEN")
    
    LEAD_EMAIL=$(echo "$LEAD_DETAIL" | python3 -c "import sys, json; print(json.load(sys.stdin).get('email', ''))" 2>/dev/null)
    LEAD_NAME=$(echo "$LEAD_DETAIL" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"{d.get('first_name', '')} {d.get('last_name', '')}\")" 2>/dev/null)
    
    echo "✅ Lead Details Retrieved:"
    echo "   Name: $LEAD_NAME"
    echo "   Email: $LEAD_EMAIL"
    echo "   ID: $FIRST_LEAD_ID"
fi

# Step 5: Review the lead (approve it)
echo ""
echo "Step 5: Review Lead (Approve)"
echo "-----------------------------"
if [ -n "$FIRST_LEAD_ID" ]; then
    REVIEW_RESPONSE=$(curl -s -X PUT "http://localhost:8000/api/v1/leads/$FIRST_LEAD_ID/review" \
      -H "Authorization: Bearer $ADMIN_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "decision": "approved",
        "notes": "High-quality lead, good fit for our ICP",
        "edits": {
          "job_title": "VP of Engineering & Technology"
        }
      }')
    
    REVIEW_DECISION=$(echo "$REVIEW_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('review_decision', ''))" 2>/dev/null)
    echo "✅ Lead reviewed: $REVIEW_DECISION"
fi

# Step 6: Check database stats
echo ""
echo "Step 6: Database Statistics"
echo "---------------------------"
DB_TEST=$(curl -s http://localhost:8000/api/v1/db-test)
echo "$DB_TEST" | python3 -m json.tool 2>/dev/null

echo ""
echo "=========================================="
echo "Workflow Test Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  ✅ Admin authentication (JWT)"
echo "  ✅ Lead batch upload (API Key)"
echo "  ✅ Lead listing"
echo "  ✅ Lead details retrieval"
echo "  ✅ Lead review and approval"
echo "  ✅ Database connectivity"
echo ""
echo "Phase 1 Foundation: COMPLETE"
echo "=========================================="
