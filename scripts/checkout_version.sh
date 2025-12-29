#!/bin/bash
# =============================================================================
# Checkout a specific git version/commit and rebuild the staging container
# Usage: ./checkout_version.sh <commit-hash-or-tag>
# Example: ./checkout_version.sh 1e7ebe4
# Example: ./checkout_version.sh v1.2.3
# =============================================================================

set -e  # Exit on error

VERSION="${1:-}"
PROJECT_DIR="/opt/zana-bot"
COMPOSE_DIR="${PROJECT_DIR}/zana_planner"

if [ -z "$VERSION" ]; then
    echo "Error: No version/commit specified"
    echo "Usage: $0 <commit-hash-or-tag>"
    echo "Example: $0 1e7ebe4"
    echo "Example: $0 v1.2.3"
    exit 1
fi

echo "========================================"
echo "Checking out version: $VERSION"
echo "========================================"

# Navigate to project directory
cd "$PROJECT_DIR" || {
    echo "Error: Project directory not found: $PROJECT_DIR"
    exit 1
}

# Check if it's a git repository
if [ ! -d .git ]; then
    echo "Error: Not a git repository at $PROJECT_DIR"
    exit 1
fi

# Handle git lock file if it exists
if [ -f .git/index.lock ]; then
    echo "[1/5] Removing stale git lock file..."
    sudo rm -f .git/index.lock 2>/dev/null || rm -f .git/index.lock 2>/dev/null || true
fi

# Fetch latest changes to ensure we have the commit/tag
echo "[2/5] Fetching latest changes from origin..."
git fetch origin --tags --prune || {
    echo "Warning: Failed to fetch from origin, continuing with local repository..."
}

# Check if the version exists
if ! git rev-parse --verify "$VERSION" >/dev/null 2>&1; then
    echo "Error: Version/commit '$VERSION' not found in repository"
    echo "Available tags:"
    git tag -l | head -10
    exit 1
fi

# Get current branch/state info
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")
CURRENT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

echo "Current state: $CURRENT_BRANCH @ $CURRENT_COMMIT"

# Checkout the specified version
echo "[3/5] Checking out $VERSION..."
git checkout "$VERSION" || {
    echo "Error: Failed to checkout $VERSION"
    exit 1
}

# Get commit info for build
COMMIT_SHA=$(git rev-parse --short HEAD)
BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
FULL_COMMIT=$(git rev-parse HEAD)

echo "Checked out: $COMMIT_SHA ($FULL_COMMIT)"
echo "Build date: $BUILD_DATE"

# Navigate to compose directory
cd "$COMPOSE_DIR" || {
    echo "Error: Compose directory not found: $COMPOSE_DIR"
    exit 1
}

# Rebuild the staging container
echo "[4/5] Rebuilding staging container..."
echo "This may take a few minutes..."
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

sudo docker compose build \
    --build-arg GIT_COMMIT="${COMMIT_SHA}" \
    --build-arg BUILD_DATE="${BUILD_DATE}" \
    --progress=plain \
    zana-staging || {
    echo "Error: Failed to build container"
    exit 1
}

# Restart the staging container
echo "[5/5] Restarting staging container..."
sudo docker compose stop zana-staging 2>/dev/null || true
sudo docker compose up -d zana-staging || {
    echo "Error: Failed to start container"
    exit 1
}

# Wait a moment for container to start
sleep 3

# Verify container is running
if sudo docker compose ps zana-staging | grep -q "Up"; then
    echo ""
    echo "========================================"
    echo "✅ Successfully deployed version $VERSION"
    echo "========================================"
    echo "Commit: $COMMIT_SHA"
    echo "Build date: $BUILD_DATE"
    echo ""
    echo "Container status:"
    sudo docker compose ps zana-staging
    echo ""
    echo "View logs: sudo docker compose logs -f zana-staging"
else
    echo ""
    echo "⚠️  Warning: Container may not be running properly"
    echo "Check status: sudo docker compose ps zana-staging"
    echo "Check logs: sudo docker compose logs zana-staging"
    exit 1
fi
