"""Login with OAuth 2.0 / OpenID Connect, against a fake provider served by the standard library."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from ushka import Depends
from ushka.auth import (
    GitHub,
    Google,
    current_user,
    login_required,
    login_required_for,
    login_url,
    logout,
    problems,
)
from ushka.testing import TestClient

KEY = "k" * 48
BASE = "https://app.example.test"
CLIENT_SECRET = "s3cr3t-client-secret-value"
ACCESS_TOKEN = "access-token-value-123"
ENV = {"USHKA_APP_SECRET_KEY": KEY, "USHKA_OAUTH_GOOGLE_CLIENT_SECRET": CLIENT_SECRET, "USHKA_OAUTH_GITHUB_CLIENT_SECRET": CLIENT_SECRET}


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


class Fake:
    """A provider on 127.0.0.1: token endpoint (with PKCE), Google userinfo and GitHub user + e-mails."""

    def __init__(self):
        self.codes: dict[str, dict] = {}
        self.requests: list[dict] = []
        self.mode = "ok"
        self.google = {"sub": "g-1", "email": "Ana@Example.com", "email_verified": True, "name": "Ana", "picture": "https://img.example/a.png", "hd": "example.com"}
        self.github_user = {"id": 4242, "login": "ana", "name": "Ana G", "avatar_url": "https://img.example/gh.png"}
        self.github_emails = [{"email": "other@example.com", "primary": False, "verified": True}, {"email": "ana@example.com", "primary": True, "verified": True}]
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, payload, extra=None):
                body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()).items()}
                fake.requests.append({"path": self.path, "form": form})
                if fake.mode == "token_error":
                    return self._send(400, {"error": "invalid_grant", "error_description": "PROVIDER-SECRET-TEXT"})
                if fake.mode == "token_200_error":
                    return self._send(200, {"error": "bad_verification_code"})
                if fake.mode == "huge":
                    return self._send(200, b'{"access_token":"' + b"a" * (2 * 1024 * 1024) + b'"}')
                if fake.mode == "slow":
                    time.sleep(1.5)
                if fake.mode == "redirect":
                    return self._send(302, b"", {"Location": "https://evil.example/steal"})
                if fake.mode == "garbage":
                    return self._send(200, b"<html>not json</html>")
                grant = fake.codes.pop(form.get("code", ""), None)  # a code works once
                ok = (
                    grant
                    and form.get("client_id") == grant["client_id"]
                    and form.get("client_secret") == CLIENT_SECRET
                    and form.get("redirect_uri") == grant["redirect_uri"]
                    and form.get("grant_type") == "authorization_code"
                    and base64.urlsafe_b64encode(hashlib.sha256(form.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode() == grant["challenge"]
                )
                if not ok:
                    return self._send(400, {"error": "invalid_grant"})
                token = {"access_token": ACCESS_TOKEN, "token_type": "Bearer"}
                if grant["nonce"]:
                    claims = {"iss": "https://accounts.google.com", "aud": grant["client_id"], "sub": fake.google["sub"], "exp": time.time() + 600, "nonce": grant["nonce"]}
                    if fake.mode == "wrong_nonce":
                        claims["nonce"] = "someone-elses-nonce"
                    token["id_token"] = f"{b64({'alg': 'RS256'})}.{b64(claims)}.sig"
                self._send(200, token)

            def do_GET(self):
                fake.requests.append({"path": self.path, "auth": self.headers.get("Authorization")})
                if self.headers.get("Authorization") != f"Bearer {ACCESS_TOKEN}":
                    return self._send(401, {"error": "bad token"})
                if self.path == "/userinfo":
                    return self._send(200, fake.google)
                if self.path == "/user":
                    return self._send(200, fake.github_user)
                if self.path == "/user/emails":
                    return self._send(200, fake.github_emails)
                self._send(404, {})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def authorize(self, location: str, *, error: str | None = None) -> str:
        """What the provider does after the browser follows `location`: the callback URL to open."""
        parts = urlsplit(location)
        q = {k: v[0] for k, v in parse_qs(parts.query).items()}
        assert q["response_type"] == "code" and q["code_challenge_method"] == "S256"
        redirect = urlsplit(q["redirect_uri"])
        callback = redirect.path
        if error:
            return f"{callback}?error={error}&state={quote(q['state'])}"
        code = f"code-{len(self.codes)}-{q['state'][:6]}"
        self.codes[code] = {"client_id": q["client_id"], "redirect_uri": q["redirect_uri"], "challenge": q["code_challenge"], "nonce": q.get("nonce", "")}
        return f"{callback}?code={code}&state={quote(q['state'])}"


@pytest.fixture
def fake(monkeypatch):
    server = Fake()
    monkeypatch.setattr(Google, "authorize_url", server.url + "/authorize")
    monkeypatch.setattr(Google, "token_url", server.url + "/token")
    monkeypatch.setattr(Google, "userinfo_url", server.url + "/userinfo")
    monkeypatch.setattr(GitHub, "authorize_url", server.url + "/authorize")
    monkeypatch.setattr(GitHub, "token_url", server.url + "/token")
    monkeypatch.setattr(GitHub, "userinfo_url", server.url + "/user")
    monkeypatch.setattr(GitHub, "emails_url", server.url + "/user/emails")
    for cls in (Google, GitHub):
        monkeypatch.setattr(cls, "allow_http", True)
        monkeypatch.setattr(cls, "timeout", 0.5)
    yield server
    server.close()


TOML = f'''
[app]
auto_discover = false
[oauth]
google_client_id = "google-id"
github_client_id = "github-id"
redirect_base = "{BASE}"
'''


@pytest.fixture
def build(workdir, make_app, monkeypatch, fake):
    def _build(toml: str = TOML, env: dict | None = None, routes: bool = True):
        for k, v in {**ENV, **(env or {})}.items():
            monkeypatch.setenv(k, v)
        (workdir / "ushka.toml").write_text(toml)
        app = make_app()
        if routes:
            add_routes(app)
        return app

    return _build


LOGIN = Depends(login_required)
LOGIN_GITHUB = Depends(login_required_for("github"))


def add_routes(app):
    @app.get("/account")
    async def account(user=LOGIN):
        return {"email": user["email"]}

    @app.get("/gh-only")
    async def gh_only(user=LOGIN_GITHUB):
        return {"email": user["email"]}

    @app.get("/me")
    async def me(request):
        return {"user": current_user(request), "session": dict(request.session)}

    @app.get("/bye")
    async def bye(request):
        logout(request)
        return {"ok": True}


async def start(client, fake, provider="google", next_=None):
    url = f"/auth/{provider}/login" + (f"?next={quote(next_)}" if next_ is not None else "")
    res = await client.get(url)
    assert res.status_code == 302, res.text
    return res.headers["location"]


async def login(client, fake, provider="google", next_=None):
    """Runs the whole flow; returns the response of the callback."""
    location = await start(client, fake, provider, next_)
    return await client.get(fake.authorize(location))


def error_of(res):
    assert res.status_code == 302
    parts = urlsplit(res.headers["location"])
    return parts.path, parse_qs(parts.query).get("login_error", [None])[0]


# -- the happy paths ------------------------------------------------------------------


async def test_google_login_end_to_end(build, fake):
    app = build()
    async with TestClient(app) as client:
        location = await start(client, fake)
        q = parse_qs(urlsplit(location).query)
        assert location.startswith(fake.url + "/authorize?")
        assert q["client_id"] == ["google-id"]
        assert q["redirect_uri"] == [f"{BASE}/auth/google/callback"]
        assert q["scope"] == ["openid email profile"]
        assert q["code_challenge_method"] == ["S256"] and q["nonce"] and q["state"]
        assert "client_secret" not in location and CLIENT_SECRET not in location

        res = await client.get(fake.authorize(location))
        assert res.status_code == 302 and res.headers["location"] == "/"
        user = (await client.get("/me")).json()["user"]
        assert user == {"provider": "google", "sub": "g-1", "email": "ana@example.com", "name": "Ana", "picture": "https://img.example/a.png"}
        token_request = next(r for r in fake.requests if r["path"] == "/token")
        assert token_request["form"]["client_secret"] == CLIENT_SECRET  # server to server only
        assert any(r.get("auth") == f"Bearer {ACCESS_TOKEN}" and r["path"] == "/userinfo" for r in fake.requests)


async def test_github_login_uses_the_primary_verified_email(build, fake):
    app = build()
    async with TestClient(app) as client:
        res = await login(client, fake, "github")
        assert res.status_code == 302 and res.headers["location"] == "/"
        user = (await client.get("/me")).json()["user"]
        assert user == {"provider": "github", "sub": "4242", "email": "ana@example.com", "name": "Ana G", "picture": "https://img.example/gh.png"}


async def test_only_the_minimal_profile_is_kept_in_the_session(build, fake):
    fake.google["phone"] = "+55 11 99999"
    fake.google["locale"] = "pt-BR"
    app = build()
    async with TestClient(app) as client:
        await login(client, fake)
        session = (await client.get("/me")).json()["session"]
        assert set(session) == {"user"}
        assert set(session["user"]) == {"provider", "sub", "email", "name", "picture"}
        assert ACCESS_TOKEN not in json.dumps(session)


async def test_next_is_kept_and_followed(build, fake):
    app = build()
    async with TestClient(app) as client:
        res = await login(client, fake, next_="/account?tab=1")
        assert res.headers["location"] == "/account?tab=1"


async def test_the_session_key_and_after_login_are_configurable(build, fake):
    app = build(TOML + 'session_key = "who"\nafter_login = "/home"\n')
    async with TestClient(app) as client:
        res = await login(client, fake)
        assert res.headers["location"] == "/home"
        assert set((await client.get("/me")).json()["session"]) == {"who"}


async def test_login_prefix_is_configurable(build, fake):
    app = build(TOML + 'login_prefix = "/signin"\n')
    async with TestClient(app) as client:
        assert (await client.get("/auth/google/login")).status_code == 404
        location = (await client.get("/signin/google/login")).headers["location"]
        assert f"{BASE}/signin/google/callback" in location.replace("%3A", ":").replace("%2F", "/")
        assert login_url("google", config=app.config) == "/signin/google/login"


# -- state, PKCE, nonce ---------------------------------------------------------------


async def test_wrong_missing_and_repeated_state_are_refused(build, fake):
    app = build()
    async with TestClient(app) as client:
        location = await start(client, fake)
        good = fake.authorize(location)
        wrong = good.replace("state=", "state=x")
        assert error_of(await client.get(wrong)) == ("/", "state")
        # the failed attempt used up the flow: even the right state is now refused
        assert error_of(await client.get(good)) == ("/", "state")
        assert (await client.get("/me")).json()["user"] is None

        location = await start(client, fake)
        no_state = fake.authorize(location).split("&state=")[0]
        assert error_of(await client.get(no_state)) == ("/", "state")

    async with TestClient(app) as client:  # no flow at all (callback opened directly)
        assert error_of(await client.get("/auth/google/callback?code=x&state=y")) == ("/", "state")


async def test_a_replayed_callback_is_refused(build, fake):
    app = build()
    async with TestClient(app) as client:
        location = await start(client, fake)
        callback = fake.authorize(location)
        assert (await client.get(callback)).headers["location"] == "/"
        await client.get("/bye")
        assert error_of(await client.get(callback)) == ("/", "state")
        assert (await client.get("/me")).json()["user"] is None


async def test_state_of_another_session_is_refused(build, fake):
    app = build()
    async with TestClient(app) as victim, TestClient(app) as attacker:
        callback = fake.authorize(await start(attacker, fake))  # the attacker's own login...
        assert error_of(await victim.get(callback)) == ("/", "state")  # ...planted on a victim
        assert (await victim.get("/me")).json()["user"] is None


async def test_an_expired_flow_is_refused(build, fake, monkeypatch):
    app = build()
    async with TestClient(app) as client:
        callback = fake.authorize(await start(client, fake))
        real = time.time
        monkeypatch.setattr("ushka.auth.flow.time.time", lambda: real() + 3600)
        assert error_of(await client.get(callback)) == ("/", "state")


async def test_the_fake_server_verifies_pkce(build, fake):
    app = build()
    async with TestClient(app) as client:
        location = await start(client, fake)
        callback = fake.authorize(location)
        fake.codes[next(iter(fake.codes))]["challenge"] = "tampered"  # a verifier that does not match
        assert error_of(await client.get(callback)) == ("/", "token")
        # and the happy path proves the verifier does match the challenge
        assert (await login(client, fake)).headers["location"] == "/"
        form = [r for r in fake.requests if r["path"] == "/token"][-1]["form"]
        assert 43 <= len(form["code_verifier"]) <= 128


async def test_state_pkce_and_nonce_are_random_per_login(build, fake):
    app = build()
    async with TestClient(app) as client:
        seen = [parse_qs(urlsplit(await start(client, fake)).query) for _ in range(3)]
        for key in ("state", "code_challenge", "nonce"):
            assert len({q[key][0] for q in seen}) == 3


async def test_a_wrong_nonce_in_the_id_token_is_refused(build, fake):
    fake.mode = "wrong_nonce"
    app = build()
    async with TestClient(app) as client:
        assert error_of(await login(client, fake)) == ("/", "token")


# -- the profile ----------------------------------------------------------------------


async def test_unverified_email_is_refused(build, fake):
    fake.google["email_verified"] = False
    fake.github_emails = [{"email": "ana@example.com", "primary": True, "verified": False}]
    app = build()
    async with TestClient(app) as client:
        assert error_of(await login(client, fake)) == ("/", "unverified")
        assert error_of(await login(client, fake, "github")) == ("/", "unverified")
        assert (await client.get("/me")).json()["user"] is None


async def test_allowed_email_domains(build, fake):
    app = build(TOML + 'allowed_email_domains = ["example.com"]\n')
    async with TestClient(app) as client:
        assert (await login(client, fake)).headers["location"] == "/"
        await client.get("/bye")
        fake.google.update(email="eve@evil.example", hd="evil.example")
        assert error_of(await login(client, fake)) == ("/", "domain")
        # a custom-domain address without the Workspace claim is not enough on Google
        fake.google.update(email="eve@example.com", hd="")
        assert error_of(await login(client, fake)) == ("/", "domain")
        fake.github_emails = [{"email": "x@other.example", "primary": True, "verified": True}]
        assert error_of(await login(client, fake, "github")) == ("/", "domain")
        assert (await client.get("/me")).json()["user"] is None


async def test_the_domain_hint_is_sent_for_a_single_domain(build, fake):
    app = build(TOML + 'allowed_email_domains = ["example.com"]\n')
    async with TestClient(app) as client:
        assert parse_qs(urlsplit(await start(client, fake)).query)["hd"] == ["example.com"]


async def test_provider_error_is_a_redirect_with_a_code(build, fake):
    app = build(TOML + 'login_error_path = "/oops"\n')
    async with TestClient(app) as client:
        location = await start(client, fake)
        res = await client.get(fake.authorize(location, error="access_denied"))
        assert error_of(res) == ("/oops", "denied")
        assert res.headers["location"] == "/oops?login_error=denied"
        location = await start(client, fake)
        res = await client.get(fake.authorize(location, error="server_error&error_description=EVIL-TEXT"))
        assert error_of(res) == ("/oops", "provider") and "EVIL-TEXT" not in res.text + res.headers["location"]


async def test_token_endpoint_failures_never_become_a_500(build, fake, caplog):
    app = build()
    caplog.set_level(logging.DEBUG)
    async with TestClient(app) as client:
        for mode, code in (("token_error", "token"), ("token_200_error", "token"), ("garbage", "token"), ("redirect", "token")):
            fake.mode = mode
            res = await login(client, fake)
            assert error_of(res) == ("/", code), mode
            assert "PROVIDER-SECRET-TEXT" not in res.text + res.headers["location"] + caplog.text
        assert fake.requests[-1]["path"] == "/token"  # the redirect to evil.example was never followed
    assert "evil.example" not in caplog.text


async def test_a_huge_answer_is_refused(build, fake):
    fake.mode = "huge"
    app = build()
    async with TestClient(app) as client:
        assert error_of(await login(client, fake)) == ("/", "token")


async def test_a_slow_provider_times_out(build, fake):
    fake.mode = "slow"
    app = build()
    async with TestClient(app) as client:
        assert error_of(await login(client, fake)) == ("/", "network")


async def test_provider_down_is_a_network_error(build, fake, monkeypatch):
    monkeypatch.setattr(Google, "token_url", "http://127.0.0.1:1/token")
    app = build()
    async with TestClient(app) as client:
        assert error_of(await login(client, fake)) == ("/", "network")


async def test_plain_http_endpoints_are_refused_for_real_providers(build, fake, monkeypatch):
    monkeypatch.setattr(Google, "allow_http", False)
    app = build()
    async with TestClient(app) as client:
        assert error_of(await login(client, fake)) == ("/", "config")
        assert fake.requests == []


# -- next ----------------------------------------------------------------------------


@pytest.mark.parametrize("evil", ["//evil.example", "https://evil.example/x", "javascript:alert(1)", "/\\evil.example", "///evil.example", "data:text/html,x"])
async def test_a_malicious_next_is_neutralised(build, fake, evil):
    app = build(TOML + 'after_login = "/home"\n')
    async with TestClient(app) as client:
        res = await login(client, fake, next_=evil)
        assert res.headers["location"] == "/home"


async def test_next_in_the_callback_is_ignored(build, fake):
    app = build()
    async with TestClient(app) as client:
        location = await start(client, fake, next_="/safe")
        res = await client.get(fake.authorize(location) + "&next=https://evil.example")
        assert res.headers["location"] == "/safe"


# -- sessions ------------------------------------------------------------------------


async def test_the_cookie_session_survives_login_and_logout(build, fake):
    app = build()
    async with TestClient(app) as client:
        await login(client, fake)
        assert (await client.get("/account")).json() == {"email": "ana@example.com"}
        await client.get("/bye")
        assert (await client.get("/me")).json()["user"] is None


def db_toml(workdir):
    return TOML + f'[session]\nstore = "database"\n[database]\nurl = "sqlite:///{workdir}/s.db"\n'


async def test_database_sessions_rotate_the_id_at_login(build, fake, workdir):
    app = build(db_toml(workdir))
    async with TestClient(app) as client:
        location = await start(client, fake)
        before = client.cookies["_ushka_session"]  # a session id exists before login
        res = await client.get(fake.authorize(location))
        after = client.cookies["_ushka_session"]
        assert res.status_code == 302 and after != before
        assert (await client.get("/me")).json()["user"]["email"] == "ana@example.com"

        # the id planted before the login is worthless
        async with TestClient(app) as attacker:
            assert (await attacker.get("/me", cookies={"_ushka_session": before})).json()["user"] is None


async def test_database_sessions_logout_revokes_a_copied_cookie(build, fake, workdir):
    app = build(db_toml(workdir))
    async with TestClient(app) as client:
        await login(client, fake)
        stolen = client.cookies["_ushka_session"]
        await client.get("/bye")
        async with TestClient(app) as thief:
            assert (await thief.get("/me", cookies={"_ushka_session": stolen})).json()["user"] is None


async def test_database_sessions_a_replayed_callback_is_refused(build, fake, workdir):
    app = build(db_toml(workdir))
    async with TestClient(app) as client:
        callback = fake.authorize(await start(client, fake))
        assert (await client.get(callback)).headers["location"] == "/"
        assert error_of(await client.get(callback)) == ("/", "state")


# -- routes: yours win, no credentials no routes --------------------------------------


async def test_your_route_overrides_the_built_in_one(build, fake):
    app = build()

    @app.get("/auth/google/login")
    async def mine():
        return {"mine": True}

    async with TestClient(app) as client:
        assert (await client.get("/auth/google/login")).json() == {"mine": True}
        assert (await client.get("/auth/github/login")).status_code == 302  # the other one is still built in


async def test_a_provider_without_credentials_has_no_routes(build, fake):
    toml = f'[app]\nauto_discover = false\n[oauth]\ngoogle_client_id = "id"\nredirect_base = "{BASE}"\n'
    app = build(toml, env={"USHKA_OAUTH_GOOGLE_CLIENT_SECRET": ""})
    async with TestClient(app) as client:
        for provider in ("google", "github"):
            for page in ("login", "callback"):
                assert (await client.get(f"/auth/{provider}/{page}")).status_code == 404


async def test_the_callback_and_login_answer_get_only(build, fake):
    app = build()
    async with TestClient(app) as client:
        callback = fake.authorize(await start(client, fake))
        assert (await client.head(callback)).status_code == 405  # a prefetch must not use up the login
        assert (await client.get(callback)).headers["location"] == "/"


# -- redirect_uri ---------------------------------------------------------------------


async def test_redirect_uri_does_not_depend_on_the_host_header(build, fake):
    app = build()
    async with TestClient(app) as client:
        res = await client.get("http://evil.example/auth/google/login", headers={"X-Forwarded-Host": "evil.example"})
        q = parse_qs(urlsplit(res.headers["location"]).query)
        assert q["redirect_uri"] == [f"{BASE}/auth/google/callback"]


async def test_redirect_uri_falls_back_to_seo_url(build, fake):
    toml = '[app]\nauto_discover = false\n[seo]\nurl = "https://seo.example.test"\n[oauth]\ngoogle_client_id = "id"\n'
    app = build(toml)
    async with TestClient(app) as client:
        q = parse_qs(urlsplit(await start(client, fake)).query)
        assert q["redirect_uri"] == ["https://seo.example.test/auth/google/callback"]


async def test_without_a_trusted_origin_the_app_refuses_to_start(build, fake):
    toml = '[app]\nauto_discover = false\n[oauth]\ngoogle_client_id = "id"\n'
    with pytest.raises(RuntimeError, match="redirect_base"):
        build(toml)


async def test_debug_may_use_the_request_origin(build, fake):
    toml = '[app]\nauto_discover = false\ndebug = true\n[oauth]\ngoogle_client_id = "id"\n'
    app = build(toml)
    async with TestClient(app) as client:
        q = parse_qs(urlsplit(await start(client, fake)).query)
        assert q["redirect_uri"] == ["http://testserver/auth/google/callback"]


# -- the API -------------------------------------------------------------------------


async def test_login_required_redirects_with_the_current_url(build, fake):
    app = build()
    async with TestClient(app) as client:
        res = await client.get("/account?tab=2&x=a%20b")
        assert res.status_code == 302
        assert res.headers["location"] == "/auth/google/login?next=%2Faccount%3Ftab%3D2%26x%3Da%2520b"
        location = (await client.get(res.headers["location"])).headers["location"]
        done = await client.get(fake.authorize(location))
        assert done.headers["location"] == "/account?tab=2&x=a%20b"
        assert (await client.get("/account")).json() == {"email": "ana@example.com"}


async def test_login_required_for_picks_the_provider(build, fake):
    app = build()
    async with TestClient(app) as client:
        assert (await client.get("/gh-only")).headers["location"].startswith("/auth/github/login?next=")


def test_login_url(build, fake):
    app = build()
    assert login_url("google", config=app.config) == "/auth/google/login"
    assert login_url("github", next="/x y", config=app.config) == "/auth/github/login?next=%2Fx+y"
    with pytest.raises(ValueError, match="unknown provider"):
        login_url("myspace", config=app.config)


async def test_current_user_is_none_for_a_forged_session_value(build, fake):
    app = build()

    @app.get("/plant")
    async def plant(request):
        request.session["user"] = "admin"
        return {}

    async with TestClient(app) as client:
        await client.get("/plant")
        assert (await client.get("/me")).json()["user"] is None


# -- secrets -------------------------------------------------------------------------


async def test_no_secret_or_token_appears_in_logs_or_responses(build, fake, caplog):
    caplog.set_level(logging.DEBUG)
    app = build()
    seen = []
    async with TestClient(app) as client:
        for mode in ("ok", "token_error", "huge", "garbage", "wrong_nonce"):
            fake.mode = mode
            location = await start(client, fake)
            seen.append(location)
            res = await client.get(fake.authorize(location))
            seen += [res.text, str(res.headers), (await client.get("/me")).text]
        fake.mode = "ok"
        await login(client, fake, "github")
    blob = "\n".join(seen) + caplog.text
    assert CLIENT_SECRET not in blob and ACCESS_TOKEN not in blob
    assert CLIENT_SECRET not in repr(Google("id", CLIENT_SECRET))


# -- check and configuration -----------------------------------------------------------


def test_check_warns_about_a_half_configured_provider(build, fake):
    app = build('[app]\nauto_discover = false\n[oauth]\ngithub_client_id = "id"\nredirect_base = "https://x.test"\n', env={"USHKA_OAUTH_GITHUB_CLIENT_SECRET": ""})
    found = problems(app.config)
    assert any(level == "warn" and "github" in msg and "client_secret" in msg for level, msg in found)


def test_check_on_a_real_config(workdir, monkeypatch):
    from ushka.core.config import Config

    monkeypatch.setenv("USHKA_OAUTH_GOOGLE_CLIENT_SECRET", "x")
    (workdir / "ushka.toml").write_text('[oauth]\ngoogle_client_id = "id"\n')
    config = Config(workdir).load_from_file()
    found = problems(config, production=True)
    assert ("error", "[oauth] has no trusted address for the redirect URI: set [oauth] redirect_base (or [seo] url), e.g. \"https://example.com\"") in found
    assert any("cookie" in msg and "revoked" in msg for level, msg in found if level == "warn")

    Config._instance = None
    Config._initialized = False
    (workdir / "ushka.toml").write_text('[oauth]\ngoogle_client_id = "id"\nredirect_base = "http://example.com"\n[session]\nstore = "database"\n')
    found = problems(Config(workdir).load_from_file(), production=True)
    assert [m for lvl, m in found if lvl == "error"] == []
    assert any("not https" in m for _, m in found)
    assert not any("cookie" in m for _, m in found)


def test_import_ushka_does_not_load_the_auth_package():
    import subprocess
    import sys

    code = "import sys, ushka; print('ushka.auth' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip() == "False"
