import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Callable, Any
from dnslib import DNSRecord, RR, A, AAAA, QTYPE, RCODE
from backend.app.config import (
    DNS_HOST,
    DNS_PORT,
    UPSTREAM_DNS,
    UPSTREAM_DNS_PORT,
    DNS_TIMEOUT,
    SINKHOLE_IP,
)
from backend.app.student_registry import student_registry
from backend.app.rule_manager import rule_manager
from backend.app.database import get_db

logger = logging.getLogger("examguard.dns")

class UpstreamClientProtocol(asyncio.DatagramProtocol):
    def __init__(self, future: asyncio.Future):
        self.future = future
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if not self.future.done():
            self.future.set_result(data)

    def error_received(self, exc):
        if not self.future.done():
            self.future.set_exception(exc)

class DNSServerProtocol(asyncio.DatagramProtocol):
    def __init__(self, ws_broadcaster: Optional[Callable[[dict], Any]] = None):
        self.transport = None
        self.ws_broadcaster = ws_broadcaster

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple):
        asyncio.create_task(self.handle_query(data, addr))

    async def forward_upstream(self, data: bytes) -> Optional[bytes]:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: UpstreamClientProtocol(future),
            remote_addr=(UPSTREAM_DNS, UPSTREAM_DNS_PORT)
        )
        try:
            transport.sendto(data)
            return await asyncio.wait_for(future, timeout=DNS_TIMEOUT)
        except Exception as e:
            logger.warning(f"Greška pri prosljeđivanju upstream DNS upita: {e}")
            return None
        finally:
            transport.close()

    async def handle_query(self, data: bytes, addr: tuple):
        client_ip = addr[0]
        try:
            request = DNSRecord.parse(data)
        except Exception as e:
            logger.error(f"Neuspjelo parsiranje DNS paketa od {client_ip}: {e}")
            return

        if not request.q:
            return

        domain = str(request.q.qname).rstrip(".")
        qtype_num = request.q.qtype
        qtype_str = QTYPE.get(qtype_num, "UNKNOWN")

        # 1. Registriraj ili dohvati radnu stanicu (Auto-Naming)
        student_info = await student_registry.get_or_register_ip(client_ip)
        workstation_name = student_info["workstation_name"]
        student_name = student_info.get("full_name")
        student_id = student_info.get("student_id")

        # 2. Provjeri pravila u RuleManageru
        status, category, reason, is_violation = rule_manager.evaluate(domain)
        now_iso = datetime.now(timezone.utc).isoformat()
        active_session = rule_manager.get_active_session()
        session_id = active_session["id"] if active_session else None

        response_bytes = None

        if status == "BLOCKED":
            reply = request.reply()
            
            # Ako je Firefox Canary domena, postavi NXDOMAIN
            if domain == "use-application-dns.net":
                reply.header.rcode = getattr(RCODE, "NXDOMAIN")
            else:
                reply.header.rcode = getattr(RCODE, "NOERROR")
                if qtype_str == "A":
                    reply.add_answer(RR(request.q.qname, QTYPE.A, rdata=A(SINKHOLE_IP), ttl=0))
                elif qtype_str == "AAAA":
                    reply.add_answer(RR(request.q.qname, QTYPE.AAAA, rdata=AAAA("::"), ttl=0))
                else:
                    # Za ostale tipove vraćamo NOERROR bez zapisa (Sinkhole)
                    pass

            response_bytes = reply.pack()
        else:
            # ALLOWED: Proslijedi na upstream DNS
            response_bytes = await self.forward_upstream(data)
            if not response_bytes:
                # Fallback ako upstream zakaže
                reply = request.reply()
                reply.header.rcode = getattr(RCODE, "SERVFAIL")
                response_bytes = reply.pack()

        # Pošalji odgovor nazad klijentu
        if self.transport and response_bytes:
            self.transport.sendto(response_bytes, addr)

        # 3. Zabilježi aktivnost i prekršaje
        await student_registry.record_query_activity(client_ip, is_violation=is_violation)

        # 4. Asinkrono spremi log u bazu
        log_payload = {
            "session_id": session_id,
            "timestamp": now_iso,
            "client_ip": client_ip,
            "workstation_name": workstation_name,
            "student_name": student_name,
            "student_id": student_id,
            "domain": domain,
            "query_type": qtype_str,
            "status": status,
            "category": category,
            "reason": reason,
            "is_violation": is_violation
        }

        asyncio.create_task(self._save_log_and_broadcast(log_payload))

    async def _save_log_and_broadcast(self, log_payload: dict):
        try:
            async with get_db() as db:
                cursor = await db.execute("""
                    INSERT INTO query_logs 
                    (session_id, timestamp, client_ip, workstation_name, student_name, student_id, domain, query_type, status, category, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_payload["session_id"],
                    log_payload["timestamp"],
                    log_payload["client_ip"],
                    log_payload["workstation_name"],
                    log_payload["student_name"],
                    log_payload["student_id"],
                    log_payload["domain"],
                    log_payload["query_type"],
                    log_payload["status"],
                    log_payload["category"],
                    log_payload["reason"],
                ))
                await db.commit()
                log_payload["id"] = cursor.lastrowid
        except Exception as e:
            logger.error(f"Greška pri spremanju DNS loga u bazu: {e}")

        # Pošalji preko WebSocketa dashboardu
        if self.ws_broadcaster:
            await self.ws_broadcaster({
                "type": "dns_query",
                "data": log_payload
            })
            if log_payload["is_violation"]:
                await self.ws_broadcaster({
                    "type": "violation_alert",
                    "data": log_payload
                })

class DNSServer:
    def __init__(self, host: str = DNS_HOST, port: int = DNS_PORT, ws_broadcaster: Optional[Callable[[dict], Any]] = None):
        self.host = host
        self.port = port
        self.ws_broadcaster = ws_broadcaster
        self.transport = None

    async def start(self):
        loop = asyncio.get_running_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: DNSServerProtocol(self.ws_broadcaster),
            local_addr=(self.host, self.port)
        )
        logger.info(f" ExamGuard DNS poslužitelj uspješno pokrenut na {self.host}:{self.port} (UDP)")

    def stop(self):
        if self.transport:
            self.transport.close()
            logger.info("ExamGuard DNS poslužitelj zaustavljen.")
