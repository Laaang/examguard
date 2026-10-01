import os
import sys
from pathlib import Path

# Base Paths & PyInstaller compatibility
if getattr(sys, "frozen", False):
    # Pokrenuto kao PyInstaller bundle (privremeni ekstrahirani folder za frontend)
    BASE_DIR = Path(sys._MEIPASS)
    # Baza podataka se sprema trajno u direktorij gdje se nalazi sam .exe
    EXE_DIR = Path(sys.executable).resolve().parent
    DB_PATH = os.getenv("EXAMGUARD_DB", str(EXE_DIR / "examguard.db"))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    DB_PATH = os.getenv("EXAMGUARD_DB", str(BASE_DIR / "examguard.db"))

FRONTEND_DIR = BASE_DIR / "frontend"

# Network & Server Settings
DNS_HOST = os.getenv("DNS_HOST", "0.0.0.0")
DNS_PORT = int(os.getenv("DNS_PORT", "5053"))  # 5053 for non-root testing, 53 for production
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))

# Upstream DNS Settings (Cloudflare primary, Google secondary)
UPSTREAM_DNS = os.getenv("UPSTREAM_DNS", "1.1.1.1")
UPSTREAM_DNS_PORT = int(os.getenv("UPSTREAM_DNS_PORT", "53"))
DNS_TIMEOUT = float(os.getenv("DNS_TIMEOUT", "2.0"))

# SINKHOLE IP
SINKHOLE_IP = "0.0.0.0"
