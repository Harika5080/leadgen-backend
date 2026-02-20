# Lead Generation Automation Platform

A comprehensive, white-labelable lead generation and management platform designed for multi-tenant SaaS deployment or on-premise installation.

## Features

- Automated 7-stage lead processing pipeline
- Multi-tenant architecture with complete isolation
- White-labeling and branding customization
- Comprehensive settings management interface
- Lead enrichment and email verification
- Human review workflow with priority scoring
- Export to Instantly.ai, Smartlead.ai, and Salesforce
- Complete audit logging and compliance tracking
- Cloud or on-premise deployment support

## Quick Start

### Prerequisites

- Docker 20.0+ and Docker Compose 2.0+
- 8GB RAM minimum (16GB recommended)
- 20GB disk space minimum
- Internet connection for external API services

### Installation

1.docker compose down

# 2. Clean build cache (this fixes it)
docker builder prune -af

# 3. Rebuild without cache
docker compose build --no-cache backend

# 4. Start everything
docker compose up -d
