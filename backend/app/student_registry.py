import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Callable
from backend.app.database import get_db

class StudentRegistry:
    def __init__(self):
        # In-memory fast cache: ip -> dict
        self._students: Dict[str, Dict[str, Any]] = {}
        self._next_station_number: int = 1
        self._lock = asyncio.Lock()
        self._on_update_callback: Optional[Callable[[Dict[str, Any]], Any]] = None

    def set_update_callback(self, callback: Callable[[Dict[str, Any]], Any]):
        self._on_update_callback = callback

    async def initialize(self):
        """Učitaj postojeće radne stanice i studente iz baze."""
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM students ORDER BY id ASC")
            rows = await cursor.fetchall()
            for row in rows:
                data = dict(row)
                self._students[data["ip_address"]] = data

            # Odredi idući broj stanice
            if self._students:
                highest_num = 0
                for s in self._students.values():
                    name = s.get("workstation_name", "")
                    if "Radna stanica #" in name:
                        try:
                            num = int(name.split("#")[-1])
                            if num > highest_num:
                                highest_num = num
                        except ValueError:
                            pass
                self._next_station_number = highest_num + 1

    async def get_or_register_ip(self, ip_address: str) -> Dict[str, Any]:
        """Dohvati podatke o stanici ili automatski dodijeli naziv ako je nova IP adresa."""
        if ip_address in ("127.0.0.1", "::1"):
            ip_address = "127.0.0.1"

        if ip_address in self._students:
            return self._students[ip_address]

        async with self._lock:
            # Double-check inside lock
            if ip_address in self._students:
                return self._students[ip_address]

            station_name = f"Radna stanica #{self._next_station_number:02d}"
            self._next_station_number += 1
            now = datetime.now(timezone.utc).isoformat()

            student_data = {
                "ip_address": ip_address,
                "workstation_name": station_name,
                "full_name": None,
                "student_id": None,
                "checked_in_at": None,
                "is_checked_in": 0,
                "total_queries": 0,
                "violations_count": 0,
                "last_seen": now
            }

            # Spremi u SQLite
            async with get_db() as db:
                await db.execute("""
                    INSERT OR IGNORE INTO students 
                    (ip_address, workstation_name, full_name, student_id, checked_in_at, is_checked_in, total_queries, violations_count, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ip_address, station_name, None, None, None, 0, 0, 0, now
                ))
                await db.commit()
                
                cursor = await db.execute("SELECT id FROM students WHERE ip_address = ?", (ip_address,))
                row = await cursor.fetchone()
                if row:
                    student_data["id"] = row["id"]

            self._students[ip_address] = student_data

            # Obavijesti dashboard ako postoji callback
            if self._on_update_callback:
                asyncio.create_task(self._on_update_callback({
                    "type": "student_registered",
                    "student": student_data
                }))

            return student_data

    async def check_in_student(self, ip_address: str, full_name: str, student_id: str) -> Dict[str, Any]:
        """Student se prijavljuje preko studentskog portala."""
        await self.get_or_register_ip(ip_address)
        now = datetime.now(timezone.utc).isoformat()

        async with self._lock:
            student = self._students[ip_address]
            student["full_name"] = full_name.strip()
            student["student_id"] = student_id.strip()
            student["checked_in_at"] = now
            student["is_checked_in"] = 1
            student["last_seen"] = now

            # Ažuriraj u SQLite
            async with get_db() as db:
                await db.execute("""
                    UPDATE students 
                    SET full_name = ?, student_id = ?, checked_in_at = ?, is_checked_in = 1, last_seen = ?
                    WHERE ip_address = ?
                """, (student["full_name"], student["student_id"], now, now, ip_address))
                await db.commit()

            # Emitiraj WebSocket događaj
            if self._on_update_callback:
                asyncio.create_task(self._on_update_callback({
                    "type": "student_checked_in",
                    "student": student
                }))

            return student

    async def record_query_activity(self, ip_address: str, is_violation: bool):
        """Povećaj brojač upita i prekršaja za radnu stanicu."""
        if ip_address in ("127.0.0.1", "::1"):
            ip_address = "127.0.0.1"

        student = await self.get_or_register_ip(ip_address)
        student["total_queries"] += 1
        if is_violation:
            student["violations_count"] += 1
        student["last_seen"] = datetime.now(timezone.utc).isoformat()

        # Update u bazi asinkrono
        async with get_db() as db:
            await db.execute("""
                UPDATE students 
                SET total_queries = total_queries + 1,
                    violations_count = violations_count + ?,
                    last_seen = ?
                WHERE ip_address = ?
            """, (1 if is_violation else 0, student["last_seen"], ip_address))
            await db.commit()

    async def reset_all(self):
        """Potpuno čišćenje svih radnih stanica i studenata za novi ispit."""
        async with self._lock:
            self._students.clear()
            self._next_station_number = 1
            from backend.app.database import reset_classroom_data
            await reset_classroom_data()

            if self._on_update_callback:
                asyncio.create_task(self._on_update_callback({
                    "type": "classroom_reset",
                    "students": []
                }))

    def get_all_students(self):
        return list(self._students.values())

    def get_student(self, ip_address: str) -> Optional[Dict[str, Any]]:
        if ip_address in ("127.0.0.1", "::1"):
            ip_address = "127.0.0.1"
        return self._students.get(ip_address)

# Globalni singleton registar
student_registry = StudentRegistry()

