"""Sessions: the signed cookie (default) and revocable server-side sessions.

``Session`` keeps the data in the signed cookie. ``ServerSession`` keeps it in a
store (``[session] store = "database"``) and puts only an opaque id in the
cookie, so logging out really ends the session. See the Sessions guide.
"""

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
    "get_store",
    "no_database_reason",
    "revoke_user_sessions",
]
