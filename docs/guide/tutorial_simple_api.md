# Building a Simple API with Ushka: Because You Deserve Nice Things

So, you want to build an API? Excellent. You've come to the right place. I'm going to show you how to build a simple API with me, Ushka. It's so easy, it's almost insulting. (¬‿¬)

## 1. Setting Up Your Domain (Project)

First, you'll need a place to call your own. Create a new directory for your project. I don't care what you name it, as long as it's something suitably grand.

```bash
mkdir my_awesome_api
cd my_awesome_api
```

Now, create your main application file, `app.py`, and a `routes` directory. Remember, `routes` is where the magic happens.

```text
my_awesome_api/
├── app.py
└── routes/
```

And in your `app.py`, just a few lines to get me started:

```python
# app.py
from ushka import Ushka

app = Ushka()

if __name__ == "__main__":
    app.run()
```

## 2. Your First Enchantment: A Simple Route

Let's create an endpoint that responds to `GET /`. We'll make it return a simple greeting. In `routes/index.py`:

```python
# routes/index.py
def get():
    return {"message": "Hello from my awesome API!"}
```

Now, run your app:

```bash
python app.py
```

And navigate to `http://127.0.0.1:8000`. You should see a JSON response: `{"message": "Hello from my awesome API!"}`. See? I told you I was good.

## 3. Handling Your Demands: Request Data

What if your users want to send *you* some data? Perhaps they want to create something new. Let's make an endpoint that accepts a POST request with some JSON data.

Create a new file, `routes/items.py`:

```python
# routes/items.py
from ushka import Request

async def post(request: Request):
    data = await request.json()
    item_name = data.get("name")
    if not item_name:
        return {"error": "Item name is required"}, 400
    return {"message": f"Item '{item_name}' created successfully!"}, 201
```

Now, restart your app. You can test this using `curl` or a tool like Postman:

```bash
curl -X POST -H "Content-Type: application/json" -d '{"name": "My New Widget"}' http://127.0.0.1:8000/items
```

You should get `{"message": "Item 'My New Widget' created successfully!"}`. I can handle your requests with grace, you know.

## 4. Dynamic Shenanigans: Path Parameters

What if you want to get a specific item? We can use path parameters for that. Let's add a `GET /items/{item_id}` endpoint. Edit `routes/items.py`:

```python
# routes/items.py
from ushka import Request

async def post(request: Request):
    data = await request.json()
    item_name = data.get("name")
    if not item_name:
        return {"error": "Item name is required"}, 400
    return {"message": f"Item '{item_name}' created successfully!"}, 201

def get(item_id: str):
    # In a real app, you'd fetch this from a database
    return {"id": item_id, "name": f"Item {item_id}"}
```

Restart your app and try:

```bash
curl http://127.0.0.1:8000/items/fancy-sword-of-doom
```

And you'll get `{"id": "fancy-sword-of-doom", "name": "Item fancy-sword-of-doom"}`. See? Dynamic, just like me.

## You Did It! (Mostly Me)

Congratulations, you've built a simple API with Ushka. It wasn't so hard, was it? Now go forth and build amazing things. And remember who made it all possible. (UwU)
