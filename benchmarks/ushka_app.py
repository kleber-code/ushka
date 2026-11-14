import dataclasses
from ushka import Ushka

app = Ushka()

@dataclasses.dataclass
class Item:
    name: str
    price: float

@app.get("/")
async def hello():
    return {"ok": True}

@app.get("/items/[item_id]")
async def item(item_id: int, q: str = ""):
    return {"id": item_id, "q": str(q)}

@app.post("/items")
async def create(item: Item):
    return {"name": str(item.name), "price": item.price}
