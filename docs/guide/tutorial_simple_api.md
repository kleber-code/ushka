# Building a Simple API with Ushka

So, you want to build an API? Excellent. You've come to the right place. I'm
going to show you how to build a small JSON API with me, Ushka. It's so easy,
it's almost insulting. (¬‿¬)

You will learn filesystem routes, request bodies, status codes, path
parameters and how Ushka Guard keeps request data honest.

## 1. Setting up your domain (project)

Install me and create a project folder. I don't care what you name it, as long
as it's suitably grand.

```bash
pip install ushka
mkdir my_awesome_api
cd my_awesome_api
```

You need an `app.py` and a `routes/` folder. Remember, `routes/` is where the
magic happens.

```text
my_awesome_api/
├── app.py
├── store.py
└── routes/
    ├── index.py
    └── items/
        ├── index.py
        └── [item_id].py
```

`app.py` is just a few lines:

```python
# app.py
from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    app.run()
```

!!! tip
    `ushka new my_awesome_api` creates a complete project (templates, static
    files, `.env` with a secret key) if you prefer to start from that.

## 2. Your first enchantment: a simple route

A file in `routes/` is a URL, and a function named after an HTTP verb answers
it. `routes/index.py` is `/`:

```python
# routes/index.py
def get():
    return {"message": "Hello from my awesome API!"}
```

Start the development server. It reloads whenever you save a file, so you can
leave it running for the rest of the tutorial:

```bash
ushka dev
```

Open <http://127.0.0.1:8000> and you'll see
`{"message": "Hello from my awesome API!"}`. Returning a `dict` gives you JSON.
See? I told you I was good.

## 3. Handling your demands: request data

Let's accept new items with `POST /items`. We'll keep them in memory, in a
module of their own so every route file shares the same dict:

```python
# store.py
from itertools import count

ITEMS = {}       # our "database" for now
NEXT_ID = count(1)
```

An `index.py` inside a folder serves the folder's URL, so create
`routes/items/index.py`:

```python
# routes/items/index.py
from ushka import Request

from store import ITEMS, NEXT_ID


async def get():
    return list(ITEMS.values())


async def post(request: Request):
    data = await request.json()
    name = data.get("name")
    if not name:
        return {"error": "Item name is required"}, 400

    item_id = str(next(NEXT_ID))
    ITEMS[item_id] = {"id": item_id, "name": name}
    return ITEMS[item_id], 201
```

Returning a tuple `(body, status)` sets the status code. Try it:

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"name": "My New Widget"}' http://127.0.0.1:8000/items
```

```json
{"id": "1", "name": "My New Widget"}
```

Forget the name and you get a `400` with `{"error": "Item name is required"}`.
Send broken JSON and I answer `400 Bad Request` for you; you never have to
catch the parse error yourself.

## 4. Dynamic shenanigans: path parameters

To fetch one item we need `GET /items/<item_id>`. Square brackets in a file
name capture that part of the URL, so create `routes/items/[item_id].py`:

```python
# routes/items/[item_id].py
from ushka.guard import safe
from ushka.http.exceptions import HttpNotFound

from store import ITEMS


def get(item_id: str):
    item_id = str(safe.integer(item_id, min=1))  # "abc" or "0" -> 400 Bad Request
    if item_id not in ITEMS:
        raise HttpNotFound(message=f"No item {item_id}")
    return ITEMS[item_id]


def delete(item_id: str):
    ITEMS.pop(str(safe.integer(item_id, min=1)), None)
    return None  # 204 No Content
```

Now try it:

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"name": "Fancy Sword of Doom"}' http://127.0.0.1:8000/items
curl http://127.0.0.1:8000/items/1
```

```json
{"id": "1", "name": "Fancy Sword of Doom"}
```

`/items/42` answers `404`, `/items/abc` answers `400`, and
`curl -X DELETE http://127.0.0.1:8000/items/1` answers `204 No Content`
(returning `None` does that).

A few things worth knowing:

* `item_id` is always a **string**: the `: str` annotation is just
  documentation, and `item_id: int` would not convert anything. That is why we
  call `safe.integer()`.
* It is also `Untrusted`, like everything that comes from the client. Returning
  it inside JSON is perfectly fine. Pasting it into HTML, a redirect, a file path
  or raw SQL is not, and I will stop you with an error that explains the fix.
  Read [Ushka Guard](guard.md) when you get there.

## 5. Check your work

```bash
ushka routes list
```

```text
◆ 3 route(s)
  · / - GET
  · /items - GET, POST
  · /items/[item_id] - DELETE, GET
```

## You did it! (Mostly me)

Congratulations, you've built a simple API with Ushka. It wasn't so hard, was
it? Next steps:

* store the items for real with the [ORM](orm.md) (right now they vanish
  whenever the server reloads);
* add HTML pages with [templates](templates.md);
* learn all the [return values and request helpers](routing.md#return-values).

Now go forth and build amazing things. And remember who made it all possible.
(UwU)
