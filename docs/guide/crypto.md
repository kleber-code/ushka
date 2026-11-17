# Encryption

Ushka encrypts with **Fernet** (AES-128-CBC plus HMAC-SHA256, with a timestamp):
authenticated encryption, so a changed token is refused instead of decrypting to
garbage. The Python standard library has no AES, so the cipher comes from the
audited [`cryptography`](https://cryptography.io) package, as an optional extra.
Ushka implements no cipher of its own.

```bash
pip install "ushka[crypto]"
```

Without the extra, everything else works as before. `import ushka` never imports
`cryptography`; using encryption without it raises an `ImportError` that says how
to install it.

## Encrypt and decrypt

```python
from ushka.crypto import DecryptionError, decrypt, encrypt

token = encrypt("4111 1111 1111 1111")      # urlsafe text, safe in a cookie or a column
card = decrypt(token)                       # "4111 1111 1111 1111"
card = decrypt(token, ttl=3600)             # refused if it is older than an hour

try:
    decrypt(value_from_the_client)
except DecryptionError:
    ...                                     # changed, truncated, expired or another key
```

| Function | Does |
| --- | --- |
| `encrypt(data, *, key=None) -> str` | Text to a Fernet token. |
| `decrypt(token, *, key=None, ttl=None) -> str` | The text back, as a plain `str`. |
| `encrypt_bytes(data, *, key=None) -> str` | Bytes to a token. |
| `decrypt_bytes(token, *, key=None, ttl=None) -> bytes` | The bytes back. |
| `generate_key() -> str` | A new random key. |
| `derive_key(secret_key) -> str` | The key Ushka derives from `[app] secret_key` (see below). |
| `DecryptionError` | Raised for any token that does not decrypt. |

`DecryptionError` has the same generic message for a changed token, a wrong key
and an expired one: it never contains the data and never says which it was, so it
tells an attacker nothing. Tokens are not deterministic (the same text gives a
different token each time), so you cannot compare or search by token.

`key=` is for tests and special cases: one key, or a list (the first encrypts, all
decrypt). Left out, the keys of the app are used.

### Decrypted values are plain `str`

A token that decrypts was written by your application: nobody else holds the key.
That is why `decrypt()` returns an ordinary `str`, not an
[`Untrusted`](guard.md) one. The taint of the original text does not survive
storage. If what you encrypted was request data, and the decrypted text will reach
a sink (HTML, SQL, a redirect), mark it again:
`Untrusted(decrypt(token), "database")`.

## Keys

```bash
ushka crypto genkey      # prints one key, and nothing else
```

```bash
# .env
USHKA_CRYPTO_KEYS=Uc5q...key-one...=,gB8k...key-two...=
```

`[crypto] keys` is a list, **newest first**. It is a secret, so it comes from the
environment or `.env` and never from `ushka.toml` (`ushka check` flags it there).

### No keys set: derived from the secret key

To work with no setup, when `keys` is empty Ushka derives a key from
`[app] secret_key` with HKDF-SHA256 (fixed `info` of `b"ushka-fernet-v1"`, no salt,
32 bytes). The key is stable, so data survives restarts, and it is not the secret
itself. The cost: rotating the secret key (which you should be able to do) would
make everything encrypted unreadable. `ushka check --production` warns about it
when the app encrypts something, and suggests a dedicated key. Move to one without
losing data: put the new key in `keys` and turn on `keep_derived`, which keeps the derived key as the last
one, for decrypting only:

```toml
[crypto]
keep_derived = true               # keys (USHKA_CRYPTO_KEYS) holds the new key
```

`derive_key(secret_key)` still prints the derived key, if you prefer to list it in `USHKA_CRYPTO_KEYS`.

### Rotation

The first key encrypts, every key decrypts (`MultiFernet`). To rotate:

1. `ushka crypto genkey`, and put the new key **first**: `USHKA_CRYPTO_KEYS=new,old`.
2. Deploy. New data uses `new`; old data still reads with `old`.
3. Drop `old` once nothing encrypted with it is left (rows rewritten, sessions
   expired). Data that only `old` could read now raises `DecryptionError`.

## Encrypted session cookies

A cookie session is signed, and the client can read it. To make it unreadable too:

```toml
# ushka.toml
[session]
encrypt = true
```

The cookie then holds a Fernet token instead of the signed payload: the browser
can neither read nor change it. Your routes do not change. Notes:

- It lasts `[session] max_age`, checked from the token's own timestamp.
- An old, changed or foreign cookie becomes an empty session, never a 500. Turning
  `encrypt` on or off therefore logs everyone out once.
- The 4 KB limit still applies, and the encrypted cookie is about a third bigger.
- A copied cookie still works until it expires: for a logout that really ends the
  session use [server-side sessions](sessions.md#server-side-sessions), which are
  unchanged (the cookie there is only a random id).
- With `encrypt = true` and no extra installed, or no usable key, the app refuses
  to start, rather than failing on the first request.

## Encrypted columns

```python
from ushka.orm import db

class Patient(db.Model):
    name = db.String(length=80)
    diagnosis = db.Encrypted()                 # a str, stored as a Fernet token
    notes = db.Encrypted(nullable=True)
```

You assign and read a plain `str`; the database holds the token (in a `Text`
column), so a leaked dump or backup shows nothing. `nullable` and `default` work
like in the other helpers (`NULL` stays `NULL`).

- **You cannot filter or sort by the value.** Encryption is not deterministic, so
  `Patient.diagnosis == "flu"` never matches. Keep a separate searchable column
  (a category, a hash with a secret) for lookups.
- **Rotation works**, because every key in `[crypto] keys` decrypts. Rewrite rows
  (read, then save) to move them to the newest key before dropping the old one.
- A row that cannot be decrypted (the key is gone) raises `DecryptionError` when it
  is read.
- Only `str` is stored. Convert other values (`json.dumps`, `str`) first.

## Not covered

Encryption protects data at rest and in the cookie. It does not hide data from your
own application, and it is not a password store: for passwords use a slow hash such
as `hashlib.scrypt`.
