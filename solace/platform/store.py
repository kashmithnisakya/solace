"""SQLite storage for the human side of Solace: counsellors, their logins, hand-offs and an audit log.

People who talk to Solace never need an account. A hand-off only exists after the person agrees
to let a counsellor read their conversation.
"""

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from pydantic import BaseModel

SCHEMA = """
CREATE TABLE IF NOT EXISTS counsellors (
    id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
    pw_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS staff_sessions (
    token_hash TEXT PRIMARY KEY, counsellor_id TEXT NOT NULL, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS handoffs (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, status TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'none', created_at REAL NOT NULL, updated_at REAL NOT NULL,
    accepted_at REAL, closed_at REAL, counsellor_id TEXT, note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS handoffs_session ON handoffs (session_id);
CREATE TABLE IF NOT EXISTS audit_log (
    at REAL NOT NULL, counsellor_id TEXT NOT NULL, action TEXT NOT NULL, handoff_id TEXT
);
"""

SESSION_DAYS = 7
RISK_ORDER = {"none": 0, "low": 1, "moderate": 2, "high": 3, "imminent": 4}


class Counsellor(BaseModel):
    id: str
    email: str
    name: str


class Handoff(BaseModel):
    id: str
    session_id: str
    status: str  # requested → active → closed
    risk_level: str
    created_at: float
    updated_at: float
    accepted_at: float | None = None
    closed_at: float | None = None
    counsellor_id: str | None = None
    counsellor_name: str | None = None
    note: str = ""


# ---------- passwords ----------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    check = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(check.hex(), digest)


_DUMMY_HASH = hash_password(secrets.token_hex(8))  # keeps login timing the same for unknown emails


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- store ----------


class PlatformStore:
    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def _q(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self._lock, self._db:
            return self._db.execute(sql, args).fetchall()

    # counsellors

    def add_counsellor(self, email: str, name: str, password: str) -> Counsellor:
        if len(password) < 12:
            raise ValueError("Use a password of at least 12 characters.")
        c = Counsellor(id=uuid.uuid4().hex, email=email.strip().lower(), name=name.strip())
        self._q(
            "INSERT INTO counsellors VALUES (?, ?, ?, ?, 1, ?)",
            (c.id, c.email, c.name, hash_password(password), time.time()),
        )
        return c

    def set_active(self, email: str, active: bool) -> bool:
        with self._lock, self._db:
            cur = self._db.execute(
                "UPDATE counsellors SET active=? WHERE email=?", (int(active), email.strip().lower())
            )
            if not active:
                self._db.execute(
                    "DELETE FROM staff_sessions "
                    "WHERE counsellor_id IN (SELECT id FROM counsellors WHERE email=?)",
                    (email.strip().lower(),),
                )
            return cur.rowcount > 0

    def list_counsellors(self) -> list[tuple[Counsellor, bool]]:
        rows = self._q("SELECT id, email, name, active FROM counsellors ORDER BY name")
        return [(Counsellor(id=i, email=e, name=n), bool(a)) for i, e, n, a in rows]

    def login(self, email: str, password: str) -> str | None:
        """Returns a new session token, or None. Takes the same time whether or not the email exists."""
        rows = self._q(
            "SELECT id, pw_hash FROM counsellors WHERE email=? AND active=1", (email.strip().lower(),)
        )
        if not rows:
            verify_password(password, _DUMMY_HASH)
            return None
        cid, pw_hash = rows[0]
        if not verify_password(password, pw_hash):
            return None
        token = secrets.token_urlsafe(32)
        self._q(
            "INSERT INTO staff_sessions VALUES (?, ?, ?)",
            (_token_hash(token), cid, time.time() + SESSION_DAYS * 86400),
        )
        self.audit(cid, "login")
        return token

    def counsellor_for(self, token: str | None) -> Counsellor | None:
        if not token:
            return None
        rows = self._q(
            "SELECT c.id, c.email, c.name FROM staff_sessions s JOIN counsellors c ON c.id = s.counsellor_id "
            "WHERE s.token_hash=? AND s.expires_at>? AND c.active=1",
            (_token_hash(token), time.time()),
        )
        return Counsellor(id=rows[0][0], email=rows[0][1], name=rows[0][2]) if rows else None

    def logout(self, token: str) -> None:
        self._q("DELETE FROM staff_sessions WHERE token_hash=?", (_token_hash(token),))

    # hand-offs

    _COLS = (
        "h.id, h.session_id, h.status, h.risk_level, h.created_at, h.updated_at, h.accepted_at, "
        "h.closed_at, h.counsellor_id, c.name, h.note"
    )
    _FROM = "FROM handoffs h LEFT JOIN counsellors c ON c.id = h.counsellor_id"

    def _handoffs(self, where: str, args: tuple = ()) -> list[Handoff]:
        rows = self._q(f"SELECT {self._COLS} {self._FROM} WHERE {where}", args)
        keys = list(Handoff.model_fields)
        return [Handoff(**dict(zip(keys, r, strict=True))) for r in rows]

    def get(self, handoff_id: str) -> Handoff | None:
        found = self._handoffs("h.id=?", (handoff_id,))
        return found[0] if found else None

    def open_for(self, session_id: str) -> Handoff | None:
        """The person's current hand-off (waiting or with a counsellor), if any."""
        found = self._handoffs(
            "h.session_id=? AND h.status != 'closed' ORDER BY h.created_at DESC", (session_id,)
        )
        return found[0] if found else None

    def request(self, session_id: str, risk_level: str) -> Handoff:
        existing = self.open_for(session_id)
        if existing:
            return existing
        now = time.time()
        hid = uuid.uuid4().hex
        self._q(
            "INSERT INTO handoffs (id, session_id, status, risk_level, created_at, updated_at) "
            "VALUES (?, ?, 'requested', ?, ?, ?)",
            (hid, session_id, risk_level, now, now),
        )
        return self.get(hid)  # type: ignore[return-value]

    def accept(self, handoff_id: str, counsellor_id: str) -> Handoff | None:
        now = time.time()
        with self._lock, self._db:
            cur = self._db.execute(
                "UPDATE handoffs SET status='active', counsellor_id=?, accepted_at=?, updated_at=? "
                "WHERE id=? AND status='requested'",
                (counsellor_id, now, now, handoff_id),
            )
        return self.get(handoff_id) if cur.rowcount else None

    def close(self, handoff_id: str, note: str = "") -> Handoff | None:
        now = time.time()
        with self._lock, self._db:
            cur = self._db.execute(
                "UPDATE handoffs SET status='closed', closed_at=?, updated_at=?, note=? "
                "WHERE id=? AND status != 'closed'",
                (now, now, note[:2000], handoff_id),
            )
        return self.get(handoff_id) if cur.rowcount else None

    def touch(self, session_id: str, risk_level: str) -> Handoff | None:
        """Note new activity, keeping the highest risk seen during the hand-off."""
        h = self.open_for(session_id)
        if not h:
            return None
        level = (
            risk_level if RISK_ORDER.get(risk_level, 0) > RISK_ORDER.get(h.risk_level, 0) else h.risk_level
        )
        self._q("UPDATE handoffs SET risk_level=?, updated_at=? WHERE id=?", (level, time.time(), h.id))
        return self.get(h.id)

    def queue(self, since: float) -> list[Handoff]:
        """Open hand-offs, plus ones closed since `since`. Most urgent and longest waiting first."""
        found = self._handoffs("h.status != 'closed' OR h.closed_at > ?", (since,))
        status_order = {"requested": 0, "active": 1, "closed": 2}
        return sorted(
            found, key=lambda h: (status_order[h.status], -RISK_ORDER.get(h.risk_level, 0), h.created_at)
        )

    def delete_session(self, session_id: str) -> None:
        self._q("DELETE FROM handoffs WHERE session_id=?", (session_id,))

    # audit

    def audit(self, counsellor_id: str, action: str, handoff_id: str | None = None) -> None:
        """Who did what, and when. Never message content."""
        self._q("INSERT INTO audit_log VALUES (?, ?, ?, ?)", (time.time(), counsellor_id, action, handoff_id))

    def audit_entries(self, limit: int = 100) -> list[tuple]:
        return self._q(
            "SELECT at, counsellor_id, action, handoff_id FROM audit_log ORDER BY at DESC LIMIT ?", (limit,)
        )
