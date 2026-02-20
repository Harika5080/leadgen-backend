#!/bin/bash
# Auto-generate TypeScript types from FastAPI backend
# Requires: npm install -g openapi-typescript

echo "🔄 Generating TypeScript types from backend..."

# Get OpenAPI schema
curl -s http://localhost:8000/openapi.json > openapi.json

# Generate TypeScript types
npx openapi-typescript openapi.json --output src/types/api-generated.ts

echo "✅ Types generated at: src/types/api-generated.ts"
echo ""
echo "Usage:"
echo "  import type { components } from '@/types/api-generated';"
echo "  type Lead = components['schemas']['Lead'];"