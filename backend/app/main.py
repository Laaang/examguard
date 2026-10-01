import os
import csv
import io
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import (
    DNS_HOST,
    DNS_PORT,
    WEB_HOST,
    WEB_PORT,
    FRONTEND_DIR,
)
from backend.app.database import init_db, get_db
from backend.app.models import (
    ExamSessionCreate,
    ExamSessionResponse,
    ModeSwitchRequest,
    StudentCheckInRequest,
    StudentUpdateRequest,
    RuleCreate,
    CategoryToggleRequest,
)
from backend.app.student_registry import student_registry
from backend.app.rule_manager import rule_manager
from backend.app.dns_engine import DNSServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("examguard.api")

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead)

manager = ConnectionManager()
dns_server_instance: Optional[DNSServer] = None
checkin_remaining_seconds: int = 0
checkin_task: Optional[asyncio.Task] = None

async def run_checkin_timer(total_seconds: int = 120):
    global checkin_remaining_seconds
    checkin_remaining_seconds = total_seconds
    try:
        while checkin_remaining_seconds > 0:
            await asyncio.sleep(1)
            checkin_remaining_seconds -= 1
            await manager.broadcast({
                "type": "checkin_tick",
                "remaining_seconds": checkin_remaining_seconds
            })
        
        # Automatski prebaci u ispit kad istekne prijava!
        active_session = rule_manager.get_active_session()
        if active_session and active_session.get("phase") == "checkin":
            await start_exam_internal()
    except asyncio.CancelledError:
        pass

async def start_exam_internal():
    global checkin_task, checkin_remaining_seconds
    if checkin_task and not checkin_task.done():
        checkin_task.cancel()
    checkin_remaining_seconds = 0
    now = datetime.now(timezone.utc).isoformat()
    active_session = rule_manager.get_active_session()
    if active_session:
        async with get_db() as db:
            await db.execute("""
                UPDATE sessions 
                SET phase = 'active', is_active = 1, exam_started_at = ?
                WHERE id = ?
            """, (now, active_session["id"]))
            await db.commit()
            active_session["phase"] = "active"
            active_session["is_active"] = 1
            active_session["exam_started_at"] = now
            rule_manager.set_active_session(active_session)

        await manager.broadcast({
            "type": "session_update",
            "session": active_session
        })
        await manager.broadcast({
            "type": "exam_started",
            "message": "Ispit je službeno započeo! Mrežni nadzor je aktivan."
        })

@asynccontextmanager
async def lifespan(app: FastAPI):
    global dns_server_instance
    logger.info(" Pokretanje ExamGuard DNS sustava...")
    
    await init_db()
    await student_registry.initialize()
    await rule_manager.initialize()
    student_registry.set_update_callback(manager.broadcast)

    dns_server_instance = DNSServer(
        host=DNS_HOST,
        port=DNS_PORT,
        ws_broadcaster=manager.broadcast
    )
    await dns_server_instance.start()
    
    yield
    
    global checkin_task
    if checkin_task and not checkin_task.done():
        checkin_task.cancel()

    if dns_server_instance:
        dns_server_instance.stop()
    logger.info("🛑 ExamGuard DNS sustav zaustavljen.")

app = FastAPI(
    title="ExamGuard DNS API",
    description="Sustav za nadzor i kontrolu ispita na razini DNS-a",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_client_ip(request: Request) -> str:
    """Iščitava pravu IP adresu klijenta."""
    x_forwarded = request.headers.get("X-Forwarded-For")
    if x_forwarded:
        ip = x_forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "127.0.0.1"
    if ip in ("::1", "127.0.0.1"):
        return "127.0.0.1"
    return ip

# ==========================================
# 1. Studentski Portal Rute (/student)
# ==========================================

@app.get("/student", response_class=FileResponse)
async def serve_student_page():
    student_file = FRONTEND_DIR / "student.html"
    if not student_file.exists():
        raise HTTPException(status_code=404, detail="student.html nije pronađen")
    return FileResponse(student_file)

@app.get("/api/student/me")
async def get_student_me(request: Request):
    """Vraća detektiranu IP adresu klijenta, radnu stanicu i ispitnu fazu."""
    client_ip = get_client_ip(request)
    station = await student_registry.get_or_register_ip(client_ip)
    active_session = rule_manager.get_active_session()
    
    return {
        "ip_address": client_ip,
        "workstation_name": station["workstation_name"],
        "full_name": station.get("full_name"),
        "student_id": station.get("student_id"),
        "is_checked_in": bool(station.get("is_checked_in")),
        "session": {
            "title": active_session["title"] if active_session else "Nema aktivnog ispita",
            "mode": rule_manager.get_current_mode(),
            "phase": active_session.get("phase", "idle") if active_session else "idle",
            "checkin_remaining": checkin_remaining_seconds,
            "is_active": bool(active_session and active_session.get("is_active"))
        }
    }

@app.post("/api/student/checkin")
async def checkin_student(payload: StudentCheckInRequest, request: Request):
    """Obrada forme za prijavu studenta na ispit."""
    client_ip = get_client_ip(request)
    updated_student = await student_registry.check_in_student(
        ip_address=client_ip,
        full_name=payload.full_name,
        student_id=payload.student_id
    )
    return {
        "status": "success",
        "message": f"Uspješna prijava! Dobrodošli, {payload.full_name}.",
        "student": updated_student
    }

# ==========================================
# 2. Profesor - Upravljanje ispitnom sesijom i fazama
# ==========================================

@app.get("/api/session")
async def get_current_session():
    session = rule_manager.get_active_session()
    if not session:
        return {"session": None, "mode": "inactive", "phase": "idle", "checkin_remaining": 0}
    return {
        "session": session,
        "mode": rule_manager.get_current_mode(),
        "phase": session.get("phase", "idle"),
        "checkin_remaining": checkin_remaining_seconds
    }

@app.post("/api/session/start-checkin")
async def start_checkin_phase():
    """Pokreće 2-minutnu fazu prijave studenata prije ispita."""
    global checkin_task
    if checkin_task and not checkin_task.done():
        checkin_task.cancel()

    duration = 120  # 2 minute
    now = datetime.now(timezone.utc).isoformat()
    active_session = rule_manager.get_active_session()

    async with get_db() as db:
        if active_session:
            await db.execute("""
                UPDATE sessions 
                SET phase = 'checkin', checkin_duration_seconds = ?, checkin_started_at = ?, is_active = 1
                WHERE id = ?
            """, (duration, now, active_session["id"]))
            await db.commit()
            active_session["phase"] = "checkin"
            active_session["checkin_duration_seconds"] = duration
            active_session["checkin_started_at"] = now
            active_session["is_active"] = 1
        else:
            cursor = await db.execute("""
                INSERT INTO sessions (title, mode, phase, checkin_duration_seconds, checkin_started_at, duration_minutes, started_at, is_active)
                VALUES (?, ?, 'checkin', ?, ?, 90, ?, 1)
            """, ("Ispit", "whitelist", duration, now, now))
            await db.commit()
            cursor2 = await db.execute("SELECT * FROM sessions WHERE id = ?", (cursor.lastrowid,))
            active_session = dict(await cursor2.fetchone())

    rule_manager.set_active_session(active_session)
    checkin_task = asyncio.create_task(run_checkin_timer(duration))

    await manager.broadcast({
        "type": "session_update",
        "session": active_session
    })
    return {"status": "success", "session": active_session, "duration": duration}

@app.post("/api/session/start-exam")
async def start_exam():
    """Ručno pokretanje ispita i aktivacija nadzora."""
    await start_exam_internal()
    return {"status": "success", "session": rule_manager.get_active_session()}

@app.post("/api/session/stop-exam")
async def stop_exam():
    """Zaustavljanje ispita i nadzora."""
    global checkin_task, checkin_remaining_seconds
    if checkin_task and not checkin_task.done():
        checkin_task.cancel()
    checkin_remaining_seconds = 0

    active_session = rule_manager.get_active_session()
    now = datetime.now(timezone.utc).isoformat()
    if active_session:
        async with get_db() as db:
            await db.execute("""
                UPDATE sessions 
                SET phase = 'finished', is_active = 0, ended_at = ? 
                WHERE id = ?
            """, (now, active_session["id"]))
            await db.commit()
            active_session["phase"] = "finished"
            active_session["is_active"] = 0
            active_session["ended_at"] = now

        rule_manager.set_active_session(active_session)
        await manager.broadcast({
            "type": "session_update",
            "session": active_session
        })
    return {"status": "success", "message": "Ispit je uspješno zaustavljen."}

@app.post("/api/session/reset-classroom")
async def reset_classroom():
    """Gumb za novi ispit: potpuno briše sve studente i logove te priprema čistu učionicu."""
    global checkin_task, checkin_remaining_seconds
    if checkin_task and not checkin_task.done():
        checkin_task.cancel()
    checkin_remaining_seconds = 0

    await student_registry.reset_all()

    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute("UPDATE sessions SET is_active = 0 WHERE is_active = 1")
        cursor = await db.execute("""
            INSERT INTO sessions (title, mode, phase, checkin_duration_seconds, duration_minutes, started_at, is_active)
            VALUES (?, 'whitelist', 'idle', 120, 90, ?, 0)
        """, ("Novi ispit", now))
        await db.commit()
        cursor2 = await db.execute("SELECT * FROM sessions WHERE id = ?", (cursor.lastrowid,))
        new_session = dict(await cursor2.fetchone())

    rule_manager.set_active_session(new_session)
    await manager.broadcast({
        "type": "classroom_reset",
        "students": []
    })
    await manager.broadcast({
        "type": "session_update",
        "session": new_session
    })
    return {"status": "success", "message": "Učionica je potpuno resetirana za novi ispit."}

@app.post("/api/session/mode")
async def change_session_mode(payload: ModeSwitchRequest):
    if payload.mode not in ("whitelist", "blacklist", "monitor"):
        raise HTTPException(status_code=400, detail="Nevažeći način rada")

    active_session = rule_manager.get_active_session()
    if not active_session:
        raise HTTPException(status_code=400, detail="Nema aktivne sesije")

    async with get_db() as db:
        await db.execute("UPDATE sessions SET mode = ? WHERE id = ?", (payload.mode, active_session["id"]))
        await db.commit()
        active_session["mode"] = payload.mode

    rule_manager.set_active_session(active_session)
    await manager.broadcast({
        "type": "session_update",
        "session": active_session
    })
    return {"status": "success", "mode": payload.mode}

# ==========================================
# 3. Profesor - Pregled studenata i radnih stanica
# ==========================================

@app.get("/api/students")
async def get_all_students():
    return student_registry.get_all_students()

@app.put("/api/students/{ip_address}")
async def update_student(ip_address: str, payload: StudentUpdateRequest):
    student = student_registry.get_student(ip_address)
    if not student:
        raise HTTPException(status_code=404, detail="Radna stanica nije pronađena")

    async with get_db() as db:
        if payload.workstation_name:
            student["workstation_name"] = payload.workstation_name
        if payload.full_name:
            student["full_name"] = payload.full_name
            student["is_checked_in"] = 1
        if payload.student_id:
            student["student_id"] = payload.student_id

        await db.execute("""
            UPDATE students 
            SET workstation_name = ?, full_name = ?, student_id = ?
            WHERE ip_address = ?
        """, (student["workstation_name"], student["full_name"], student["student_id"], ip_address))
        await db.commit()

    await manager.broadcast({
        "type": "student_updated",
        "student": student
    })
    return student

# ==========================================
# 4. Profesor - Pravila i kategorije
# ==========================================

@app.get("/api/rules")
async def get_all_rules():
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM rules ORDER BY rule_type DESC, id ASC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

@app.post("/api/rules")
async def create_rule(payload: RuleCreate):
    rule = await rule_manager.add_rule(
        domain=payload.domain,
        rule_type=payload.rule_type,
        category=payload.category
    )
    return rule

@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: int):
    await rule_manager.delete_rule(rule_id)
    return {"status": "success", "message": "Pravilo obrisano"}

@app.post("/api/categories/toggle")
async def toggle_category(payload: CategoryToggleRequest):
    rule_manager.toggle_category(payload.category, payload.enabled)
    return {"status": "success", "category": payload.category, "enabled": payload.enabled}

# ==========================================
# 5. Logovi, Statistika i CSV Izvoz
# ==========================================

@app.get("/api/logs")
async def get_query_logs(
    limit: int = 100,
    offset: int = 0,
    domain: Optional[str] = None,
    ip: Optional[str] = None,
    status: Optional[str] = None
):
    query = "SELECT * FROM query_logs WHERE 1=1"
    params = []

    if domain:
        query += " AND domain LIKE ?"
        params.append(f"%{domain}%")
    if ip:
        query += " AND client_ip = ?"
        params.append(ip)
    if status:
        query += " AND status = ?"
        params.append(status.upper())

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    async with get_db() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

@app.get("/api/stats")
async def get_system_stats():
    active_session = rule_manager.get_active_session()
    session_id = active_session["id"] if active_session else None

    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM query_logs WHERE session_id = ?", (session_id,))
        total_queries = (await cursor.fetchone())["cnt"]

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM query_logs WHERE session_id = ? AND status = 'BLOCKED'", (session_id,))
        blocked_queries = (await cursor.fetchone())["cnt"]

        allowed_queries = total_queries - blocked_queries

        all_students = student_registry.get_all_students()
        active_count = len(all_students)
        checked_in_count = sum(1 for s in all_students if s.get("is_checked_in"))
        total_violations = sum(s.get("violations_count", 0) for s in all_students)

    return {
        "session_active": bool(active_session and active_session.get("is_active")),
        "session_title": active_session["title"] if active_session else "Nema aktivnog ispita",
        "current_mode": rule_manager.get_current_mode(),
        "phase": active_session.get("phase", "idle") if active_session else "idle",
        "checkin_remaining": checkin_remaining_seconds,
        "total_queries": total_queries,
        "blocked_queries": blocked_queries,
        "allowed_queries": allowed_queries,
        "active_students_count": active_count,
        "checked_in_count": checked_in_count,
        "total_violations_count": total_violations
    }

@app.get("/api/logs/export")
async def export_logs_csv(session_id: Optional[int] = None):
    active_session = rule_manager.get_active_session()
    sid = session_id or (active_session["id"] if active_session else None)

    async with get_db() as db:
        if sid:
            cursor = await db.execute("SELECT * FROM query_logs WHERE session_id = ? ORDER BY id ASC", (sid,))
        else:
            cursor = await db.execute("SELECT * FROM query_logs ORDER BY id ASC")
        rows = await cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Vrijeme (UTC)", "IP Adresa", "Radna stanica", 
        "Student (Ime i Prezime)", "Broj indeksa / JMBAG", 
        "Tražena domena", "Tip upita", "Status", "Kategorija", "Razlog"
    ])

    for row in rows:
        writer.writerow([
            row["id"],
            row["timestamp"],
            row["client_ip"],
            row["workstation_name"],
            row["student_name"] or "Neprijavljen",
            row["student_id"] or "-",
            row["domain"],
            row["query_type"],
            row["status"],
            row["category"] or "-",
            row["reason"] or "-"
        ])

    output.seek(0)
    filename = f"ispit_dns_logovi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ==========================================
# 6. WebSocket Endpoint (/ws)
# ==========================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        stats = await get_system_stats()
        await websocket.send_json({
            "type": "initial_state",
            "stats": stats,
            "students": student_registry.get_all_students()
        })
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

# ==========================================
# 7. Static Files & Root Route
# ==========================================

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/", response_class=FileResponse)
async def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>ExamGuard DNS</h1><p>Frontend se učitava...</p>")
    return FileResponse(index_file)
