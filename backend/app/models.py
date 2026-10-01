from typing import Optional, List
from pydantic import BaseModel, Field

# --- Session Models ---
class ExamSessionCreate(BaseModel):
    title: str = Field(default="Ispit", description="Naziv ispita / kolegija")
    mode: str = Field(default="whitelist", description="whitelist, blacklist, or monitor")
    duration_minutes: int = Field(default=90, description="Trajanje ispita u minutama")

class ExamSessionResponse(BaseModel):
    id: int
    title: str
    mode: str
    duration_minutes: int
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    is_active: bool

class ModeSwitchRequest(BaseModel):
    mode: str = Field(..., description="whitelist, blacklist, or monitor")

# --- Student Models ---
class StudentCheckInRequest(BaseModel):
    full_name: str = Field(..., min_length=2, description="Ime i prezime studenta")
    student_id: str = Field(..., min_length=2, description="JMBAG ili broj indeksa")

class StudentUpdateRequest(BaseModel):
    workstation_name: Optional[str] = None
    full_name: Optional[str] = None
    student_id: Optional[str] = None

class StudentResponse(BaseModel):
    id: int
    ip_address: str
    workstation_name: str
    full_name: Optional[str] = None
    student_id: Optional[str] = None
    checked_in_at: Optional[str] = None
    is_checked_in: bool = False
    total_queries: int = 0
    violations_count: int = 0
    last_seen: Optional[str] = None

# --- Rule Models ---
class RuleCreate(BaseModel):
    domain: str = Field(..., min_length=2, description="Naziv domene ili wildcard npr. *.moodle.org")
    rule_type: str = Field(..., description="whitelist or blacklist")
    category: str = Field(default="custom", description="Kategorija npr. ai_cheat, social, search, custom")

class RuleResponse(BaseModel):
    id: int
    domain: str
    rule_type: str
    category: str
    is_enabled: bool

class CategoryToggleRequest(BaseModel):
    category: str
    enabled: bool

# --- Query Log Models ---
class QueryLogResponse(BaseModel):
    id: int
    session_id: Optional[int]
    timestamp: str
    client_ip: str
    workstation_name: str
    student_name: Optional[str] = None
    student_id: Optional[str] = None
    domain: str
    query_type: str
    status: str  # ALLOWED or BLOCKED
    category: Optional[str] = None
    reason: Optional[str] = None

# --- Stats Models ---
class StatsResponse(BaseModel):
    session_active: bool
    session_title: Optional[str] = None
    current_mode: str
    elapsed_seconds: int = 0
    total_queries: int = 0
    blocked_queries: int = 0
    allowed_queries: int = 0
    active_students_count: int = 0
    total_violations_count: int = 0
