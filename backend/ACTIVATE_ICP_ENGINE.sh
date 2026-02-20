#!/bin/bash

echo "🔄 ICP ENGINE ACTIVATION"
echo "========================"
echo ""

echo "Step 1: Restarting backend..."
docker-compose restart backend

echo ""
echo "Step 2: Waiting for backend to be ready..."
sleep 5

echo ""
echo "Step 3: Checking health..."
curl -s http://localhost:8000/health | python3 -m json.tool

echo ""
echo ""
echo "Step 4: Testing API Templates endpoint..."
curl -s http://localhost:8000/api/v1/api-templates | python3 -m json.tool | head -30

echo ""
echo ""
echo "Step 5: Checking scheduler status..."
docker-compose logs backend 2>&1 | grep -i "scheduler\|apscheduler\|job" | tail -10

echo ""
echo ""
echo "✅ ACTIVATION COMPLETE!"
echo ""
echo "Next steps:"
echo "  1. Open API docs: http://localhost:8000/docs"
echo "  2. Check for 4 new sections: ICPs, Data Sources, Ingestion, API Templates"
echo "  3. View templates: curl http://localhost:8000/api/v1/api-templates"
echo ""