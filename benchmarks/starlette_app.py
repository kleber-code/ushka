from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

async def hello(request):
    return JSONResponse({"ok": True})
async def item(request):
    return JSONResponse({"id": int(request.path_params["item_id"]), "q": request.query_params.get("q", "")})
async def create(request):
    d = await request.json()
    return JSONResponse({"name": d["name"], "price": float(d["price"])})

app = Starlette(routes=[Route("/", hello), Route("/items/{item_id}", item), Route("/items", create, methods=["POST"])])
