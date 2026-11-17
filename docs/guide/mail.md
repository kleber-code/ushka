# Reading e-mail (IMAP)

```python
from ushka.mail import ImapClient

async with ImapClient() as mail:                 # host, user and password from ushka.toml and .env
    async for msg in mail.unseen():
        ...
        await mail.mark_seen(msg.uid)
```

`ImapClient` reads an app's inbox (support, leads, receipts) with no dependency: the
standard library's `imaplib`, run outside the event loop. One rule matters: **everything
in an e-mail is written by a stranger**, so everything in it is `Untrusted`.
It is not loaded by `import ushka`; import it where you use it.

## Configuration

```toml
# ushka.toml
[imap]
host = "imap.example.com"
user = "support@example.com"
```

```bash
# .env: the password never goes in ushka.toml
USHKA_IMAP_PASSWORD=...
```

`ImapClient()` reads `[imap]`; what you pass wins, and the rest still comes from there:
`ImapClient(folder="Leads")`, `ImapClient("imap.other.com", "me@other.com", password)`.
`ImapClient.from_config()` is the same call. With no `host`, it comes from the user's address when that is at a
well-known provider (`you@gmail.com` is `imap.gmail.com`; also outlook, icloud, yahoo, fastmail, zoho), and
`host = "gmail"` names one too (`PROVIDER_HOSTS`). Any other domain needs its host: Ushka does not guess where
to send a password. A misspelt option is a `TypeError`
that suggests the right name. Options are the keys of the [`[imap]` table](configuration.md)
(`port`, `ssl`, `starttls`, `allow_insecure`, `folder`, `timeout`, `max_message_kb`,
`max_parts`) and three that exist only in code: `ssl_context`, `taint` and `max_depth`.

`ushka check` reports a host without a password, a password written in `ushka.toml`, and a
connection that is not encrypted. Gmail and Outlook do not accept the account password
over IMAP: use an app password. OAuth (XOAUTH2) is not supported.

## A routine that turns unread mail into leads

```python
# services/inbox.py
import logging

from ushka.mail import ImapClient

log = logging.getLogger("inbox")


async def collect_leads(save_lead) -> int:
    count = 0

    def refused(uid, error):          # too big, too many parts: skip it, keep going
        log.warning("message %s refused: %s", uid, error)

    async with ImapClient() as mail:
        async for msg in mail.unseen(limit=50, on_error=refused, mark_refused=True):
            await save_lead(
                sender=msg.from_address,   # Untrusted: the ORM stores it as data
                subject=msg.subject,
                body=msg.text,
            )
            await mail.mark_seen(msg.uid)  # unseen() leaves the message unread
            count += 1
    return count
```

Run it from a scheduler, a script or a route behind your own login.
`fetch` and `unseen` never mark a message as read; you do it after you have
handled it, so a crash does not lose mail.

## The client

```python
async with ImapClient() as mail:
    await mail.folders()                              # ["INBOX", "Faturas ção", ...]
    await mail.select("Faturas ção")                  # returns the message count
    uids = await mail.search(unseen=True, from_="billing@example.com", since=date(2026, 11, 1))
    msg = await mail.fetch(uids[-1])
    await mail.mark_seen(msg.uid)                     # and mark_unseen
    await mail.move(msg.uid, "Arquivo")               # copy, then delete here
    await mail.delete(msg.uid)                        # flag \Deleted and UID EXPUNGE
```

* Everything uses **UIDs**, which survive deletions, never sequence numbers.
* One connection, one command at a time: a lock serialises tasks, because
  `imaplib` is not thread-safe. After a dropped connection the next call
  reconnects and selects the same folder again.
* `search` takes keyword arguments and builds the command for you:
  flags (`unseen=True`, `seen`, `flagged`, `answered`, `deleted`, `draft`),
  text (`from_`, `to`, `cc`, `bcc`, `subject`, `body`, `text`), dates (`since`,
  `before`, `on`, `sent_since`, `sent_before`, `sent_on`; a `date` or
  `datetime`), sizes (`larger`, `smaller`), `header=("X-Name", "value")`,
  `keyword=` and `uid=`. `limit=n` keeps the newest `n` UIDs.
* Folder names may have accents and spaces; they are sent in the modified UTF-7
  that IMAP requires (`ushka.mail.encode_folder` and `decode_folder`).
* `delete` expunges only that message. On a server without `UIDPLUS` it would
  have to expunge everything flagged `\Deleted`, so it refuses when another
  message is flagged.

### Search values cannot inject commands

A value you pass to `search` is a quoted string with `\` and `"` escaped, so
`subject='x" OR ALL'` searches for that text. A CR, LF, NUL or any other control
character is refused with `ImapSecurityError`, which is what stops
`"x\r\nA2 DELETE INBOX"` from becoming a second command. UIDs, flag names and
header names are checked against a strict pattern. Non-ASCII text is sent as
UTF-8 with `CHARSET UTF-8`.

## The message

`fetch` returns a `Message`:

| Field | Type | Notes |
| --- | --- | --- |
| `uid` | `int` | |
| `message_id` | `Untrusted` or `None` | A message without one is fine. |
| `subject`, `from_` | `Untrusted` | RFC 2047 words decoded; invalid charsets become replacement characters. |
| `to`, `cc` | `list[Untrusted]` | One entry per address. |
| `date` | `datetime` or `None` | Timezone-aware; `None` when missing or invalid. |
| `text`, `html` | `Untrusted` | The plain and the HTML body, raw. |
| `attachments` | `list[Attachment]` | |
| `headers` | `dict[str, Untrusted]` | Lower-case names, first value of each. |

`msg.from_address` is only the address. It is the sender's claim: the `From`
header is trivially forged, so do not treat it as identity (check SPF, DKIM and
DMARC results in `headers["authentication-results"]` if it matters).

The `source` of each text says where it came from (`"mail:subject"`,
`"mail:text"`, `"mail:attachment_filename"`...), and appears in the
[guard](guard.md) error.

## Using what the e-mail says

Because the text is `Untrusted`, the dangerous uses are refused:

```python
redirect(msg.subject)              # UnsafeValueError USHKA-G003
open(msg.attachments[0].filename)  # refused: a file-system path (use save())
```

and the safe ones are short:

```python
from ushka import safe

# show it: autoescaped by the template, no |safe
await render(request, "ticket.html", {"msg": msg})

# in code that builds HTML: escape it
title = safe.html(msg.subject)

# an ORM or db.text() parameter is data, not SQL
await Lead.create(subject=msg.subject, body=msg.text)
```

**HTML mail is hostile.** `msg.html` can hold `<script>`, tracking pixels, forms
and links that look like your bank. Never print it with `|safe`. Either show
`msg.text`, show `safe.html(msg.html)` (which shows the markup as text), or run
a sanitiser you trust on it and then mark the result with `safe.trust(...)` and
a reason. Do not render it in your own origin without one. Links in e-mail are
`Untrusted` too: use `safe.url(value, allow=["https://"])` before you link them.

## Attachments

```python
for att in msg.attachments:
    att.filename        # Untrusted: what the sender called it
    att.safe_filename   # plain str: base name only, no /, \, .. or NUL
    att.content_type    # Untrusted: a claim, not proof
    att.size, att.read()
    att.save("inbox-files", extensions=[".pdf", ".png"])
```

`save` works exactly like [`UploadFile.save`](uploads.md): a random name unless
you pass a plain `name=` (use `att.safe_filename`), no overwriting unless
`overwrite=True`, no following a symlink, and an optional allow-list of
extensions (a refusal raises `UploadRejected`). Check the magic bytes
(`att.read()[:8]`) when the type matters, and never open a received file from a
privileged process. A forwarded message (`message/rfc822`) is an attachment, not
parsed into the body.

## Limits

| Limit | Default | When it is exceeded |
| --- | --- | --- |
| `max_message_kb` | 10240 | Refused from `RFC822.SIZE` before the body is downloaded. |
| `max_parts` | 100 | `MessageRefused` (a bomb of MIME parts). |
| MIME depth | 10 | `MessageRefused` (`ImapClient(max_depth=...)`). |
| `timeout` | 30 | Seconds to connect and to wait on each read; `ImapError`, and the next call reconnects. |

`MessageRefused` and `MessageNotFound` are `ImapError`s about one message; pass
`on_error=` to `unseen()` to skip them.

## Security summary

* **TLS is mandatory.** `ssl = true` (port 993) verifies the certificate and the
  host name with the default context, and `ImapClient(ssl_context=...)` is
  refused if it would not. `ssl = false` with `starttls = true` upgrades before
  the login. Plain text needs `allow_insecure = true`, logs a warning every time
  and `ushka check` flags it: for a local test server only.
* The password is read from `USHKA_IMAP_PASSWORD`, is held in an object whose
  `repr` is `'***'`, and is never in a log line, an error message or `repr`. Nor
  are message bodies or subjects: `repr(msg)` is `Message(uid=5, size=1042, attachments=1)`.
* Every text in the message is `Untrusted`. With `[security] taint = false` they
  are plain strings, as everywhere else.

## Not included

OAuth2 (XOAUTH2), IDLE (push) and sending mail. For new mail, poll with
`unseen()` from a scheduler. There is no way to send a raw IMAP command.
