#!/usr/bin/env bash
# deploy.sh - One-Click Deployment Shell Script for Ubuntu/Debian Cloud Servers (T-314)

set -euo pipefail

BOLD='\033[1;32m'
NC='\033[0m'

echo -e "${BOLD}═════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}     SWING TRADING SYSTEM - ONE-CLICK CLOUD DEPLOYMENT SCRIPT        ${NC}"
echo -e "${BOLD}═════════════════════════════════════════════════════════════════════${NC}"

# Check Docker Installation
if ! command -v docker &> /dev/null; then
    echo "🐳 Docker not found. Installing Docker Engine..."
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

# Check Docker Compose
DOCKER_COMPOSE_CMD=""
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    echo "❌ docker-compose not found. Installing..."
    sudo apt-get install -y docker-compose
    DOCKER_COMPOSE_CMD="docker-compose"
fi

# Create required directories
echo "📁 Setting up data & SSL directories..."
mkdir -p data logs reports ssl

# Generate Self-Signed SSL Certificates if missing (for Nginx HTTPS)
if [ ! -f ssl/server.crt ] || [ ! -f ssl/server.key ]; then
    echo "🔒 Generating SSL certificates for HTTPS termination..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout ssl/server.key -out ssl/server.crt \
      -subj "/C=IN/ST=Karnataka/L=Bengaluru/O=SwingTrading/CN=localhost" 2>/dev/null || true
fi

# Create default .env if missing
if [ ! -f .env ]; then
    echo "⚙️ Creating default .env environment configuration..."
    cat <<'EOF' > .env
PORT=8000
REDIS_URL=redis://redis:6379/0
DATABASE_PATH=/app/data/system.db
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_2FA_PIN=1234
WHATSAPP_VERIFY_TOKEN=swing_trading_secret_token
EOF
fi

# Build and Launch Containers
echo "🚀 Building and starting Docker containers..."
$DOCKER_COMPOSE_CMD down --remove-orphans || true
$DOCKER_COMPOSE_CMD up -d --build

# Health Verification Loop
echo "⏳ Waiting for Web Server container to initialize..."
MAX_ATTEMPTS=20
ATTEMPT=0
HEALTHY=false

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    if curl -s http://localhost:8000/health | grep -q '"status"'; then
        HEALTHY=true
        break
    fi
    sleep 2
done

echo ""
if [ "$HEALTHY" = true ]; then
    echo -e "${BOLD}✅ DEPLOYMENT SUCCESSFUL!${NC}"
    echo "─────────────────────────────────────────────────────────────────"
    echo "• FastAPI Server:      http://localhost:8000"
    echo "• Nginx HTTPS Proxy:   https://localhost:443"
    echo "• Health Endpoint:     http://localhost:8000/health"
    echo "• Telemetry Metrics:   http://localhost:8000/metrics"
    echo "─────────────────────────────────────────────────────────────────"
    echo "Container Status:"
    $DOCKER_COMPOSE_CMD ps
else
    echo "⚠️ System started but health check pending. View container logs:"
    $DOCKER_COMPOSE_CMD logs --tail=20
fi
