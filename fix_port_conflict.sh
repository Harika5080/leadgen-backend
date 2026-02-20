#!/bin/bash

# Check what's using port 5432
echo "=== Checking Port 5432 ==="
lsof -i :5432 2>/dev/null || netstat -an | grep 5432

# Check all running PostgreSQL containers
echo ""
echo "=== All PostgreSQL Containers ==="
docker ps -a | grep postgres

# Update docker-compose.yml to use different port
echo ""
echo "=== Updating docker-compose.yml to use port 5433 ==="
cat > docker-compose.yml << 'COMPOSEEND'
services:
  db:
    image: postgres:15
    container_name: leadgen-db
    environment:
      POSTGRES_USER: leadgen
      POSTGRES_PASSWORD: leadgen123
      POSTGRES_DB: leadgen
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backend/init_schema.sql:/docker-entrypoint-initdb.d/init_schema.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U leadgen"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: leadgen-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: leadgen-backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://leadgen:leadgen123@db:5432/leadgen
      - REDIS_URL=redis://redis:6379/0
    env_file:
      - .env
    volumes:
      - ./backend:/app
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

volumes:
  postgres_data:
  redis_data:
COMPOSEEND

echo "✅ docker-compose.yml updated"

# Restart everything
echo ""
echo "=== Restarting all services ==="
docker-compose down
docker-compose up -d

# Wait for services
echo "Waiting for services to start..."
sleep 15

# Check status
echo ""
echo "=== Container Status ==="
docker-compose ps

# Test database
echo ""
echo "=== Testing Database ==="
docker-compose exec db psql -U leadgen -d leadgen -c "SELECT 1;"

# Test backend
echo ""
echo "=== Testing Backend ==="
curl -s http://localhost:8000/health | python3 -m json.tool

echo ""
echo "✅ Setup complete! Database now on port 5433"
