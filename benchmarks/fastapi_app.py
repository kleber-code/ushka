from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.get("/")
async def hello():
    return {"ok": True}

@app.get("/items/{item_id}")
async def item(item_id: int, q: str = ""):
    return {"id": item_id, "q": q}

@app.post("/items")
async def create(item: Item):
    return {"name": item.name, "price": item.price}
