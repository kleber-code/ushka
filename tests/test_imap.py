"""`ushka.mail.ImapClient`: no network, an `imaplib` stand-in with canned answers."""

import asyncio
import imaplib
import logging
import re
import ssl
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from email.message import EmailMessage

import pytest

from ushka import redirect
from ushka.core.config import Config
from ushka.guard import UnsafeValueError, Untrusted, check_html, check_path, safe
from ushka.mail import (
    ImapClient,
    ImapError,
    ImapSecurityError,
    MessageNotFound,
    MessageRefused,
    build_search,
    decode_folder,
    encode_folder,
    parse_message,
)

PASSWORD = "s3cret-p@ss\"word"
BODY_MARK = "CONFIDENTIAL-BODY-MARKER"


# -- the stand-in server ------------------------------------------------------------


class Server:
    """What the fake `imaplib` classes talk to."""

    def __init__(self):
        self.messages: dict[int, bytes] = {}
        self.flags: dict[int, set[str]] = {}
        self.commands: list[tuple] = []
        self.constructed: list[dict] = []
        self.caps = b"IMAP4rev1 UIDPLUS"
        self.folders = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Faturas &AOc-&AOM-o"', b'(\\Noselect) "/" "[Gmail]"']
        self.delay = 0.0
        self.busy = 0
        self.overlap = False
        self.fail_with: Exception | None = None
        self.sizes: dict[int, int] = {}
        self.fetched_bodies: list[int] = []
        self.starttls_called = False

    def add(self, uid, raw, flags=()):
        self.messages[uid] = raw
        self.flags[uid] = set(flags)


@pytest.fixture
def server(monkeypatch):
    srv = Server()

    class Fake:
        def __init__(self, host, port=143, *, ssl_context=None, timeout=None):
            srv.constructed.append({"cls": type(self).__name__, "host": host, "port": port, "ssl_context": ssl_context, "timeout": timeout})
            self.closed = False

        def starttls(self, ssl_context=None):
            srv.starttls_called = True
            srv.constructed[-1]["starttls_context"] = ssl_context

        def login(self, user, password):
            srv.commands.append(("LOGIN", user))
            if password != PASSWORD:
                raise imaplib.IMAP4.error(f"[AUTHENTICATIONFAILED] login failed for {password}")
            return "OK", [b"ok"]

        def capability(self):
            return "OK", [srv.caps]

        def select(self, mailbox, readonly=False):
            srv.commands.append(("SELECT", mailbox, readonly))
            return "OK", [str(len(srv.messages)).encode()]

        def list(self):
            return "OK", list(srv.folders)

        def expunge(self):
            srv.commands.append(("EXPUNGE",))
            for uid in [u for u, f in srv.flags.items() if "\\Deleted" in f]:
                srv.messages.pop(uid)
                srv.flags.pop(uid)
            return "OK", [None]

        def logout(self):
            srv.commands.append(("LOGOUT",))
            return "BYE", [b"bye"]

        def shutdown(self):
            srv.commands.append(("SHUTDOWN",))

        def uid(self, command, *args):
            srv.busy += 1
            if srv.busy > 1:
                srv.overlap = True
            try:
                if srv.delay:
                    time.sleep(srv.delay)
                if srv.fail_with is not None:
                    raise srv.fail_with
                srv.commands.append((command, args))
                return self._uid(command, *args)
            finally:
                srv.busy -= 1

        def _uid(self, command, *args):
            if command == "SEARCH":
                tokens = [a.decode() if isinstance(a, bytes) else a for a in args]
                if tokens[:2] == ["CHARSET", "UTF-8"]:
                    tokens = tokens[2:]
                if tokens == ["UNSEEN"]:
                    ids = [u for u, f in srv.flags.items() if "\\Seen" not in f]
                elif tokens == ["DELETED"]:
                    ids = [u for u, f in srv.flags.items() if "\\Deleted" in f]
                else:
                    ids = list(srv.messages)
                return "OK", [" ".join(map(str, ids)).encode()]
            if command == "FETCH":
                uid = int(args[0])
                if uid not in srv.messages:
                    return "OK", [None]
                raw = srv.messages[uid]
                if args[1] == "(RFC822.SIZE)":
                    size = srv.sizes.get(uid, len(raw))
                    return "OK", [f"1 (UID {uid} RFC822.SIZE {size})".encode()]
                srv.fetched_bodies.append(uid)
                return "OK", [(f"1 (UID {uid} BODY[] {{{len(raw)}}}".encode(), raw), b")"]
            if command == "STORE":
                uid, op, flag = int(args[0]), args[1], args[2].strip("()")
                if op.startswith("+"):
                    srv.flags[uid].add(flag)
                else:
                    srv.flags[uid].discard(flag)
                return "OK", [None]
            if command == "COPY":
                return "OK", [None]
            if command == "EXPUNGE":
                uid = int(args[0])
                srv.messages.pop(uid, None)
                srv.flags.pop(uid, None)
                return "OK", [None]
            raise AssertionError(f"unexpected command {command}")

    monkeypatch.setattr(imaplib, "IMAP4_SSL", type("IMAP4_SSL", (Fake,), {}))
    monkeypatch.setattr(imaplib, "IMAP4", type("IMAP4", (Fake,), {"error": imaplib.IMAP4.error, "abort": imaplib.IMAP4.abort}))
    return srv


def client(**kw):
    kw.setdefault("user", "me@example.com")
    kw.setdefault("password", PASSWORD)
    return ImapClient("imap.example.com", **kw)


def simple(subject="Hello", body="Hi there", from_="Ann <ann@example.com>"):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_
    msg["To"] = "me@example.com, Bob <bob@example.com>"
    msg["Cc"] = "carol@example.com"
    msg["Date"] = "Mon, 17 Nov 2026 10:00:00 +0000"
    msg["Message-ID"] = "<abc@example.com>"
    msg.set_content(body)
    return msg.as_bytes()


# -- normal flow ---------------------------------------------------------------------


async def test_normal_flow(server):
    server.add(1, simple("First"), flags={"\\Seen"})
    server.add(2, simple("Second", body=BODY_MARK))
    server.add(3, simple("Third"))
    async with client() as mail:
        assert await mail.folders() == ["INBOX", "Faturas ção", "[Gmail]"]
        assert await mail.select("INBOX") == 3
        assert await mail.search(unseen=True) == [2, 3]
        msg = await mail.fetch(2)
        assert msg.uid == 2 and msg.subject == "Second" and BODY_MARK in msg.text
        assert msg.from_ == "Ann <ann@example.com>" and msg.from_address == "ann@example.com"
        assert msg.to == ["me@example.com", "Bob <bob@example.com>"] and msg.cc == ["carol@example.com"]
        assert msg.date == datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
        assert msg.message_id == "<abc@example.com>" and msg.headers["subject"] == "Second"
        assert "\\Seen" not in server.flags[2]  # fetch does not mark it read
        await mail.mark_seen(2)
        assert "\\Seen" in server.flags[2]
        await mail.mark_unseen(2)
        assert "\\Seen" not in server.flags[2]
        await mail.move(3, "Faturas çã")
        assert ("COPY", ("3", '"Faturas &AOcA4w-"')) in server.commands
        assert 3 not in server.messages
        await mail.delete(2)
        assert list(server.messages) == [1]
    assert server.commands[-1] == ("LOGOUT",)


async def test_unseen_iterator_uses_uids_and_skips_refused(server):
    server.add(10, simple("ok"))
    server.add(11, simple("big"))
    server.add(12, simple("ok2"))
    server.sizes[11] = 50 * 1024 * 1024
    refused = []
    async with client() as mail:
        got = [m.uid async for m in mail.unseen(on_error=lambda uid, exc: refused.append(uid))]
        assert got == [10, 12] and refused == [11]
        with pytest.raises(MessageRefused):
            [m async for m in mail.unseen()]


async def test_fetch_of_a_missing_uid(server):
    async with client() as mail:
        with pytest.raises(MessageNotFound):
            await mail.fetch(99)


@pytest.mark.parametrize("bad", [0, -1, True, "1; DELETE", 2**40, 1.5, "1 2"])
async def test_uids_are_validated(server, bad):
    async with client() as mail:
        with pytest.raises(ImapSecurityError):
            await mail.fetch(bad)
        with pytest.raises(ImapSecurityError):
            await mail.mark_seen(bad)


async def test_uid_may_be_a_digit_string(server):
    server.add(5, simple())
    async with client() as mail:
        assert (await mail.fetch("5")).uid == 5


async def test_delete_without_uidplus_refuses_to_expunge_other_messages(server):
    server.caps = b"IMAP4rev1"
    server.add(1, simple(), flags={"\\Deleted"})  # someone else's pending delete
    server.add(2, simple())
    async with client() as mail:
        with pytest.raises(ImapError, match="UIDPLUS"):
            await mail.delete(2)
        assert 1 in server.messages and 2 in server.messages
        del server.flags[1]  # nothing else pending
        server.flags[1] = set()
        await mail.delete(2)
    assert list(server.messages) == [1]


# -- the criteria builder ----------------------------------------------------------------


def tokens(**kw):
    return [t.decode() for t in build_search(**kw)]


def test_search_criteria():
    assert tokens() == ["ALL"]
    assert tokens(unseen=True, seen=False) == ["UNSEEN"]
    assert tokens(from_="ann@example.com", subject="Invoice 7") == ["FROM", '"ann@example.com"', "SUBJECT", '"Invoice 7"']
    assert tokens(since=date(2026, 1, 5), before=datetime(2026, 11, 17, 8, 0)) == ["SINCE", "05-Jan-2026", "BEFORE", "17-Nov-2026"]
    assert tokens(larger=1000, smaller=5) == ["LARGER", "1000", "SMALLER", "5"]
    assert tokens(header=("X-Spam", "yes"), keyword="Lead") == ["HEADER", "X-Spam", '"yes"', "KEYWORD", "Lead"]
    assert tokens(uid=[3, 4]) == ["UID", "3,4"] and tokens(uid="5:*") == ["UID", "5:*"]


def test_search_values_are_quoted_and_escaped():
    assert tokens(subject='say "hi"') == ["SUBJECT", '"say \\"hi\\""']
    assert tokens(subject="back\\slash") == ["SUBJECT", '"back\\\\slash"']
    assert tokens(subject='x\\" OR ALL') == ["SUBJECT", '"x\\\\\\" OR ALL"']  # the quote stays inside the string
    assert build_search(subject="ação")[1] == '"ação"'.encode()


@pytest.mark.parametrize("value", ["a\r\nA1 DELETE INBOX", "a\nb", "a\rb", "a\x00b", "a\x7fb", "a\tb"])
def test_search_refuses_control_characters(value):
    for key in ("subject", "from_", "body", "text"):
        with pytest.raises(ImapSecurityError):
            build_search(**{key: value})
    with pytest.raises(ImapSecurityError):
        build_search(header=("X-A", value))


@pytest.mark.parametrize(
    "kw",
    [
        {"header": ("X Bad\r\n", "v")},
        {"keyword": "a b"},
        {"keyword": "x)\r\n"},
        {"uid": "1:2 OR ALL"},
        {"uid": []},
    ],
)
def test_search_refuses_malformed_atoms(kw):
    with pytest.raises(ImapSecurityError):
        build_search(**kw)


@pytest.mark.parametrize("kw", [{"larger": -1}, {"larger": True}, {"larger": "5 OR ALL"}, {"since": "2026-01-01"}, {"unseen": "yes"}, {"nope": 1}, {"subject": 5}])
def test_search_refuses_wrong_types(kw):
    with pytest.raises(TypeError):
        build_search(**kw)


async def test_search_sends_charset_for_unicode_and_never_a_second_command(server):
    server.add(1, simple())
    async with client() as mail:
        await mail.search(subject="fatura ção")
        with pytest.raises(ImapSecurityError):
            await mail.search(subject="x\r\nA2 LOGOUT")
    _cmd, args = next(c for c in server.commands if c[0] == "SEARCH")
    assert args[:2] == (b"CHARSET", b"UTF-8")
    assert not any(c[0] == "LOGOUT" for c in server.commands[:-1])  # only the real logout, at the end
    assert len([c for c in server.commands if c[0] == "SEARCH"]) == 1


async def test_search_limit_keeps_the_newest(server):
    for i in range(1, 6):
        server.add(i, simple())
    async with client() as mail:
        assert await mail.search(limit=2) == [4, 5]


# -- folder names ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, encoded",
    [
        ("INBOX", "INBOX"),
        ("Enviados & Rascunhos", "Enviados &- Rascunhos"),
        ("Faturas çã", "Faturas &AOcA4w-"),
        ("Entrada/Ações", "Entrada/A&AOcA9Q-es"),
        ("日本語", "&ZeVnLIqe-"),
        ("😀", "&2D3eAA-"),
    ],
)
def test_folder_names_are_modified_utf7(name, encoded):
    assert encode_folder(name) == encoded
    assert decode_folder(encoded) == name


@pytest.mark.parametrize("name", ["a\r\nb", "a\x00", "a\nb"])
async def test_folder_names_refuse_control_characters(server, name):
    async with client() as mail:
        with pytest.raises(ImapSecurityError):
            await mail.select(name)
        with pytest.raises(ImapSecurityError):
            await mail.move(1, name)


async def test_folder_name_is_quoted_in_select(server):
    async with client() as mail:
        await mail.select('He said "hi" \\ & ç')
    selects = [c for c in server.commands if c[0] == "SELECT"]
    assert selects[-1][1] == '"He said \\"hi\\" \\\\ &- &AOc-"'
    assert selects[0][1] == '"INBOX"'


# -- hostile messages --------------------------------------------------------------------------


def test_everything_from_the_mail_is_untrusted():
    msg = EmailMessage()
    msg["Subject"] = "Hi"
    msg["From"] = "Eve <eve@example.com>"
    msg["To"] = "me@example.com"
    msg["Cc"] = "x@example.com"
    msg["Message-ID"] = "<1@x>"
    msg["X-Custom"] = "value"
    msg.set_content("plain")
    msg.add_alternative("<p>html</p>", subtype="html")
    msg.add_attachment(b"data", maintype="application", subtype="pdf", filename="a.pdf")
    m = parse_message(msg.as_bytes(), 1)
    for field, source in [
        (m.subject, "mail:subject"),
        (m.from_, "mail:from"),
        (m.from_address, "mail:from"),
        (m.to[0], "mail:to"),
        (m.cc[0], "mail:cc"),
        (m.message_id, "mail:message_id"),
        (m.text, "mail:text"),
        (m.html, "mail:html"),
        (m.headers["x-custom"], "mail:header"),
        (m.attachments[0].filename, "mail:attachment_filename"),
        (m.attachments[0].content_type, "mail:attachment_type"),
    ]:
        assert isinstance(field, Untrusted) and field.source == source
    assert parse_message(msg.as_bytes(), 1, taint=False).subject.__class__ is str


def test_mail_text_is_refused_by_the_sinks():
    m = parse_message(simple("/evil", body="<script>alert(1)</script>", from_="//evil.com <e@evil.com>"), 1)
    with pytest.raises(UnsafeValueError):
        redirect(m.subject)
    with pytest.raises(UnsafeValueError):
        check_html("<h1>" + m.text + "</h1>")
    with pytest.raises(UnsafeValueError):
        check_path(m.subject)
    assert "<script>" not in str(safe.html(m.text))


def test_html_with_script_is_kept_raw_but_untrusted():
    raw = b"Subject: x\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>hi</p><script>steal()</script>"
    m = parse_message(raw, 1)
    assert "<script>" in m.html and isinstance(m.html, Untrusted)
    assert "&lt;script&gt;" in str(safe.html(m.html))
    with pytest.raises(UnsafeValueError):
        check_html(m.html)


def test_broken_headers_do_not_crash():
    raw = (
        b"Subject: =?utf-8?b?!!!not-base64?= and =?x-no-such-charset?q?caf=E9?= =?utf-8?q?bad=FF?=\r\n"
        b"From: =?bogus?= <a@b.c>\r\n"
        b"Date: not a date at all\r\n"
        b"To: , ,, <>, a@b.c\r\n"
        b"Content-Type: text/plain; charset=made-up-charset\r\n\r\n"
        b"caf\xe9 body \xff\xfe"
    )
    m = parse_message(raw, 1)
    assert isinstance(m.subject, str) and m.date is None and m.message_id is None
    assert "body" in m.text and "\x00" not in m.text
    assert m.to == ["a@b.c"]


def test_a_message_without_headers_or_body():
    m = parse_message(b"", 7)
    assert (m.subject, m.from_, m.text, m.html, m.to, m.attachments, m.date, m.message_id) == ("", "", "", "", [], [], None, None)


def test_header_control_characters_are_flattened():
    raw = b"Subject: =?utf-8?q?a=0D=0ABcc:_evil=00x?=\r\n\r\nbody"
    m = parse_message(raw, 1)
    assert "\r" not in m.subject and "\n" not in m.subject and "\x00" not in m.subject


def test_naive_dates_are_utc_and_good_dates_keep_their_zone():
    assert parse_message(b"Date: Mon, 17 Nov 2026 10:00:00 -0000\r\n\r\n", 1).date.tzinfo is timezone.utc
    assert parse_message(b"Date: Mon, 17 Nov 2026 10:00:00 -0300\r\n\r\n", 1).date.utcoffset().total_seconds() == -3 * 3600
    assert parse_message(b"Date: Mon, 99 Foo 2026 99:99:99 +0000\r\n\r\n", 1).date is None


def nested(depth):
    raw = b"Content-Type: text/plain\r\n\r\nleaf"
    for i in range(depth):
        raw = (
            f'Content-Type: multipart/mixed; boundary="b{i}"\r\n\r\n--b{i}\r\n'.encode() + raw + f"\r\n--b{i}--\r\n".encode()
        )
    return raw


def test_deeply_nested_multipart_is_refused():
    assert parse_message(nested(5), 1).text == "leaf"
    with pytest.raises(MessageRefused, match="nested"):
        parse_message(nested(30), 1)
    with pytest.raises(MessageRefused):
        parse_message(nested(5000), 1)  # beyond what the parser itself survives
    with pytest.raises(MessageRefused):
        parse_message(nested(5), 1, max_depth=2)


def test_too_many_parts_are_refused():
    parts = "".join(f"--B\r\nContent-Type: text/plain\r\n\r\np{i}\r\n" for i in range(300))
    raw = f'Content-Type: multipart/mixed; boundary="B"\r\n\r\n{parts}--B--\r\n'.encode()
    with pytest.raises(MessageRefused, match="MIME parts"):
        parse_message(raw, 1, max_parts=100)
    assert len(parse_message(raw, 1, max_parts=400).text.split("\n\n")) == 300


def test_attachment_names_are_hostile_and_cleaned(workdir):
    msg = EmailMessage()
    msg["Subject"] = "files"
    msg.set_content("see attached")
    for name in ["../../etc/passwd", "..\\..\\windows\\evil.exe", "a\x00b.txt", "/abs/path/x.png", "..", ""]:
        msg.add_attachment(b"payload", maintype="application", subtype="octet-stream", filename=name or None)
    m = parse_message(msg.as_bytes(), 1)
    assert len(m.attachments) == 6
    for att in m.attachments:
        assert isinstance(att.filename, Untrusted)
        clean = att.safe_filename
        assert type(clean) is str and clean
        assert not re.search(r"[/\\\x00]|\.\.", clean), clean
    assert m.attachments[0].safe_filename == "passwd"
    assert m.attachments[1].safe_filename == "evil.exe"
    assert m.attachments[3].safe_filename == "x.png"
    assert m.attachments[2].safe_filename.endswith("txt")
    with pytest.raises(UnsafeValueError):
        check_path(m.attachments[0].filename)


def test_attachment_save_has_the_upload_guarantees(tmp_path):
    msg = EmailMessage()
    msg.set_content("x")
    msg.add_attachment(b"payload", maintype="application", subtype="octet-stream", filename="../../evil.exe")
    att = parse_message(msg.as_bytes(), 1).attachments[0]
    assert att.read() == b"payload" and att.size == 7
    saved = att.save(tmp_path / "in")
    assert saved.parent == (tmp_path / "in").resolve() and saved.read_bytes() == b"payload" and saved.suffix == ".exe"
    named = att.save(tmp_path / "in", att.safe_filename)
    assert named.name == "evil.exe"
    with pytest.raises(FileExistsError):
        att.save(tmp_path / "in", "evil.exe")
    att.save(tmp_path / "in", "evil.exe", overwrite=True)
    with pytest.raises(ValueError):
        att.save(tmp_path / "in", "../x")
    with pytest.raises(UnsafeValueError):
        att.save(tmp_path / "in", att.filename)  # the sender's own name: Untrusted, never a path
    with pytest.raises(ValueError, match="allowed"):
        att.save(tmp_path / "in", "a.exe", extensions=[".pdf"])
    att.save(tmp_path / "in", "a.exe", extensions=["EXE"])
    with pytest.raises(UnsafeValueError):
        att.save(Untrusted(str(tmp_path), "mail:text"))
    if hasattr(__import__("os"), "symlink"):
        (tmp_path / "in" / "link.exe").symlink_to(tmp_path / "target")
        with pytest.raises(OSError):
            att.save(tmp_path / "in", "link.exe", overwrite=True)
        assert not (tmp_path / "target").exists()


def test_attached_message_is_an_attachment_not_parsed_into_the_body():
    inner = simple("inner", body=BODY_MARK)
    raw = b'Content-Type: multipart/mixed; boundary="B"\r\n\r\n--B\r\nContent-Type: text/plain\r\n\r\nouter\r\n--B\r\nContent-Type: message/rfc822\r\n\r\n' + inner + b"\r\n--B--\r\n"
    m = parse_message(raw, 1)
    assert m.text.strip() == "outer" and len(m.attachments) == 1
    assert BODY_MARK.encode() in m.attachments[0].read()


async def test_oversize_message_is_refused_before_the_body_is_downloaded(server):
    server.add(1, simple())
    server.sizes[1] = 11 * 1024 * 1024
    async with client() as mail:
        with pytest.raises(MessageRefused, match="max_message_kb"):
            await mail.fetch(1)
    assert server.fetched_bodies == []
    server.sizes[1] = 5 * 1024
    async with client(max_message_kb=1) as mail:
        with pytest.raises(MessageRefused):
            await mail.fetch(1)
    assert server.fetched_bodies == []


async def test_a_server_that_lies_about_the_size_is_still_stopped(server):
    server.add(1, b"Subject: x\r\n\r\n" + b"a" * 4096)
    server.sizes[1] = 10
    async with client(max_message_kb=1) as mail:
        with pytest.raises(MessageRefused):
            await mail.fetch(1)


# -- transport security -------------------------------------------------------------------------------


async def test_tls_is_verified_by_default(server):
    async with client() as mail:
        pass
    built = server.constructed[0]
    assert built["cls"] == "IMAP4_SSL" and built["port"] == 993 and built["timeout"] == 30
    ctx = built["ssl_context"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True
    assert mail.host == "imap.example.com"


def test_plain_text_is_refused_without_opt_in(server):
    for kw in ({"ssl": False}, {"ssl": False, "port": 143}):
        with pytest.raises(ImapSecurityError, match="plain-text"):
            client(**kw)
    with pytest.raises(ImapSecurityError, match="exclusive"):
        client(ssl=True, starttls=True)
    assert server.constructed == []


async def test_plain_text_with_opt_in_warns(server, caplog):
    caplog.set_level(logging.WARNING, logger="ushka.mail")
    async with client(ssl=False, allow_insecure=True, port=143):
        pass
    assert server.constructed[0]["cls"] == "IMAP4" and not server.starttls_called
    assert any("NOT encrypted" in r.getMessage() for r in caplog.records)
    assert PASSWORD not in caplog.text


async def test_starttls_upgrades_with_a_verifying_context_before_login(server):
    async with client(ssl=False, starttls=True, port=143):
        pass
    ctx = server.constructed[0]["starttls_context"]
    assert server.starttls_called and ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname


def test_a_weakened_ssl_context_is_refused():
    weak = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    weak.check_hostname = False
    weak.verify_mode = ssl.CERT_NONE
    with pytest.raises(ImapSecurityError, match="verify"):
        client(ssl_context=weak)
    good = ssl.create_default_context()
    assert client(ssl_context=good)


@pytest.mark.parametrize("kw", [{"user": "a\r\nb"}, {"password": "p\nq"}, {"password": "p\x00"}])
def test_credentials_with_control_characters_are_refused(kw):
    with pytest.raises(ImapSecurityError):
        client(**kw)


async def test_timeouts(server):
    async with client(timeout=7) as mail:
        server.fail_with = TimeoutError("timed out")
        with pytest.raises(ImapError, match="timed out"):
            await mail.search()
        server.fail_with = None
        assert await mail.search() == []  # it reconnected
    assert [c["timeout"] for c in server.constructed] == [7, 7]


async def test_connection_errors_are_imap_errors(server, monkeypatch):
    def boom(*a, **k):
        raise ConnectionRefusedError("no route")

    monkeypatch.setattr(imaplib, "IMAP4_SSL", boom)
    with pytest.raises(ImapError, match="connect failed"):
        async with client():
            pass


async def test_bad_login_never_repeats_the_password(server):
    with pytest.raises(ImapError) as err:
        async with client(password="wrong"):
            pass
    assert "wrong" not in str(err.value) and PASSWORD not in str(err.value)
    # the fake server echoes the password it was given in its error text
    with pytest.raises(ImapError) as err:
        async with ImapClient("h", "u", "hunter2-longer") as _:
            pass
    assert "hunter2-longer" not in str(err.value)


async def test_missing_password_is_a_clear_error(server):
    with pytest.raises(ImapError, match="USHKA_IMAP_PASSWORD"):
        async with ImapClient("h", "u", ""):
            pass


# -- the lock -------------------------------------------------------------------------------------------------


async def test_concurrent_tasks_never_interleave_commands(server):
    for i in range(1, 4):
        server.add(i, simple())
    server.delay = 0.02
    async with client() as mail:
        await asyncio.gather(*(mail.search() for _ in range(4)), mail.fetch(1), mail.mark_seen(2), mail.fetch(3))
    assert server.overlap is False


async def test_a_cancelled_task_does_not_release_the_lock_early(server):
    server.add(1, simple())
    server.delay = 0.1
    async with client() as mail:
        first = asyncio.create_task(mail.search())
        await asyncio.sleep(0.03)
        first.cancel()
        second = asyncio.create_task(mail.search())
        with pytest.raises(asyncio.CancelledError):
            await first
        assert await second == [1]
    assert server.overlap is False


# -- no secrets in logs or repr ----------------------------------------------------------------------------------


async def test_password_and_bodies_are_never_logged_or_in_a_repr(server, caplog):
    caplog.set_level(logging.DEBUG)
    server.add(1, simple("Top secret subject", body=BODY_MARK))
    async with client() as mail:
        assert PASSWORD not in repr(mail) and "s3cret" not in repr(mail.__dict__)
        msg = await mail.fetch(1)
        await mail.move(1, "Arquivo")
    for text in (caplog.text, repr(msg), repr(mail), str(mail._password)):
        assert PASSWORD not in text and "s3cret" not in text
        assert BODY_MARK not in text and "Top secret subject" not in text
    assert repr(msg) == f"Message(uid=1, size={msg.size}, attachments=0)"
    with pytest.raises(TypeError):
        import pickle

        pickle.dumps(mail._password)


# -- configuration ------------------------------------------------------------------------------------------------------


def test_from_config(workdir, monkeypatch, server):
    (workdir / "ushka.toml").write_text('[imap]\nhost = "mail.example.org"\nuser = "support@example.org"\nfolder = "Leads"\nmax_message_kb = 64\ntimeout = 5\n')
    monkeypatch.setenv("USHKA_IMAP_PASSWORD", PASSWORD)
    config = Config(workdir).load_from_file()
    mail = ImapClient.from_config(config)
    assert (mail.host, mail.port, mail.user, mail.folder, mail.timeout, mail.max_message_bytes) == ("mail.example.org", 993, "support@example.org", "Leads", 5, 65536)
    assert mail.ssl and not mail.starttls and not mail.allow_insecure and mail.taint
    assert ImapClient.from_config(config, folder="Other").folder == "Other"
    assert PASSWORD not in repr(mail)


def configure(workdir, monkeypatch, extra=""):
    (workdir / "ushka.toml").write_text(f'[imap]\nhost = "mail.example.org"\nuser = "support@example.org"\n{extra}')
    monkeypatch.setenv("USHKA_IMAP_PASSWORD", PASSWORD)


def test_no_arguments_is_from_config(workdir, monkeypatch):
    configure(workdir, monkeypatch, 'folder = "Leads"\nmax_parts = 7\n')
    a, b = ImapClient(), ImapClient.from_config()
    for mail in (a, b):
        assert (mail.host, mail.user, mail.folder, mail.max_parts, mail.port) == ("mail.example.org", "support@example.org", "Leads", 7, 993)
        assert mail.ssl and mail.taint and mail._password.reveal() == PASSWORD and PASSWORD not in repr(mail)
    assert vars(a).keys() == vars(b).keys()


def test_what_is_passed_wins_and_the_rest_comes_from_the_file(workdir, monkeypatch):
    configure(workdir, monkeypatch, "timeout = 5\n")
    mail = ImapClient("other.example.org", folder="Archive", max_message_kb=1)
    assert (mail.host, mail.user, mail.folder, mail.timeout, mail.max_message_bytes) == ("other.example.org", "support@example.org", "Archive", 5, 1024)
    assert ImapClient(password="p").user == "support@example.org"


def test_the_environment_still_changes_options_of_a_direct_client(workdir, monkeypatch):
    configure(workdir, monkeypatch)
    monkeypatch.setenv("USHKA_IMAP_FOLDER", "FromEnv")
    assert ImapClient().folder == "FromEnv"


def test_code_options_and_taint(workdir, monkeypatch):
    configure(workdir, monkeypatch)
    context = ssl.create_default_context()
    mail = ImapClient(ssl_context=context, taint=False, max_depth=3)
    assert mail._ssl_context is context and mail.taint is False and mail.max_depth == 3
    (workdir / "ushka.toml").write_text('[imap]\nhost = "h"\n[security]\ntaint = false\n')
    assert ImapClient().taint is False


def test_a_misspelt_option_is_a_type_error_with_a_suggestion(workdir, monkeypatch):
    configure(workdir, monkeypatch)
    with pytest.raises(TypeError, match="did you mean 'max_message_kb'"):
        ImapClient(max_message_kbs=5)
    with pytest.raises(TypeError, match="unexpected option 'foldr'"):
        ImapClient("h", "u", "p", foldr="X")


def test_security_checks_hold_with_values_from_the_file(workdir, monkeypatch):
    configure(workdir, monkeypatch, "ssl = false\n")
    with pytest.raises(ImapSecurityError, match="plain-text"):
        ImapClient()
    with pytest.raises(ImapSecurityError, match="exclusive"):
        ImapClient(ssl=True, starttls=True)
    with pytest.raises(ImapSecurityError, match="verify"):
        ImapClient(ssl=True, ssl_context=_lax_context())
    with pytest.raises(ImapSecurityError, match="control characters"):
        ImapClient(ssl=True, user="a\r\nb")


def _lax_context():
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def test_no_host_anywhere(workdir):
    with pytest.raises(ImapError, match="host"):
        ImapClient()


def test_from_config_without_a_host(workdir):
    with pytest.raises(ImapError, match="host"):
        ImapClient.from_config(Config(workdir).load_from_file())


def test_the_password_is_not_a_toml_setting(workdir):
    from ushka.cli.commands.check import imap_warnings

    (workdir / "ushka.toml").write_text('[imap]\nhost = "h"\npassword = "x"\n')
    config = Config(workdir).load_from_file()
    assert any("ushka.toml" in w and "USHKA_IMAP_PASSWORD" in w for w in imap_warnings(config))


def test_check_warns_about_the_connection(workdir, monkeypatch):
    from ushka.cli.commands.check import imap_warnings

    monkeypatch.setenv("USHKA_IMAP_PASSWORD", "x")
    (workdir / "ushka.toml").write_text('[imap]\nhost = "h"\n')
    assert imap_warnings(Config(workdir).load_from_file()) == []
    Config._instance = None
    Config._initialized = False
    (workdir / "ushka.toml").write_text('[imap]\nhost = "h"\nssl = false\nallow_insecure = true\n')
    assert any("STRONG WARNING" in w for w in imap_warnings(Config(workdir).load_from_file()))
    Config._instance = None
    Config._initialized = False
    (workdir / "ushka.toml").write_text('[imap]\nhost = "h"\nssl = false\n')
    assert any("refuse" in w for w in imap_warnings(Config(workdir).load_from_file()))


def test_importing_ushka_does_not_load_the_mail_client():
    code = "import sys, ushka; print('ushka.mail' in sys.modules, 'imaplib' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    assert out[0] == "False"
