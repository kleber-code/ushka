"""`[security] trusted_proxies`: the client address behind Caddy/nginx, and no spoofing."""

import pytest

from ushka import Request
from ushka.cli import main
from ushka.cli.commands import new
from ushka.http import proxy


def _scope(peer, headers=None):
    return {
        "type": "http",
        "method": "GET",
        "path": "/",
        "scheme": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (peer, 5000) if peer else None,
    }


def ip(scope, trusted):
    return proxy.client_ip(scope, proxy.networks_from_config(trusted))


def test_without_trusted_proxies_the_headers_are_ignored():
    scope = _scope("203.0.113.9", {"x-forwarded-for": "1.1.1.1"})
    assert ip(scope, []) == "203.0.113.9"


def test_untrusted_peer_cannot_spoof_the_header():
    scope = _scope("203.0.113.9", {"x-forwarded-for": "1.1.1.1"})
    assert ip(scope, ["10.0.0.1"]) == "203.0.113.9"


def test_trusted_peer_gives_the_forwarded_client():
    scope = _scope("10.0.0.1", {"x-forwarded-for": "198.51.100.7"})
    assert ip(scope, ["10.0.0.1"]) == "198.51.100.7"


def test_forged_leftmost_entry_is_not_believed():
    # the client sent "6.6.6.6"; our proxy appended the address it really saw
    scope = _scope("10.0.0.1", {"x-forwarded-for": "6.6.6.6, 198.51.100.7"})
    assert ip(scope, ["10.0.0.1"]) == "198.51.100.7"


def test_chain_of_several_trusted_proxies_is_skipped_from_the_right():
    scope = _scope("10.0.0.2", {"x-forwarded-for": "6.6.6.6, 198.51.100.7, 10.0.0.9, 10.0.0.1"})
    assert ip(scope, ["10.0.0.0/24"]) == "198.51.100.7"


def test_repeated_headers_are_joined():
    scope = _scope("10.0.0.1")
    scope["headers"] = [(b"x-forwarded-for", b"6.6.6.6"), (b"x-forwarded-for", b"198.51.100.7")]
    assert ip(scope, ["10.0.0.1"]) == "198.51.100.7"


def test_cidr_and_ipv6():
    scope = _scope("fd00::5", {"x-forwarded-for": "2001:db8::1, fd00::9"})
    assert ip(scope, ["fd00::/64"]) == "2001:db8::1"
    assert ip(_scope("10.9.9.9", {"x-forwarded-for": "2001:db8::1"}), ["10.0.0.0/8"]) == "2001:db8::1"


def test_ipv4_mapped_peer_and_ports_and_brackets():
    scope = _scope("::ffff:10.0.0.1", {"x-forwarded-for": "198.51.100.7:4711"})
    assert ip(scope, ["10.0.0.1"]) == "198.51.100.7"
    assert ip(_scope("10.0.0.1", {"x-forwarded-for": "[2001:db8::1]:80"}), ["10.0.0.1"]) == "2001:db8::1"


@pytest.mark.parametrize(
    "header", ["unknown", "not-an-ip", "1.2.3", "999.1.1.1", "1.1.1.1, <script>", "1.2.3.4:notaport", "[::1", ""]
)
def test_malformed_header_falls_back_to_the_peer(header):
    scope = _scope("10.0.0.1", {"x-forwarded-for": header})
    assert ip(scope, ["10.0.0.1"]) == "10.0.0.1"


def test_all_hops_trusted_gives_the_nearest_peer():
    scope = _scope("10.0.0.1", {"x-forwarded-for": "10.0.0.2"})
    assert ip(scope, ["10.0.0.0/8"]) == "10.0.0.1"


def test_no_peer_means_unknown():
    assert ip(_scope(None, {"x-forwarded-for": "1.1.1.1"}), ["10.0.0.1"]) is None


def test_invalid_trusted_entries_are_skipped_and_star_is_not_a_wildcard(caplog):
    nets = proxy.networks_from_config(["*", "not-an-ip", "10.0.0.0/8"])
    assert [str(n) for n in nets] == ["10.0.0.0/8"]
    assert proxy.networks_from_config("10.0.0.1, 192.168.0.0/16") != ()
    assert proxy.networks_from_config(None) == ()


def test_scheme_and_host_only_from_a_trusted_proxy():
    nets = proxy.networks_from_config(["10.0.0.1"])
    headers = {"x-forwarded-proto": "https", "x-forwarded-host": "Example.com"}
    assert proxy.forwarded_scheme(_scope("10.0.0.1", headers), nets) == "https"
    assert proxy.forwarded_host(_scope("10.0.0.1", headers), nets) == "example.com"
    assert proxy.forwarded_scheme(_scope("203.0.113.9", headers), nets) == "http"
    assert proxy.forwarded_host(_scope("203.0.113.9", headers), nets) is None
    junk = {"x-forwarded-proto": "javascript", "x-forwarded-host": "a b/<x>"}
    assert proxy.forwarded_scheme(_scope("10.0.0.1", junk), nets) == "http"
    assert proxy.forwarded_host(_scope("10.0.0.1", junk), nets) is None


# --- through the app ---------------------------------------------------------


def _app(make_app, workdir, toml=""):
    if toml:
        (workdir / "ushka.toml").write_text(toml)
    app = make_app()

    @app.get("/who")
    async def who(request: Request):
        return {"ip": request.client_ip, "scheme": request.scheme, "secure": request.is_secure, "host": str(request.host)}

    return app


async def test_request_properties_with_a_trusted_proxy(make_app, workdir, call):
    app = _app(make_app, workdir, '[security]\ntrusted_proxies = ["127.0.0.1"]\n')
    headers = {"x-forwarded-for": "6.6.6.6, 198.51.100.7", "x-forwarded-proto": "https", "x-forwarded-host": "site.test", "host": "internal"}
    res = await call(app, "GET", "/who", headers=headers)  # the call fixture connects from 127.0.0.1

    assert '"ip": "198.51.100.7"' in res["body"]
    assert '"secure": true' in res["body"]
    assert '"host": "site.test"' in res["body"]
    assert "strict-transport-security" in res["headers"]  # https detected through the proxy


async def test_default_trusts_nobody(make_app, workdir, call):
    app = _app(make_app, workdir)
    headers = {"x-forwarded-for": "6.6.6.6", "x-forwarded-proto": "https", "host": "internal"}
    res = await call(app, "GET", "/who", headers=headers)

    assert '"ip": "127.0.0.1"' in res["body"]
    assert '"secure": false' in res["body"]
    assert '"host": "internal"' in res["body"]
    assert "strict-transport-security" not in res["headers"]


def test_client_ip_is_a_plain_string(make_app, workdir):
    app = _app(make_app, workdir)
    request = Request(app, _scope("10.0.0.1"), None)
    assert type(request.client_ip) is str


def test_check_production_warns_about_a_public_bind_without_proxies(workdir, monkeypatch, capsys):
    for name in ("USHKA_APP_DEBUG", "USHKA_APP_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    new.create_project("demo")
    monkeypatch.chdir(workdir / "demo")
    (workdir / "demo" / "ushka.toml").write_text('[server]\nhost = "0.0.0.0"\n', encoding="utf-8")
    main(["check", "--production"])
    out = capsys.readouterr()
    assert "trusted_proxies is empty" in out.out + out.err

    (workdir / "demo" / "ushka.toml").write_text(
        '[server]\nhost = "0.0.0.0"\n[security]\ntrusted_proxies = ["172.18.0.0/16"]\n', encoding="utf-8"
    )
    main(["check", "--production"])
    out = capsys.readouterr()
    assert "trusted_proxies is empty" not in out.out + out.err


def test_production_server_leaves_forwarded_headers_to_ushka(monkeypatch):
    pytest.importorskip("uvicorn")
    from ushka.core import server as srv

    seen = {}

    class Fake:
        started = True

        def __init__(self, config):
            seen["config"] = config

        def run(self):
            pass

    monkeypatch.setattr(srv, "QuietServer", Fake)
    srv.run_server("x:y", host="127.0.0.1", port=1, workers=1, log_config=None)
    assert seen["config"].proxy_headers is False
