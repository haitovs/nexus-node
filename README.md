# NexusNode — VPN Proxy Node

Companion node service for NexusPanel. Runs Xray core on your server.

## Quick Start

```bash
docker compose up -d
```

## Configuration

All settings via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| SERVICE_PORT | 62050 | Panel connection port |
| XRAY_API_PORT | 62051 | Xray gRPC API port |
| SERVICE_PROTOCOL | rest | Protocol (rest or rpyc) |
| SSL_CLIENT_CERT_FILE | /var/lib/nexus-node/cert.pem | Panel certificate |

## Add to Panel

1. Run this node on your VPS
2. In panel dashboard → Nodes → Add New Node
3. Enter node IP, port 62050, API port 62051
4. Copy panel certificate to `/var/lib/nexus-node/cert.pem`

## Manual Install (without Docker)

```bash
pip install -r requirements.txt
python main.py
```
