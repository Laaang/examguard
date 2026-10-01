#!/usr/bin/env python3
"""
ExamGuard DNS - Glavna pokretačka skripta
Pokreće istovremeno Web Dashboard (FastAPI/Uvicorn) i DNS Poslužitelj (dnslib/asyncio).
"""

import sys
import os
import argparse
import uvicorn

# Dodaj root direktorij u sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def main():
    parser = argparse.ArgumentParser(description="ExamGuard DNS Poslužitelj i Web Dashboard")
    parser.add_argument("--dns-port", type=int, default=int(os.getenv("DNS_PORT", 5053)),
                        help="UDP port za DNS poslužitelj (zadano: 5053 za testiranje, 53 za produkciju)")
    parser.add_argument("--web-port", type=int, default=int(os.getenv("WEB_PORT", 8000)),
                        help="TCP port za Web Dashboard (zadano: 8000)")
    parser.add_argument("--dns-host", type=str, default=os.getenv("DNS_HOST", "0.0.0.0"),
                        help="IP adresa na kojoj DNS sluša (zadano: 0.0.0.0)")
    parser.add_argument("--web-host", type=str, default=os.getenv("WEB_HOST", "0.0.0.0"),
                        help="IP adresa na kojoj Web sluša (zadano: 0.0.0.0)")
    parser.add_argument("--upstream", type=str, default=os.getenv("UPSTREAM_DNS", "1.1.1.1"),
                        help="Vanjski upstream DNS (zadano: 1.1.1.1)")

    args = parser.parse_args()

    # Postavi env varijable
    os.environ["DNS_PORT"] = str(args.dns_port)
    os.environ["WEB_PORT"] = str(args.web_port)
    os.environ["DNS_HOST"] = args.dns_host
    os.environ["WEB_HOST"] = args.web_host
    os.environ["UPSTREAM_DNS"] = args.upstream

    print("=" * 65)
    print("   EXAMGUARD DNS - SUSTAV ZA NADZOR I ZAŠTITU ISPITA")
    print("=" * 65)
    print(f"📡 DNS poslužitelj sluša na: {args.dns_host}:{args.dns_port} (UDP)")
    print(f"💻 Profesorov Dashboard:     http://localhost:{args.web_port}")
    print(f"🎓 Studentski Portal:        http://localhost:{args.web_port}/student")
    print(f"🌐 Upstream DNS resolver:    {args.upstream}:53")
    print("=" * 65)
    print("Pokretanje poslužitelja...\n")

    uvicorn.run(
        "backend.app.main:app",
        host=args.web_host,
        port=args.web_port,
        log_level="info",
        access_log=False
    )

if __name__ == "__main__":
    main()
