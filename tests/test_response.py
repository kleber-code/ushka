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
    assert result["headers"]["content-type"] == "text/plain; charset=utf-8"
    assert result["body"] == b"hello"


async def test_dict_body_is_serialized_as_json():
    result = await _send_response(Response({"ok": True}))

    assert result["headers"]["content-type"] == "application/json; charset=utf-8"
    assert json.loads(result["body"]) == {"ok": True}


async def test_list_body_is_serialized_as_json():
    result = await _send_response(Response([1, 2, 3]))

    assert result["headers"]["content-type"] == "application/json; charset=utf-8"
    assert json.loads(result["body"]) == [1, 2, 3]


async def test_html_body_is_detected():
    result = await _send_response(Response("<html><body>hi</body></html>"))

    assert result["headers"]["content-type"] == "text/html; charset=utf-8"


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

    assert result["headers"]["content-type"] == "text/csv; charset=utf-8"


def test_json_response_serializes_datetime_decimal_uuid():
    import datetime
    import json
    import uuid
    from decimal import Decimal

    uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    when = datetime.datetime(2026, 11, 17, 10, 0, tzinfo=datetime.timezone.utc)
    res = Response({"at": when, "d": Decimal("1.50"), "id": uid, "day": when.date(), "n": [Decimal(2)]})
    assert res.media_type == "application/json"
    assert json.loads(res.body) == {
        "at": "2026-11-17T10:00:00+00:00", "d": "1.50", "id": str(uid), "day": "2026-11-17", "n": ["2"],
    }
