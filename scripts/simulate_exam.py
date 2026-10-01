#!/usr/bin/env python3
"""
ExamGuard DNS - Simulator ispitne učionice
Simulira prijavu učenika preko portala te slanje legitimnih i zabranjenih DNS upita.
"""

import sys
import time
import socket
import urllib.request
import json
from dnslib import DNSRecord

API_URL = "http://127.0.0.1:8000"
DNS_HOST = "127.0.0.1"
DNS_PORT = 5053

STUDENTS = [
    {"ip": "192.168.8.10", "name": "Ana Horvat", "id": "0036111222"},
    {"ip": "192.168.8.11", "name": "Ivan Babić", "id": "0036333444"},
    {"ip": "192.168.8.12", "name": "Lucija Kovačić", "id": "0036555666"},
    {"ip": "192.168.8.13", "name": "Matej Novak", "id": "0036777888"},
]

def checkin_student(ip, name, student_id):
    url = f"{API_URL}/api/student/checkin"
    payload = json.dumps({"full_name": name, "student_id": student_id}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "X-Forwarded-For": ip
    })
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f" [PRIJAVA] {name} ({student_id}) prijavljen s {ip} -> {data.get('student', {}).get('workstation_name')}")
    except Exception as e:
        print(f"❌ [GREŠKA PRIJAVE] {name}: {e}")

def send_dns_query(domain, client_ip=None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.0)
    q = DNSRecord.question(domain)
    
    try:
        sock.sendto(q.pack(), (DNS_HOST, DNS_PORT))
        resp_data, _ = sock.recvfrom(1024)
        resp = DNSRecord.parse(resp_data)
        answers = [str(r.rdata) for r in resp.rr]
        status = "⛔ BLOKIRANO" if any("0.0.0.0" in a for a in answers) else " DOZVOLJENO"
        print(f" [DNS UPIT] {domain.ljust(25)} -> {status} (Odgovor: {answers[:2]})")
    except Exception as e:
        print(f"❌ [DNS GREŠKA] {domain}: {e}")
    finally:
        sock.close()

def main():
    print("=" * 60)
    print("   ZAPOČINJEM SIMULACIJU ISPITNE UČIONICE (EXAMGUARD)")
    print("=" * 60)

    # 1. Prijava studenata
    print("\n1. Simulacija prijave studenata na studentskom portalu:")
    for s in STUDENTS:
        checkin_student(s["ip"], s["name"], s["id"])
        time.sleep(0.3)

    # 2. Slanje niza DNS upita
    print("\n2. Slanje DNS upita u ispitnom načinu rada:")
    test_domains = [
        ("moodle.carnet.hr", "Legitiman ispitni upit"),
        ("carnet.hr", "Legitimna domena"),
        ("chatgpt.com", "AI alat - VARANJE!"),
        ("claude.ai", "AI alat - VARANJE!"),
        ("use-application-dns.net", "Firefox Canary DoH zaobilaženje"),
        ("google.com", "Tražilica - nedozvoljeno"),
        ("deepseek.com", "AI alat - VARANJE!"),
        ("moodle.carnet.hr", "Povratak na ispitni Moodle"),
    ]

    for domain, note in test_domains:
        print(f"\n-> Test: {note}")
        send_dns_query(domain)
        time.sleep(0.5)

    print("\n" + "=" * 60)
    print("   SIMULACIJA USPJEŠNO ZAVRŠENA! Provjerite dashboard!")
    print("=" * 60)

if __name__ == "__main__":
    main()
