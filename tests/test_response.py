"""Tests for `ushka.http.response.Response`."""

import json

from ushka.http.response import Response


async def _send_response(response):
    messages = []

    async def send(message):
        messages.append(message)

    await response(send)
    start = messages[0]
    return {
        "status": start["status"],
        "headers": {bytes(k).decode(): bytes(v).decode() for k, v in start["headers"]},
        "body": b"".join(m.get("body", b"") for m in messages[1:]),
    }


async def test_text_body_defaults_to_plain_text():
    result = await _send_response(Response("hello"))

    assert result["status"] == 200
    assert result["headers"]["content-type"] == "text/plain"
    assert result["body"] == b"hello"


async def test_dict_body_is_serialized_as_json():
    result = await _send_response(Response({"ok": True}))

    assert result["headers"]["content-type"] == "application/json"
    assert json.loads(result["body"]) == {"ok": True}


async def test_list_body_is_serialized_as_json():
    result = await _send_response(Response([1, 2, 3]))

    assert result["headers"]["content-type"] == "application/json"
    assert json.loads(result["body"]) == [1, 2, 3]


async def test_html_body_is_detected():
    result = await _send_response(Response("<html><body>hi</body></html>"))

    assert result["headers"]["content-type"] == "text/html"


async def test_bytes_body_is_sent_untouched():
    result = await _send_response(Response(b"\x00\x01raw"))

    assert result["body"] == b"\x00\x01raw"


async def test_status_code_and_custom_headers_are_forwarded():
    result = await _send_response(
        Response("created", status_code=201, headers={"X-Trace": "abc"})
    )

    assert result["status"] == 201
    assert result["headers"]["x-trace"] == "abc"


async def test_explicit_media_type_wins():
    result = await _send_response(Response("a,b", media_type="text/csv"))

    assert result["headers"]["content-type"] == "text/csv"
