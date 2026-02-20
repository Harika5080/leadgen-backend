#!/bin/bash

# Phase 3 - Clean Container Rebuild Script
set -e

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║       Phase 3 - Clean Container Rebuild & Deploy         ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Verify files
echo "📋 Step 1: Verifying all files exist..."
FILES=(
    "backend/requirements.txt"
    "backend/app/main.py"
    "backend/app/websocket.py"
    "backend/app/schemas/settings.py"
    "backend/app/routers/settings.py"
    "backend/app/routers/export.py"
    "backend/app/services/export_service.py"
    "backend/migrations/003_tenant_settings_user_preferences.sql"
)

MISSING=0
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "   ✅ $file"
    else
        echo "   ❌ MISSING: $file"
        MISSING=1
    fi
done

if [ $MISSING -eq 1 ]; then
    echo ""
    echo "❌ Some files are missing. Please ensure all files are in place."
    exit 1
fi

echo ""
echo "✅ All files present!"
echo ""

# Step 2: Stop containers
echo "🛑 Step 2: Stopping containers..."
docker-compose down
echo "✅ Containers stopped"
echo ""

# Step 3: Rebuild backend
echo "🔨 Step 3: Rebuilding backend container..."
docker-compose build backend

if [ $? -eq 0 ]; then
    echo "✅ Backend rebuilt successfully"
else
    echo "❌ Backend build failed"
    exit 1
fi
echo ""

# Step 4: Start containers
echo "🚀 Step 4: Starting containers..."
docker-compose up -d

if [ $? -eq 0 ]; then
    echo "✅ Containers started"
else
    echo "❌ Failed to start containers"
    exit 1
fi
echo ""

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready (15 seconds)..."
sleep 15
echo ""



# Step 7: Test deployment
echo "🧪 Step 7: Testing deployment..."
HEALTH=$(curl -s http://localhost:8000/health)

if echo "$HEALTH" | grep -q "healthy"; then
    echo "✅ Backend is healthy!"
    echo ""
    echo "$HEALTH" | python3 -m json.tool
else
    echo "❌ Health check failed"
    echo "Response: $HEALTH"
    echo ""
    echo "Check logs with: docker-compose logs backend"
    exit 1
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              🎉 Deployment Complete! 🎉                   ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "✅ Phase 3 features deployed:"
echo "   • Settings Management API"
echo "   • WebSocket Notifications"
echo "   • Export Services (Instantly/Smartlead)"
echo ""
echo "📚 Next steps:"
echo "   • API Docs: http://localhost:8000/docs"
echo "   • Health: http://localhost:8000/health"
echo "   • Test Settings: curl with JWT token"
echo ""
echo "🐛 Troubleshooting:"
echo "   • View logs: docker-compose logs -f backend"
echo "   • Check status: curl http://localhost:8000/api/v1/status"
echo ""