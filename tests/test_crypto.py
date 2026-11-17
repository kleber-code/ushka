"""Ushka Crypto: Fernet encrypt/decrypt, key rotation, encrypted sessions, `db.Encrypted`, the CLI."""

from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

pytest.importorskip("cryptography")

from ushka import crypto
from ushka.cli import main
from ushka.crypto import (
    DecryptionError,
    decrypt,
    decrypt_bytes,
    encrypt,
    encrypt_bytes,
    generate_key,
)
from ushka.crypto import fernet as fernet_module

SECRET = "s" * 48


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("USHKA_APP_SECRET_KEY", SECRET)
    monkeypatch.delenv("USHKA_CRYPTO_KEYS", raising=False)


# -- the API ---------------------------------------------------------------------------


def test_round_trip_text_and_bytes():
    token = encrypt("olá, mundo")
    assert isinstance(token, str) and "olá" not in token
    assert decrypt(token) == "olá, mundo"
    assert type(decrypt(token)) is str  # plain str, not Untrusted
    assert decrypt_bytes(encrypt_bytes(b"\x00\xff data")) == b"\x00\xff data"


def test_each_token_is_different_but_both_decrypt():
    a, b = encrypt("same"), encrypt("same")
    assert a != b and decrypt(a) == decrypt(b) == "same"


def test_wrong_types_are_programming_errors():
    with pytest.raises(TypeError):
        encrypt(b"bytes")
    with pytest.raises(TypeError):
        encrypt_bytes("text")
    with pytest.raises(TypeError):
        decrypt(None)


def test_an_untrusted_token_decrypts():
    from ushka.guard import Untrusted

    token = encrypt("hello")
    assert decrypt(Untrusted(token, "cookie")) == "hello"


def test_ttl_expired_token_is_refused():
    key = generate_key()
    token = encrypt("x", key=key)
    time.sleep(1.1)
    with pytest.raises(DecryptionError):
        decrypt(token, key=key, ttl=0)
    assert decrypt(token, key=key, ttl=60) == "x"


def test_tampered_truncated_and_wrong_key_raise_a_generic_error():
    key = generate_key()
    token = encrypt("top secret", key=key)
    flipped = token[:-6] + ("A" if token[-6] != "A" else "B") + token[-5:]
    bad = [flipped, token[:20], token[:-4], "", "not a token", "é" * 10, token.encode()[:-3], encrypt("x", key=generate_key())]
    messages = set()
    for value in bad:
        with pytest.raises(DecryptionError) as info:
            decrypt(value, key=key)
        messages.add(str(info.value))
        assert "top secret" not in str(info.value) and key not in str(info.value)
        assert info.value.__cause__ is None and info.value.__suppress_context__
    assert len(messages) == 1  # the same message whatever went wrong


def test_decrypted_bytes_that_are_not_utf8_are_a_decryption_error_for_text():
    token = encrypt_bytes(b"\xff\xfe\xfd")
    with pytest.raises(DecryptionError):
        decrypt(token)


def test_invalid_key_is_a_clear_error_that_does_not_echo_the_key():
    with pytest.raises(ValueError) as info:
        encrypt("x", key="definitely-not-a-key")
    assert "definitely-not-a-key" not in str(info.value) and "genkey" in str(info.value)


def test_generate_key_is_a_valid_fresh_key():
    a, b = generate_key(), generate_key()
    assert a != b and len(a) == 44
    assert decrypt(encrypt("x", key=a), key=a) == "x"


# -- rotation --------------------------------------------------------------------------


def test_rotation_first_key_encrypts_all_keys_decrypt():
    k1, k2 = generate_key(), generate_key()
    old = encrypt("old data", key=k1)
    assert decrypt(old, key=[k2, k1]) == "old data"  # rotated: still readable
    new = encrypt("new data", key=[k2, k1])
    assert decrypt(new, key=k2) == "new data"  # the first key made it
    with pytest.raises(DecryptionError):
        decrypt(new, key=k1)
    with pytest.raises(DecryptionError):
        decrypt(old, key=k2)  # k1 gone: the old token is unreadable


def test_rotation_through_the_configuration(monkeypatch):
    k1, k2 = generate_key(), generate_key()
    monkeypatch.setenv("USHKA_CRYPTO_KEYS", k1)
    token = encrypt("data")
    from ushka.core.config import Config

    Config._instance = None
    Config._initialized = False
    monkeypatch.setenv("USHKA_CRYPTO_KEYS", f"{k2}, {k1}")
    assert decrypt(token) == "data"
    assert decrypt(encrypt("again"), key=k2) == "again"
    Config._instance = None
    Config._initialized = False
    monkeypatch.setenv("USHKA_CRYPTO_KEYS", k2)
    with pytest.raises(DecryptionError):
        decrypt(token)


# -- derived key -----------------------------------------------------------------------


def test_derived_key_is_stable_and_not_the_secret():
    a = crypto.derive_key(SECRET)
    assert a == crypto.derive_key(SECRET)
    assert a != SECRET and SECRET not in a
    assert a != crypto.derive_key(SECRET + "x")
    assert fernet_module.HKDF_INFO == b"ushka-fernet-v1"


def test_without_keys_the_secret_key_is_used_through_the_derived_key():
    token = encrypt("hello")
    assert decrypt(token, key=crypto.derive_key(SECRET)) == "hello"


def test_no_key_at_all_says_what_to_set(monkeypatch):
    monkeypatch.delenv("USHKA_APP_SECRET_KEY")
    with pytest.raises(RuntimeError, match="USHKA_CRYPTO_KEYS"):
        encrypt("x")


def test_crypto_keys_is_a_secret_setting_read_from_the_environment(monkeypatch):
    from ushka.core.config import Config
    from ushka.core.settings import SCHEMA

    assert SCHEMA["crypto"]["keys"].secret and SCHEMA["session"]["encrypt"].default is False
    k = generate_key()
    monkeypatch.setenv("USHKA_CRYPTO_KEYS", f"{k},{generate_key()}")
    assert Config().get("crypto_keys")[0] == k


# -- the extra is optional -------------------------------------------------------------


def test_importing_ushka_does_not_import_cryptography():
    code = "import sys, ushka, ushka.crypto; print('cryptography' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "False"


def test_without_the_extra_the_message_says_how_to_install_it(monkeypatch):
    for name in ("cryptography", "cryptography.fernet", "cryptography.hazmat.primitives",
                 "cryptography.hazmat.primitives.kdf.hkdf"):
        monkeypatch.setitem(sys.modules, name, None)
    assert crypto.is_available() is False
    for call in (lambda: encrypt("x"), lambda: decrypt("x"), generate_key, lambda: crypto.derive_key("x")):
        with pytest.raises(ImportError, match=r'pip install "ushka\[crypto\]"'):
            call()


def test_encrypted_sessions_without_the_extra_fail_when_the_app_starts(workdir, make_app, monkeypatch):
    (workdir / "ushka.toml").write_text("[session]\nencrypt = true\n")
    monkeypatch.setitem(sys.modules, "cryptography", None)
    monkeypatch.setitem(sys.modules, "cryptography.fernet", None)
    with pytest.raises(ImportError, match=r"ushka\[crypto\]"):
        make_app()


def test_encrypted_sessions_with_a_bad_key_fail_when_the_app_starts(workdir, make_app, monkeypatch):
    (workdir / "ushka.toml").write_text("[session]\nencrypt = true\n")
    monkeypatch.setenv("USHKA_CRYPTO_KEYS", "garbage")
    with pytest.raises(ValueError, match="genkey"):
        make_app()


# -- encrypted session cookie ----------------------------------------------------------


@pytest.fixture
def app(workdir, make_app):
    (workdir / "ushka.toml").write_text("[session]\nencrypt = true\n")
    app = make_app()

    @app.post("/login")
    async def login(request):
        request.session["user_id"] = 7
        request.session["name"] = "Ana Maria Secreta"
        return {"ok": True}

    @app.get("/me")
    async def me(request):
        return {"user": request.session.get("user_id"), "name": request.session.get("name")}

    return app


def cookie_of(res):
    return res["headers"]["set-cookie"].split(";", 1)[0]


async def test_encrypted_session_cookie_hides_the_content_and_reads_back(app, call):
    res = await call(app, "POST", "/login")
    cookie = cookie_of(res)
    value = cookie.split("=", 1)[1]
    assert "Ana" not in cookie and "Secreta" not in cookie and "user_id" not in cookie
    import base64

    assert "Secreta" not in base64.urlsafe_b64decode(value).decode("latin-1")
    assert decrypt(value, key=crypto.derive_key(SECRET)) == '{"user_id":7,"name":"Ana Maria Secreta"}'
    back = await call(app, "GET", "/me", headers={"cookie": cookie})
    assert json.loads(back["body"]) == {"user": 7, "name": "Ana Maria Secreta"}


async def test_tampered_old_or_foreign_cookies_are_an_empty_session_not_an_error(app, call):
    cookie = cookie_of(await call(app, "POST", "/login"))
    name, value = cookie.split("=", 1)
    bad = [
        f"{name}={value[:-8]}AAAAAAAA",
        f"{name}={value[:30]}",
        f"{name}=garbage",
        f"{name}=a.b.c",
        f"{name}={encrypt(json.dumps({'user_id': 1}), key=generate_key())}",  # right shape, other key
        f"{name}={encrypt('[1, 2]')}",  # ours, but not an object
        f"{name}={encrypt('not json')}",
    ]
    for header in bad:
        res = await call(app, "GET", "/me", headers={"cookie": header})
        assert res["status"] == 200, header
        assert json.loads(res["body"]) == {"user": None, "name": None}


def test_a_session_cookie_older_than_max_age_is_empty():
    from ushka.sessions.session import Session

    keys = [generate_key()]
    old = Session("k" * 40, max_age=1, encrypt_keys=keys)
    old["a"] = 1
    value = old._encode()
    assert Session("k" * 40, value, max_age=60, encrypt_keys=keys) == {"a": 1}
    time.sleep(2.1)  # Fernet counts whole seconds
    assert Session("k" * 40, value, max_age=1, encrypt_keys=keys) == {}


async def test_old_signed_cookies_do_not_survive_turning_encryption_on(workdir, make_app, call):
    from ushka.sessions.session import Session

    signed = Session(SECRET)
    signed["user_id"] = 7
    (workdir / "ushka.toml").write_text("[session]\nencrypt = true\n")
    app = make_app()

    @app.get("/me")
    async def me(request):
        return {"user": request.session.get("user_id")}

    res = await call(app, "GET", "/me", headers={"cookie": f"_ushka_session={signed._encode()}"})
    assert json.loads(res["body"]) == {"user": None}


async def test_session_encryption_follows_key_rotation(workdir, make_app, call, monkeypatch):
    k1, k2 = generate_key(), generate_key()
    (workdir / "ushka.toml").write_text("[session]\nencrypt = true\n")
    monkeypatch.setenv("USHKA_CRYPTO_KEYS", k1)
    first = make_app()

    @first.post("/login")
    async def login(request):
        request.session["user_id"] = 7
        return {}

    cookie = cookie_of(await call(first, "POST", "/login"))
    from ushka.core.app import Ushka  # noqa: F401
    from ushka.core.config import Config

    Config._instance = None
    Config._initialized = False
    monkeypatch.setenv("USHKA_CRYPTO_KEYS", f"{k2},{k1}")
    second = make_app()

    @second.get("/me")
    async def me(request):
        return {"user": request.session.get("user_id")}

    assert json.loads((await call(second, "GET", "/me", headers={"cookie": cookie}))["body"]) == {"user": 7}


async def test_forged_session_cookies_are_encrypted_too(workdir, make_app, call):
    from ushka.sessions.forge import forge_session_cookie

    (workdir / "ushka.toml").write_text("[session]\nencrypt = true\n")
    app = make_app()

    @app.get("/me")
    async def me(request):
        return {"user": request.session.get("uid")}

    cookie = forge_session_cookie(app, {"uid": 5})
    assert "uid" not in cookie
    assert json.loads((await call(app, "GET", "/me", headers={"cookie": cookie}))["body"]) == {"user": 5}


async def test_default_sessions_are_still_signed_not_encrypted(workdir, make_app, call):
    app = make_app()

    @app.post("/login")
    async def login(request):
        request.session["name"] = "Ana"
        return {}

    cookie = cookie_of(await call(app, "POST", "/login"))
    assert cookie.count(".") == 3 or cookie.split("=", 1)[1].count(".") == 2


# -- db.Encrypted ----------------------------------------------------------------------


@pytest.fixture
async def sqlite(tmp_path):
    from ushka.orm import db

    old = db._url
    db.configure(f"sqlite:///{tmp_path / 'enc.db'}")
    yield db
    await db.engine.dispose()
    db._url = old
    db._engine = db._session_factory = None


async def test_encrypted_column_is_transparent_but_not_plain_in_the_database(sqlite):
    db = sqlite

    class Patient(db.Model):
        __tablename__ = "enc_patients"
        name = db.String(length=40)
        diagnosis = db.Encrypted()
        note = db.Encrypted(nullable=True)
        tag = db.Encrypted(default="none")

    async with db.engine.begin() as conn:
        await conn.run_sync(lambda c: db.metadata.create_all(c, tables=[Patient.__table__]))
    created = await Patient.create(name="ana", diagnosis="segredo médico")
    again = await Patient.get(created.id)
    assert again.diagnosis == "segredo médico" and again.note is None and again.tag == "none"

    async with db.engine.connect() as conn:
        row = (await conn.exec_driver_sql("select diagnosis, note, tag from enc_patients")).one()
    assert row[0] != "segredo médico" and "segredo" not in row[0]
    assert row[1] is None  # NULL stays NULL
    assert row[2] != "none" and decrypt(row[2]) == "none"
    assert decrypt(row[0]) == "segredo médico"

    again.diagnosis = "novo"
    await again.save()
    assert (await Patient.get(created.id)).diagnosis == "novo"
    from sqlalchemy.exc import StatementError

    with pytest.raises(StatementError, match="stores str"):
        await Patient.create(name="x", diagnosis=123)


async def test_encrypted_column_survives_key_rotation_and_fails_without_the_old_key(sqlite, monkeypatch):
    from ushka.core.config import Config

    db = sqlite

    class Card(db.Model):
        __tablename__ = "enc_cards"
        number = db.Encrypted()

    async with db.engine.begin() as conn:
        await conn.run_sync(lambda c: db.metadata.create_all(c, tables=[Card.__table__]))
    k1, k2 = generate_key(), generate_key()
    monkeypatch.setenv("USHKA_CRYPTO_KEYS", k1)
    card = await Card.create(number="4111")
    for keys, ok in ((f"{k2},{k1}", True), (k2, False)):
        Config._instance = None
        Config._initialized = False
        monkeypatch.setenv("USHKA_CRYPTO_KEYS", keys)
        db.session_factory  # noqa: B018 - keep the engine; only the keys change
        if ok:
            assert (await Card.get(card.id)).number == "4111"
        else:
            with pytest.raises(DecryptionError):
                await Card.get(card.id)


# -- CLI -------------------------------------------------------------------------------


def test_cli_genkey_prints_only_a_valid_key(capsys):
    main(["crypto", "genkey"])
    out = capsys.readouterr().out
    key = out.strip()
    assert out == key + "\n" and len(key) == 44
    assert decrypt(encrypt("x", key=key), key=key) == "x"


def test_cli_genkey_without_the_extra_fails_with_the_hint(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "cryptography", None)
    monkeypatch.setitem(sys.modules, "cryptography.fernet", None)
    with pytest.raises(SystemExit) as info:
        main(["crypto", "genkey"])
    captured = capsys.readouterr()
    assert info.value.code == 1 and captured.out == "" and "ushka[crypto]" in captured.err


def test_cli_help_lists_crypto():
    def run(*args):
        code = "from ushka.cli import main; main()"
        return subprocess.run([sys.executable, "-c", code, *args], capture_output=True, text=True, check=True).stdout

    assert "crypto" in run("--help")
    assert "genkey" in run("crypto", "--help")


# -- ushka check -----------------------------------------------------------------------


def test_check_production_warns_about_the_derived_key(workdir, monkeypatch, capsys):
    from ushka.cli.commands.check import check

    (workdir / "ushka.toml").write_text("[session]\nencrypt = true\n")
    monkeypatch.setenv("USHKA_APP_DEBUG", "false")
    check(production=True)
    assert "ushka crypto genkey" in capsys.readouterr().out
    monkeypatch.setenv("USHKA_CRYPTO_KEYS", generate_key())
    check(production=True)
    assert "ushka crypto genkey" not in capsys.readouterr().out


def test_check_finds_use_of_the_column_in_the_code(workdir, monkeypatch, capsys):
    from ushka.cli.commands.check import check

    (workdir / "models.py").write_text("from ushka.orm import db\nclass A(db.Model):\n    s = db.Encrypted()\n")
    check(production=True)
    assert "ushka crypto genkey" in capsys.readouterr().out


def test_check_is_quiet_when_nothing_encrypts(workdir, capsys):
    from ushka.cli.commands.check import check

    check(production=True)
    assert "ushka crypto genkey" not in capsys.readouterr().out


def test_check_refuses_keys_in_ushka_toml(workdir, capsys):
    from ushka.cli.commands.check import check

    (workdir / "ushka.toml").write_text(f'[crypto]\nkeys = ["{generate_key()}"]\n')
    assert check() >= 1
    assert "USHKA_CRYPTO_KEYS" in capsys.readouterr().err


def test_keep_derived_reads_what_the_derived_key_wrote(monkeypatch):
    from ushka.core.config import Config

    monkeypatch.setenv("USHKA_APP_SECRET_KEY", SECRET)
    old = encrypt("before the dedicated key")  # no keys: the derived key
    dedicated = generate_key()
    for keep, readable in (("false", False), ("true", True)):
        Config._instance = None
        Config._initialized = False
        monkeypatch.setenv("USHKA_CRYPTO_KEYS", dedicated)
        monkeypatch.setenv("USHKA_CRYPTO_KEEP_DERIVED", keep)
        if readable:
            assert decrypt(old) == "before the dedicated key"
            assert decrypt(encrypt("new"), key=dedicated) == "new"  # new data uses the dedicated key
        else:
            with pytest.raises(DecryptionError):
                decrypt(old)
