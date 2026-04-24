"""Hysteria2 subprocess manager.

Parallels `XRayCore` but for the apernet/hysteria daemon. Spawns and
watches a single hysteria subprocess bound to a panel-supplied config.
Config push comes from the panel's ``app/xray/hy2_sync`` module via
``POST /hy2/config`` on the REST service.

Config ships as a flat dict; we render it to YAML and drop it at
``/etc/hysteria/config.yaml`` along with the cert + key. The apernet
binary has no hot-reload; any change triggers a subprocess restart.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

try:
    import yaml  # PyYAML
except ImportError:  # pragma: no cover — added to requirements.txt
    yaml = None  # type: ignore

from logger import logger


HYSTERIA_BIN = os.environ.get("HYSTERIA_EXECUTABLE_PATH", "/usr/local/bin/hysteria")
HYSTERIA_DIR = Path(os.environ.get("HYSTERIA_CONFIG_DIR", "/etc/hysteria"))
HYSTERIA_CONFIG = HYSTERIA_DIR / "config.yaml"
HYSTERIA_CERT = HYSTERIA_DIR / "cert.pem"
HYSTERIA_KEY = HYSTERIA_DIR / "key.pem"

# Panel's hy2-auth callback URL. The binary queries this on every new
# client handshake + periodic usage report.
PANEL_HY2_AUTH_URL = os.environ.get("PANEL_HY2_AUTH_URL", "")


class HysteriaManager:
    """Owns at most one running hysteria subprocess + its config file."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._started_at: Optional[float] = None
        self._current_tag: Optional[str] = None
        self._current_id: Optional[int] = None

    # ---- public API --------------------------------------------------------

    @property
    def binary_present(self) -> bool:
        return bool(HYSTERIA_BIN) and os.path.isfile(HYSTERIA_BIN)

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def apply(self, cfg: dict) -> None:
        """Write config + respawn. ``cfg`` is the flat shape produced by
        the panel's ``_build_payload`` in ``app/xray/hy2_sync.py``."""
        if not self.binary_present:
            logger.warning("hysteria binary missing at %s", HYSTERIA_BIN)
            raise RuntimeError(f"hysteria binary not found at {HYSTERIA_BIN}")
        if yaml is None:
            raise RuntimeError("PyYAML is required to render hysteria config")

        HYSTERIA_DIR.mkdir(parents=True, exist_ok=True)
        HYSTERIA_CERT.write_text(cfg.get("cert_pem", ""))
        HYSTERIA_CERT.chmod(0o644)
        HYSTERIA_KEY.write_text(cfg.get("key_pem", ""))
        HYSTERIA_KEY.chmod(0o600)

        yaml_cfg = self._render(cfg)
        HYSTERIA_CONFIG.write_text(yaml_cfg)
        HYSTERIA_CONFIG.chmod(0o644)

        self._current_tag = cfg.get("tag")
        self._current_id = cfg.get("id")
        self._respawn()

    def stop(self) -> None:
        """Terminate the running subprocess (if any). Safe to call when
        nothing is running."""
        with self._lock:
            proc = self._proc
            self._proc = None
            self._started_at = None
            self._current_tag = None
            self._current_id = None

        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        except Exception as e:  # best-effort shutdown
            logger.warning("hysteria stop: %s", e)

    def status(self) -> dict:
        with self._lock:
            alive = self._proc is not None and self._proc.poll() is None
            return {
                "binary_present": self.binary_present,
                "running": alive,
                "pid": self._proc.pid if (alive and self._proc) else None,
                "uptime_s": int(time.time() - self._started_at) if (alive and self._started_at) else 0,
                "tag": self._current_tag,
                "inbound_id": self._current_id,
                "config_path": str(HYSTERIA_CONFIG) if HYSTERIA_CONFIG.exists() else None,
            }

    # ---- internals ---------------------------------------------------------

    def _render(self, cfg: dict) -> str:
        obfs_type = cfg.get("obfs_type")
        obfs_password = cfg.get("obfs_password")

        out: dict = {
            "listen": f":{int(cfg['listen_port'])}",
            "tls": {
                "cert": str(HYSTERIA_CERT),
                "key": str(HYSTERIA_KEY),
            },
            "auth": {
                "type": "http",
                "http": {
                    "url": PANEL_HY2_AUTH_URL or "http://127.0.0.1/api/v1/hy2-auth",
                    "insecure": False,
                },
            },
            "masquerade": {
                "type": "proxy",
                "proxy": {
                    "url": cfg.get("masquerade_url") or "https://www.bing.com",
                    "rewriteHost": True,
                },
            },
            "bandwidth": {"up": "1 gbps", "down": "1 gbps"},
            "quic": {
                "initStreamReceiveWindow": 8388608,
                "maxStreamReceiveWindow": 8388608,
                "initConnReceiveWindow": 20971520,
                "maxConnReceiveWindow": 20971520,
                "maxIdleTimeout": "60s",
                "maxIncomingStreams": 1024,
                "disablePathMTUDiscovery": False,
            },
        }
        if obfs_type == "salamander" and obfs_password:
            out["obfs"] = {"type": "salamander",
                           "salamander": {"password": obfs_password}}
        return yaml.safe_dump(out, sort_keys=False, default_flow_style=False)

    def _respawn(self) -> None:
        # Kill prior instance first
        self.stop()
        with self._lock:
            logger.info("starting hysteria: %s server --config %s",
                        HYSTERIA_BIN, HYSTERIA_CONFIG)
            self._proc = subprocess.Popen(
                [HYSTERIA_BIN, "server", "--config", str(HYSTERIA_CONFIG)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,  # own process group so SIGTERM is clean
            )
            self._started_at = time.time()


# Module-level singleton consumed by rest_service.
manager = HysteriaManager()
