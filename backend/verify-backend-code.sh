#!/bin/bash

echo "🔍 BACKEND CODE VERIFICATION"
echo "============================"
echo ""

# Check 1: Is the new file in place?
echo "1. Checking if leads_routes.py exists..."
if docker compose exec backend test -f /app/app/routers/leads_routes.py; then
  echo "✅ File exists"
else
  echo "❌ File NOT found!"
  exit 1
fi
echo ""

# Check 2: Does it have the debug logging?
echo "2. Checking if file has debug logging..."
if docker compose exec backend grep -q "logger.info.*Leads query" /app/app/routers/leads_routes.py; then
  echo "✅ Debug logging found in file"
else
  echo "❌ Debug logging NOT found - using old version!"
  echo ""
  echo "Fix: Copy the file again:"
  echo "docker compose cp leads_routes-DEBUG.py backend:/app/app/routers/leads_routes.py"
  exit 1
fi
echo ""

# Check 3: Is the router registered in main.py?
echo "3. Checking if leads routes registered in main.py..."
if docker compose exec backend grep -q "leads_routes" /app/app/main.py; then
  echo "✅ leads_routes imported in main.py"
else
  echo "❌ leads_routes NOT imported in main.py!"
  echo ""
  echo "Fix: Add to main.py:"
  echo "  from app.routers import leads_routes"
  echo "  app.include_router(leads_routes.router, prefix='/api/v1', tags=['leads'])"
  exit 1
fi
echo ""

# Check 4: Check recent backend logs
echo "4. Checking recent backend logs..."
echo "Looking for 'Leads query' log entries..."
echo ""

docker compose logs backend --tail=100 | grep "Leads query" || echo "No 'Leads query' logs found - route might not be called"
echo ""

# Check 5: Test the endpoint directly
echo "5. Testing /leads endpoint directly..."
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"AdminPassword123!"}' \
  | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
  echo "❌ Could not get auth token"
  exit 1
fi

echo "Making request with source filter..."
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/leads?source=LinkedIn&limit=5" > /tmp/test_response.json

echo ""
echo "Response received. Checking logs..."
sleep 2

echo ""
echo "Recent backend logs (last 10 lines):"
docker compose logs backend --tail=10

echo ""
echo ""
echo "=================================="
echo "🔍 DIAGNOSIS:"
echo "=================================="

# Check if we got a response
if [ -s /tmp/test_response.json ]; then
  TOTAL=$(jq -r '.pagination.total' /tmp/test_response.json 2>/dev/null || echo "error")
  
  if [ "$TOTAL" = "error" ] || [ "$TOTAL" = "null" ]; then
    echo "❌ Invalid JSON response - backend might have crashed"
    echo ""
    echo "Full response:"
    cat /tmp/test_response.json
  else
    echo "✅ Backend is responding"
    echo "   Total leads returned: $TOTAL"
    
    # Check if debug logging appeared
    if docker compose logs backend --tail=20 | grep -q "Leads query.*source"; then
      echo "✅ Debug logging is working!"
    else
      echo "❌ Debug logging NOT appearing in logs"
      echo "   This means the new code is NOT running"
    fi
  fi
else
  echo "❌ No response from backend"
fi

echo ""
echo "Next step: Check full logs with:"
echo "docker compose logs backend --tail=100"