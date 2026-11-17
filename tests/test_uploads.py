"""`UploadFile`: what `request.files()` returns, how it is saved and how it is declared."""

import dataclasses
import io
import json
from typing import Annotated

import pytest

from ushka import Form, Request, UploadFile
from ushka.guard import UnsafeValueError, Untrusted
from ushka.http.uploads import safe_filename

BOUNDARY = "xBOUNDARYx"
HEADERS = {"content-type": f"multipart/form-data; boundary={BOUNDARY}"}


def multipart(fields=(), files=()):
    """`fields`: (name, text); `files`: (field, filename, content_type, bytes)."""
    out = b""
    for name, value in fields:
        out += (
            f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    for field, filename, ctype, data in files:
        out += (
            f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode() + data + b"\r\n"
    return out + f"--{BOUNDARY}--\r\n".encode()


def make(data=b"hello", filename="a.txt", ctype="text/plain"):
    return UploadFile(filename, ctype, io.BytesIO(data))


# --- the object ------------------------------------------------------------------


def test_attributes_and_mapping_access():
    up = make(b"12345", "My Photo.PNG", "image/png")

    assert up.size == 5
    assert up.filename == "My Photo.PNG" and isinstance(up.filename, Untrusted)
    assert isinstance(up.content_type, Untrusted)
    assert up["filename"] == "My Photo.PNG" and up["content_type"] == "image/png"
    assert up["file"] is up.file and up["size"] == 5
    assert up.get("nope") is None and "file" in up and dict(up)["size"] == 5
    with pytest.raises(KeyError):
        up["nope"]
    assert up.read() == b"12345"
    assert up.head(2) == b"12" and up.read() == b""  # head() leaves the position alone


def test_filename_is_plain_when_the_guard_is_off():
    up = UploadFile("a.txt", "text/plain", io.BytesIO(b""), taint=False)
    assert type(up.filename) is str


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("report.pdf", "report.pdf"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\x\\evil.EXE", "evil.EXE"),
        ("..", "upload"),
        ("", "upload"),
        (".htaccess", "htaccess"),
        ("fo to é.png", "fo_to_e.png"),
        ("a\x00b.txt", "a_b.txt"),
        ("<script>.html", "script_.html"),
    ],
)
def test_safe_filename(raw, expected):
    assert safe_filename(raw) == expected


def test_safe_filename_is_bounded_and_plain():
    name = safe_filename("x" * 500 + ".png")
    assert len(name) <= 100 and name.endswith(".png") and type(name) is str
    assert type(make(filename="a.txt").safe_filename) is str


def test_save_with_a_given_name(tmp_path):
    path = make(b"data").save(tmp_path / "up", "doc.txt")

    assert path == (tmp_path / "up" / "doc.txt").resolve()
    assert path.read_bytes() == b"data"


def test_save_without_a_name_ignores_the_client_name(tmp_path):
    up = make(b"x", "../../evil.PNG")
    path = up.save(tmp_path)

    assert path.parent == tmp_path.resolve()
    assert path.suffix == ".png" and len(path.stem) == 32
    assert "evil" not in path.name


def test_save_does_not_overwrite_unless_asked(tmp_path):
    make(b"one").save(tmp_path, "f.txt")
    with pytest.raises(FileExistsError):
        make(b"two").save(tmp_path, "f.txt")
    assert (tmp_path / "f.txt").read_bytes() == b"one"

    make(b"two").save(tmp_path, "f.txt", overwrite=True)
    assert (tmp_path / "f.txt").read_bytes() == b"two"


@pytest.mark.parametrize("name", ["../x.txt", "a/b.txt", "a\\b.txt", "..", ".", "", "x\x00.txt"])
def test_save_rejects_names_that_are_not_plain(tmp_path, name):
    with pytest.raises(ValueError):
        make().save(tmp_path, name)
    assert list(tmp_path.iterdir()) == []


def test_save_refuses_untrusted_paths(tmp_path):
    with pytest.raises(UnsafeValueError):
        make().save(tmp_path, Untrusted("x.txt", "query:name"))
    with pytest.raises(UnsafeValueError):
        make().save(Untrusted(str(tmp_path), "query:dir"))


def test_save_will_not_follow_a_symlink(tmp_path):
    target = tmp_path / "secret.txt"
    target.write_text("keep")
    (tmp_path / "up").mkdir()
    (tmp_path / "up" / "link.txt").symlink_to(target)

    with pytest.raises(OSError):
        make(b"pwn").save(tmp_path / "up", "link.txt", overwrite=True)
    assert target.read_text() == "keep"


def test_save_extensions_are_checked_on_the_final_name(tmp_path):
    assert make().save(tmp_path, "a.PNG", extensions=["png", ".jpg"]).name == "a.PNG"
    with pytest.raises(ValueError):
        make().save(tmp_path, "a.php", extensions=[".png"])
    with pytest.raises(ValueError):
        make(filename="shell.php").save(tmp_path, extensions=[".png"])


def test_save_keeps_the_read_position_and_close_releases_the_file(tmp_path):
    up = make(b"abcdef")
    up.read(2)
    up.save(tmp_path, "a.bin")
    assert up.read() == b"cdef"
    up.close()
    assert up.file.closed


# --- through a request -----------------------------------------------------------


@pytest.fixture
def uploads_app(app):
    @app.post("/old")
    async def old(request: Request):
        files = await request.files()
        form = await request.form()
        up = files["doc"]
        return {
            "legacy": [up["filename"], up["content_type"], up["file"].read().decode()],
            "text": dict(form),
            "form_has_file": "doc" in form,
            "type": type(up).__name__,
        }

    return app


async def test_request_files_returns_upload_files_and_form_has_only_text(uploads_app, call):
    body = multipart([("title", "Hi")], [("doc", "n.txt", "text/plain", b"contents")])
    res = await call(uploads_app, "POST", "/old", body=body, headers=HEADERS)

    data = json.loads(res["body"])
    assert data["legacy"] == ["n.txt", "text/plain", "contents"]
    assert data["text"] == {"title": "Hi"} and data["form_has_file"] is False
    assert data["type"] == "UploadFile"


async def test_typed_parameters_receive_upload_files(app, call, tmp_path):
    @app.post("/one")
    async def one(avatar: UploadFile, caption: Annotated[str, Form()] = ""):
        return {"name": avatar.safe_filename, "size": avatar.size, "caption": str(caption)}

    @app.post("/many")
    async def many(photos: list[UploadFile]):
        return {"names": [p.safe_filename for p in photos]}

    @app.post("/optional")
    async def optional(cv: UploadFile | None = None):
        return {"cv": None if cv is None else cv.size}

    body = multipart([("caption", "c")], [("avatar", "me.png", "image/png", b"PNGDATA")])
    res = await call(app, "POST", "/one", body=body, headers=HEADERS)
    assert json.loads(res["body"]) == {"name": "me.png", "size": 7, "caption": "c"}

    body = multipart(files=[("photos", "a.jpg", "image/jpeg", b"1"), ("photos", "b.jpg", "image/jpeg", b"22")])
    res = await call(app, "POST", "/many", body=body, headers=HEADERS)
    assert json.loads(res["body"]) == {"names": ["a.jpg", "b.jpg"]}

    body = multipart(files=[("photos", "only.jpg", "image/jpeg", b"1")])
    res = await call(app, "POST", "/many", body=body, headers=HEADERS)
    assert json.loads(res["body"]) == {"names": ["only.jpg"]}

    blank = multipart(files=[("cv", "", "application/octet-stream", b"")])  # input left empty
    res = await call(app, "POST", "/optional", body=blank, headers=HEADERS)
    assert json.loads(res["body"]) == {"cv": None}


async def test_missing_required_upload_is_a_422(app, call):
    @app.post("/need")
    async def need(avatar: UploadFile):
        return "ok"

    res = await call(app, "POST", "/need", body=multipart([("x", "y")]), headers=HEADERS)
    assert res["status"] == 422
    assert json.loads(res["body"])["detail"][0]["loc"] == ["form", "avatar"]


async def test_upload_inside_a_form_dataclass(app, call):
    @dataclasses.dataclass
    class Signup:
        email: str
        avatar: UploadFile
        extras: list[UploadFile] = dataclasses.field(default_factory=list)

    @app.post("/signup")
    async def signup(form: Annotated[Signup, Form()]):
        return {"email": str(form.email), "avatar": form.avatar.size, "extras": len(form.extras)}

    body = multipart(
        [("email", "a@b.c")],
        [("avatar", "a.png", "image/png", b"123"), ("extras", "e1", "text/plain", b"1"), ("extras", "e2", "text/plain", b"2")],
    )
    res = await call(app, "POST", "/signup", body=body, headers=HEADERS)
    assert json.loads(res["body"]) == {"email": "a@b.c", "avatar": 3, "extras": 2}


async def test_the_upload_size_limit_still_applies(make_app, workdir, call):
    (workdir / "ushka.toml").write_text("[limits]\nmax_request_body_multipart_size_in_KB = 1\n")
    app = make_app()

    @app.post("/up")
    async def up(f: UploadFile):
        return "ok"

    body = multipart(files=[("f", "big.bin", "application/octet-stream", b"x" * 4096)])
    res = await call(app, "POST", "/up", body=body, headers=HEADERS)
    assert res["status"] == 413


async def test_save_from_a_handler_and_files_are_closed_afterwards(app, call, tmp_path):
    seen = []

    @app.post("/save")
    async def save(doc: UploadFile):
        seen.append(doc)
        return {"path": doc.save(tmp_path / "up").name}

    body = multipart(files=[("doc", "../../x.TXT", "text/plain", b"hello")])
    res = await call(app, "POST", "/save", body=body, headers=HEADERS)

    name = json.loads(res["body"])["path"]
    assert (tmp_path / "up" / name).read_bytes() == b"hello"
    assert name.endswith(".txt")
    assert seen[0].file.closed


def test_a_disallowed_extension_is_a_400_not_a_500(tmp_path):
    from ushka.http.exceptions import HTTPBadRequest
    from ushka.http.uploads import UploadRejected

    up = make(b"x", "evil.php")
    with pytest.raises(UploadRejected) as err:
        up.save(tmp_path, extensions=[".png"])
    assert isinstance(err.value, HTTPBadRequest) and isinstance(err.value, ValueError)
    assert err.value.status_code == 400 and "evil" not in str(err.value.message)
