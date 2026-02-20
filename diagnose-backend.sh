#!/bin/bash

echo "🔍 Testing Backend Login Endpoint..."
echo ""

# Test with correct format
echo "Test 1: Correct JSON format"
echo "POST http://localhost:8000/api/v1/auth/login"
echo 'Body: {"email":"admin@test.com","password":"AdminPassword123!"}'
echo ""

RESPONSE=$(curl -w "\nHTTP_CODE:%{http_code}" -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"AdminPassword123!"}' 2>&1)

HTTP_CODE=$(echo "$RESPONSE" | grep HTTP_CODE | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE/d')

echo "Response Code: $HTTP_CODE"
echo "Response Body: $BODY"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Backend login works!"
  echo ""
  echo "This means the problem is in the FRONTEND sending wrong data."
  echo "Run the browser diagnostic script to see what's actually being sent."
elif [ "$HTTP_CODE" = "422" ]; then
  echo "❌ Backend also returns 422!"
  echo ""
  echo "This means either:"
  echo "1. Password in database is wrong"
  echo "2. Email doesn't exist in database"  
  echo "3. Backend validation is too strict"
  echo ""
  echo "Let's check if user exists..."
  docker compose exec backend python -c "
import asyncio
from app.database import get_db_sync
from app.models import User
from sqlalchemy import select

def check_user():
    db = get_db_sync()
    result = db.execute(select(User).where(User.email == 'admin@test.com'))
    user = result.scalar_one_or_none()
    if user:
        print(f'✅ User exists: {user.email}')
        print(f'   Is active: {user.is_active}')
        print(f'   Role: {user.role}')
    else:
        print('❌ User does NOT exist in database!')
        print('   You need to create the user first.')

check_user()
"
elif [ "$HTTP_CODE" = "401" ]; then
  echo "❌ Backend returns 401 (Unauthorized)"
  echo "This means user exists but password is WRONG in database."
  echo "The password should be: AdminPassword123!"
else
  echo "❌ Unexpected response code: $HTTP_CODE"
  echo "Backend might not be running or there's another issue."
fi