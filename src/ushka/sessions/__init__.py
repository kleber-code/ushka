"""Sessions: the signed cookie (default) and revocable server-side sessions.

``Session`` keeps the data in the signed cookie. ``ServerSession`` keeps it in a
store (``[session] store = "database"``) and puts only an opaque id in the
cookie, so logging out really ends the session. See the Sessions guide.
"""

from .forge import aforge_session_cookie, forge_session_cookie, parse_session_pairs
from .piece import Sessions
from .session import ServerSession, Session
from .stores import (
    DatabaseStore,
    SessionRecord,
    SessionStore,
    get_store,
    no_database_reason,
    revoke_user_sessions,
)

__all__ = [
    "DatabaseStore",
    "ServerSession",
    "Session",
    "SessionRecord",
    "SessionStore",
    "Sessions",
    "aforge_session_cookie",
    "forge_session_cookie",
    "get_store",
    "no_database_reason",
    "parse_session_pairs",
    "revoke_user_sessions",
]
