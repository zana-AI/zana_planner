#!/bin/bash
# Deployment script for Zana AI bot
# Usage: ./deploy.sh <version> [staging|prod|both]

set -e  # Exit on error

VERSION=$1
TARGET=${2:-both}

if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version> [staging|prod|both]"
    echo "Example: $0 v0.4.2 staging"
    exit 1
fi

# Validate version format (basic check)
if [[ ! $VERSION =~ ^v?[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: Version must be in format v0.4.2 or 0.4.2"
    exit 1
fi

# Normalize version (remove 'v' prefix if present)
VERSION_NUM=${VERSION#v}
IMAGE_TAG="zana-ai-bot:${VERSION_NUM}"
IMAGE_LATEST="zana-ai-bot:latest"

echo "=========================================="
echo "Zana AI Deployment Script"
echo "=========================================="
echo "Version: $VERSION_NUM"
echo "Target: $TARGET"
echo "Image: $IMAGE_TAG"
echo "=========================================="
echo ""

# Build Docker image
echo "Step 1: Building Docker image..."
docker build -t "$IMAGE_TAG" .
if [ $? -ne 0 ]; then
    echo "Error: Docker build failed"
    exit 1
fi
echo "✓ Build successful"
echo ""

# Tag as latest
echo "Step 2: Tagging as latest..."
docker tag "$IMAGE_TAG" "$IMAGE_LATEST"
echo "✓ Tagged $IMAGE_TAG as $IMAGE_LATEST"
echo ""

# Deploy to staging
if [ "$TARGET" = "staging" ] || [ "$TARGET" = "both" ]; then
    echo "Step 3: Deploying to staging..."
    docker compose up -d zana-staging
    if [ $? -ne 0 ]; then
        echo "Error: Staging deployment failed"
        exit 1
    fi
    echo "✓ Staging deployment successful"
    echo ""
    
    # Show logs
    echo "Staging container status:"
    docker compose ps zana-staging
    echo ""
fi

# Deploy to production
if [ "$TARGET" = "prod" ] || [ "$TARGET" = "both" ]; then
    if [ "$TARGET" = "both" ]; then
        echo "Step 4: Deploying to production..."
    else
        echo "Step 3: Deploying to production..."
    fi
    
    # Safety check for production
    if [ "$TARGET" = "prod" ] || [ "$TARGET" = "both" ]; then
        read -p "Deploy to PRODUCTION? (yes/no): " confirm
        if [ "$confirm" != "yes" ]; then
            echo "Deployment cancelled"
            exit 0
        fi
    fi
    
    docker compose up -d zana-prod
    if [ $? -ne 0 ]; then
        echo "Error: Production deployment failed"
        exit 1
    fi
    echo "✓ Production deployment successful"
    echo ""
    
    # Show logs
    echo "Production container status:"
    docker compose ps zana-prod
    echo ""
fi

# Deploy stats service (always)
echo "Deploying stats service..."
docker compose up -d zana-stats
if [ $? -ne 0 ]; then
    echo "Warning: Stats service deployment failed (non-critical)"
else
    echo "✓ Stats service deployment successful"
fi
echo ""

echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Useful commands:"
echo "  View logs:        docker compose logs -f [service-name]"
echo "  Check status:     docker compose ps"
echo "  Rollback:         docker tag zana-ai-bot:<old-version> zana-ai-bot:latest && docker compose up -d [service]"
echo ""