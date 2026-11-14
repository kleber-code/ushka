"""OpenAPI generated from handler signatures."""

import dataclasses
import json
from enum import Enum
from typing import Annotated, Optional

from ushka import Depends, Field, Header, Query


class Color(Enum):
    red = "red"


@dataclasses.dataclass
class Item:
    name: Annotated[str, Field(min_length=2)]
    price: float
    color: Optional[Color] = None


async def test_document_describes_paths_parameters_and_bodies(app, call):
    def auth(x_token: str = Header()):
        pass

    @app.get("/items/[item_id]")
    async def read(item_id: int, page: Annotated[int, Query(ge=1)] = 1, _=Depends(auth)):
        """Read one item.

        Longer text."""

    @app.post("/items")
    async def create(item: Item):
        return item

    doc = app.openapi(title="T", version="2")
    assert doc["openapi"] == "3.1.0" and doc["info"] == {"title": "T", "version": "2"}

    get = doc["paths"]["/items/{item_id}"]["get"]
    assert get["summary"] == "Read one item." and get["description"] == "Longer text."
    params = {(p["in"], p["name"]): p for p in get["parameters"]}
    assert params[("path", "item_id")] == {"name": "item_id", "in": "path", "required": True, "schema": {"type": "integer"}}
    assert params[("query", "page")]["schema"] == {"type": "integer", "minimum": 1} and not params[("query", "page")]["required"]
    assert params[("header", "x-token")]["required"] is True  # from the Depends

    body = doc["paths"]["/items"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body == {"$ref": "#/components/schemas/Item"}
    item = doc["components"]["schemas"]["Item"]
    assert item["required"] == ["name", "price"]
    assert item["properties"]["name"] == {"type": "string", "minLength": 2}
    assert item["properties"]["color"]["anyOf"][1] == {"type": "null"}
    assert doc["components"]["schemas"]["Color"] == {"enum": ["red"]}
    assert doc["paths"]["/items"]["post"]["responses"]["422"]


async def test_enable_openapi_serves_json_and_hides_itself(app, call):
    @app.get("/ping")
    async def ping():
        return "pong"

    app.enable_openapi()
    res = await call(app, "GET", "/openapi.json")
    doc = json.loads(res["body"])
    assert res["status"] == 200 and "/ping" in doc["paths"] and "/openapi.json" not in doc["paths"]


async def test_openapi_is_off_until_enabled(app, call):
    @app.get("/ping")
    async def ping():
        return "pong"

    assert (await call(app, "GET", "/openapi.json"))["status"] == 404
