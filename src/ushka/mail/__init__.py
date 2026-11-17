"""Reading e-mail: `ImapClient`, the messages it returns and the limits it enforces.

Not imported by ``import ushka``: use ``from ushka.mail import ImapClient``.
"""

from .imap import (
    Attachment,
    ImapClient,
    ImapError,
    ImapSecurityError,
    Message,
    MessageNotFound,
    MessageRefused,
    build_search,
    decode_folder,
    encode_folder,
    parse_message,
)

__all__ = [
    "Attachment",
    "ImapClient",
    "ImapError",
    "ImapSecurityError",
    "Message",
    "MessageNotFound",
    "MessageRefused",
    "build_search",
    "decode_folder",
    "encode_folder",
    "parse_message",
]
