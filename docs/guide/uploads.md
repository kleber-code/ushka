# Uploads

A browser sends files in a `multipart/form-data` form. Ushka gives each one to
you as an `UploadFile`: its name, type and size, and a `save()` that writes it
to disk under a name you can trust.

## A complete example

The form needs `method="post"` and `enctype="multipart/form-data"`:

```html
<!-- templates/avatar.html -->
<form method="post" action="/avatar" enctype="multipart/form-data">
  <input type="text" name="caption">
  <input type="file" name="avatar" accept="image/png,image/jpeg" required>
  <button>Upload</button>
</form>
```

The route declares the file as a typed parameter, checks it and saves it:

```python
# routes/avatar.py
import secrets
from typing import Annotated

from ushka import Form, UploadFile, render
from ushka.http.exceptions import HTTPBadRequest

UPLOADS = "uploads"
MAX_BYTES = 2 * 1024 * 1024
MAGIC = {b"\x89PNG\r\n\x1a\n": ".png", b"\xff\xd8\xff": ".jpg"}


async def get(request):
    return await render(request, "avatar.html")


async def post(avatar: UploadFile, caption: Annotated[str, Form()] = ""):
    if avatar.size > MAX_BYTES:
        raise HTTPBadRequest(message="Image too large (2 MB at most)")

    head = avatar.head(8)                       # what the bytes say, not the client
    ext = next((e for magic, e in MAGIC.items() if head.startswith(magic)), None)
    if ext is None:
        raise HTTPBadRequest(message="Send a PNG or a JPEG")

    path = avatar.save(UPLOADS, secrets.token_hex(16) + ext)   # our name, our extension
    return {"saved": path.name, "bytes": avatar.size}, 201
```

`save()` created `uploads/` if it was missing, wrote the file under a name made
of random hex and the extension the bytes proved, and returned the `Path`.
Nothing the client wrote reached the file system.

Without type hints, `request.files()` does the same by hand:

```python
async def post(request):
    upload = (await request.files())["avatar"]
    return {"name": upload.safe_filename, "size": upload.size}
```

## `UploadFile`

| | |
| --- | --- |
| `filename` | What the client called it. `Untrusted`. |
| `content_type` | What the client claims it is. `Untrusted`. |
| `size` | Bytes received. |
| `file` | A seekable binary file: in memory up to 2 MB, then a temporary file on disk. |
| `safe_filename` | `filename` cleaned for the file system: no directories, only letters, digits, `.`, `-` and `_`. A plain `str`. |
| `extension` | The lower-case extension of `safe_filename`, with its dot. |
| `read(size=-1)` | Reads bytes from the current position. |
| `head(n=16)` | The first `n` bytes without moving the position: for magic numbers. |
| `save(directory, name=None, *, extensions=None, overwrite=False)` | Writes the file and returns its `Path`. |
| `close()` | Releases the temporary file. Ushka does it when the request ends. |

`read()` and `save()` are ordinary blocking calls. For big files off the event
loop, use `await asyncio.to_thread(upload.save, "uploads")`. Save or read the
file inside the handler: it is closed once the response is sent.

Code written for the old dictionaries still works: `upload["filename"]`,
`upload["content_type"]`, `upload["size"]` and `upload["file"]`.

### `save()` rules

- **Without `name`** the file gets a random name plus the (cleaned, lower-case)
  extension of the client's file name, so two uploads never collide.
- **With `name`**, it must be a plain file name that *you* chose (`"avatar-42.png"`).
  A `/`, `\`, `..`, an empty name, or an `Untrusted` value raises. To keep the
  client's name, pass `upload.safe_filename`, ideally with a prefix of your own.
- **`extensions=[".png", ".jpg"]`** refuses any other extension of the final
  name with `ValueError`. Dots and case do not matter.
- **It never overwrites** an existing file: `FileExistsError`, unless you pass
  `overwrite=True`. It does not follow a symbolic link at the target either.
- `directory` is created with its parents. It must be a path of yours, not
  request data (an `Untrusted` one raises `UnsafeValueError`).

## Several files, and files in a model

```python
async def post(photos: list[UploadFile]):       # <input type="file" name="photos" multiple>
    return {"saved": [p.save("uploads").name for p in photos]}
```

A form can be one dataclass; text fields and files are filled in by name:

```python
import dataclasses

@dataclasses.dataclass
class Signup:
    email: str
    avatar: UploadFile
    extras: list[UploadFile] = dataclasses.field(default_factory=list)

async def post(form: Annotated[Signup, Form()]):
    form.avatar.save("uploads")
```

A file input the visitor left empty counts as no file: a required parameter
answers 422, and an `UploadFile | None = None` is `None`. Outside type hints,
`await request.uploads()` returns every file of every field as lists, and
`request.files()` the last file of each field. `request.form()` holds only the
text fields.

## Limits

- `[limits] max_request_body_multipart_size_in_KB` (50 MB) caps each uploaded
  file. A text field is capped at 64 KB. Beyond a limit the client gets **413**.
- `[limits] max_request_body_size_in_KB` (2 MB) caps ordinary bodies and how much
  of a file stays in memory before it goes to disk.
- Check `size` yourself for a stricter rule (the example above allows 2 MB), and
  put a limit on the proxy too (`client_max_body_size` in nginx, `request_body
  { max_size }` in Caddy) so huge bodies are refused before they reach Ushka.

## Security

- **Never trust `filename`.** It is client data and can contain `../`, a drive
  letter, markup or a double extension (`a.php.png`). Ushka marks it `Untrusted`
  so a path built from it is refused by the guard; use `save()`'s generated name
  or `safe_filename`.
- **Never trust `content_type`.** The client writes it, and it can say
  `image/png` for a script. When the type matters, check the first bytes
  (`head()`) as in the example, or decode the file with an image library.
- **Control the extension** with `extensions=[...]`, and do not let uploads be
  served as pages: put them in a folder outside `routes/` and expose it with
  [`app.mount_static`](static_files.md#serving-any-folder), or hand them out
  through a route that checks permissions. For user-supplied HTML, SVG and
  similar, serve with `Content-Disposition: attachment`.
- **Do not execute or `import` what was uploaded**, and do not unpack archives
  without checking the paths inside them.
- Keep the upload folder out of the repository and out of the image: a volume.
