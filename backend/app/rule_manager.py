import re
import fnmatch
from typing import Dict, List, Tuple, Any, Optional
from backend.app.database import get_db

class RuleManager:
    def __init__(self):
        self._whitelist_patterns: List[Dict[str, Any]] = []
        self._blacklist_patterns: List[Dict[str, Any]] = []
        self._category_states: Dict[str, bool] = {
            "ai_cheat": True,
            "doh_bypass": True,
            "search": True,
            "social": True,
            "custom": True,
            "educational": True,
        }
        self._active_session: Optional[Dict[str, Any]] = None

    async def initialize(self):
        """Učitaj sva pravila i aktivnu sesiju iz baze u memoriju."""
        async with get_db() as db:
            # 1. Učitaj aktivnu sesiju
            cursor = await db.execute("SELECT * FROM sessions WHERE is_active = 1 LIMIT 1")
            session = await cursor.fetchone()
            if session:
                self._active_session = dict(session)

            # 2. Učitaj pravila
            cursor = await db.execute("SELECT * FROM rules WHERE is_enabled = 1")
            rows = await cursor.fetchall()
            
            self._whitelist_patterns = []
            self._blacklist_patterns = []

            for r in rows:
                rule = dict(r)
                compiled_pattern = self._compile_domain_pattern(rule["domain"])
                rule_item = {
                    "id": rule["id"],
                    "domain": rule["domain"],
                    "category": rule["category"],
                    "pattern": compiled_pattern
                }
                if rule["rule_type"] == "whitelist":
                    self._whitelist_patterns.append(rule_item)
                else:
                    self._blacklist_patterns.append(rule_item)

    def _compile_domain_pattern(self, domain_str: str) -> re.Pattern:
        """Kompajlira domenu (s mogućim wildcardom) u regex."""
        d = domain_str.strip().lower().rstrip(".")
        if d.startswith("*."):
            base = re.escape(d[2:])
            return re.compile(rf"^(.*\.)?{base}$", re.IGNORECASE)
        elif "*" in d:
            pattern = fnmatch.translate(d)
            return re.compile(pattern, re.IGNORECASE)
        else:
            escaped = re.escape(d)
            return re.compile(rf"^(.*\.)?{escaped}$", re.IGNORECASE)

    def set_active_session(self, session: Optional[Dict[str, Any]]):
        self._active_session = session

    def get_active_session(self) -> Optional[Dict[str, Any]]:
        return self._active_session

    def get_current_mode(self) -> str:
        if not self._active_session or not self._active_session.get("is_active"):
            return "inactive"
        return self._active_session.get("mode", "whitelist")

    def toggle_category(self, category: str, enabled: bool):
        self._category_states[category] = enabled

    def is_category_enabled(self, category: str) -> bool:
        return self._category_states.get(category, True)

    def evaluate(self, domain: str) -> Tuple[str, str, str, bool]:
        """
        Ocjenjuje DNS upit za zadanu domenu.
        Vraća: (status ['ALLOWED'/'BLOCKED'], category, reason, is_violation [bool])
        """
        clean_domain = domain.strip().lower().rstrip(".")
        mode = self.get_current_mode()

        # Uvijek blokiraj DoH zaobilaženje (Firefox canary 'use-application-dns.net')
        if clean_domain == "use-application-dns.net":
            return ("BLOCKED", "doh_bypass", "Firefox DoH Canary blokiran za zaštitu lokalnog DNS-a", False)

        for b_rule in self._blacklist_patterns:
            if b_rule["category"] == "doh_bypass" and self.is_category_enabled("doh_bypass"):
                if b_rule["pattern"].match(clean_domain):
                    return ("BLOCKED", "doh_bypass", "Blokiran javni DoH poslužitelj", True)

        # 1. Ako sesija nije aktivna (Ispit nije u tijeku)
        if mode == "inactive":
            return ("ALLOWED", "normal", "Ispit nije aktivan", False)

        # 2. Način rada: Samo nadzor (Monitor-only)
        if mode == "monitor":
            for b_rule in self._blacklist_patterns:
                cat = b_rule["category"]
                if self.is_category_enabled(cat) and b_rule["pattern"].match(clean_domain):
                    return ("ALLOWED", cat, f"Nadzor: Detektiran sumnjiv posjet ({cat})", True)
            return ("ALLOWED", "normal", "Samo nadzor - promet dozvoljen", False)

        # 3. Način rada: Strogi Whitelist (Preporučeni ispitni mod)
        if mode == "whitelist":
            for w_rule in self._whitelist_patterns:
                if w_rule["pattern"].match(clean_domain):
                    return ("ALLOWED", "whitelist", "Dozvoljena ispitna stranica", False)
            
            for b_rule in self._blacklist_patterns:
                if b_rule["pattern"].match(clean_domain) and b_rule["category"] == "ai_cheat":
                    return ("BLOCKED", "ai_cheat", "Pokušaj pristupa AI alatu (Strogi mod)", True)

            return ("BLOCKED", "whitelist_violation", "Stranica nije na popisu dozvoljenih za ispit", True)

        # 4. Način rada: Blacklist (Blokiraj samo zabranjeno)
        if mode == "blacklist":
            for b_rule in self._blacklist_patterns:
                cat = b_rule["category"]
                if self.is_category_enabled(cat) and b_rule["pattern"].match(clean_domain):
                    reason = "Pokušaj pristupa zabranjenoj stranici"
                    if cat == "ai_cheat":
                        reason = "Pokušaj varanja pomoću AI alata"
                    elif cat == "search":
                        reason = "Zabranjena internetska tražilica"
                    elif cat == "social":
                        reason = "Zabranjena društvena mreža / komunikacijski kanal"
                    return ("BLOCKED", cat, reason, True)

            return ("ALLOWED", "normal", "Dozvoljen pristup internetu", False)

        return ("ALLOWED", "normal", "Zadani prolaz", False)

    async def add_rule(self, domain: str, rule_type: str, category: str = "custom") -> Dict[str, Any]:
        domain = domain.strip().lower()
        async with get_db() as db:
            cursor = await db.execute("""
                INSERT OR REPLACE INTO rules (domain, rule_type, category, is_enabled)
                VALUES (?, ?, ?, 1)
            """, (domain, rule_type, category))
            await db.commit()
            rule_id = cursor.lastrowid

        compiled = self._compile_domain_pattern(domain)
        rule_item = {
            "id": rule_id,
            "domain": domain,
            "category": category,
            "pattern": compiled
        }
        if rule_type == "whitelist":
            self._whitelist_patterns.append(rule_item)
        else:
            self._blacklist_patterns.append(rule_item)

        return rule_item

    async def delete_rule(self, rule_id: int):
        async with get_db() as db:
            await db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
            await db.commit()

        self._whitelist_patterns = [r for r in self._whitelist_patterns if r["id"] != rule_id]
        self._blacklist_patterns = [r for r in self._blacklist_patterns if r["id"] != rule_id]

# Globalni singleton
rule_manager = RuleManager()
