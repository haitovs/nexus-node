#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}
╔══════════════════════════════════════╗
║       NexusNode Installer            ║
╚══════════════════════════════════════╝
${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root${NC}"
  exit 1
fi

# Install Docker if needed
if ! command -v docker &> /dev/null; then
  echo -e "${YELLOW}Installing Docker...${NC}"
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker && systemctl start docker
fi

if ! command -v docker compose &> /dev/null; then
  apt-get update -qq && apt-get install -y -qq docker-compose-plugin > /dev/null 2>&1
fi

echo -e "${GREEN}Docker OK${NC}"

# Setup
INSTALL_DIR="/opt/nexus-node"
DATA_DIR="/var/lib/nexus-node"
mkdir -p "$INSTALL_DIR" "$DATA_DIR"

# Get panel certificate
echo ""
echo -e "${YELLOW}You need the panel's SSL certificate to connect this node.${NC}"
echo -e "Get it from your panel server: ${BLUE}cat /var/lib/marzban/ssl_cert.pem${NC}"
echo ""
echo "Paste the certificate content (then press Ctrl+D on a new line):"
cat > "$DATA_DIR/cert.pem"

if [ ! -s "$DATA_DIR/cert.pem" ]; then
  echo -e "${RED}No certificate provided. You can add it later to $DATA_DIR/cert.pem${NC}"
fi

# Docker compose
cat > "$INSTALL_DIR/docker-compose.yml" << 'YAML'
services:
  nexus-node:
    container_name: nexus-node
    image: ghcr.io/haitovs/nexus-node:latest
    restart: always
    network_mode: host
    environment:
      SSL_CLIENT_CERT_FILE: "/var/lib/nexus-node/cert.pem"
      SERVICE_PORT: "62050"
      XRAY_API_PORT: "62051"
      SERVICE_PROTOCOL: "rest"
    volumes:
      - /var/lib/nexus-node:/var/lib/nexus-node
YAML

# Try pulling from registry, fall back to building
cd "$INSTALL_DIR"
echo -e "${YELLOW}Starting node...${NC}"
docker compose pull 2>/dev/null || {
  echo -e "${YELLOW}Registry unavailable, building locally...${NC}"
  # Clone and build
  apt-get install -y -qq git > /dev/null 2>&1
  git clone https://github.com/haitovs/nexus-node.git /tmp/nexus-build 2>/dev/null
  cp /tmp/nexus-build/Dockerfile "$INSTALL_DIR/"
  cp /tmp/nexus-build/*.py "$INSTALL_DIR/"
  cp /tmp/nexus-build/requirements.txt "$INSTALL_DIR/"
  rm -rf /tmp/nexus-build
  sed -i 's|image:.*|build: .|' "$INSTALL_DIR/docker-compose.yml"
}

docker compose up -d

NODE_IP=$(curl -s4 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     NexusNode Installed               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "  Node IP:    ${BLUE}${NODE_IP}${NC}"
echo -e "  Port:       ${BLUE}62050${NC}"
echo -e "  API Port:   ${BLUE}62051${NC}"
echo ""
echo -e "  ${YELLOW}Add this node in your panel:${NC}"
echo -e "  Dashboard → Nodes → Add New Node"
echo -e "  Address: ${BLUE}${NODE_IP}${NC}"
echo -e "  Port: ${BLUE}62050${NC}"
echo -e "  API Port: ${BLUE}62051${NC}"
echo ""
echo -e "  Config:     ${INSTALL_DIR}/docker-compose.yml"
echo -e "  Data:       ${DATA_DIR}/"
echo -e "  Cert:       ${DATA_DIR}/cert.pem"
echo ""
