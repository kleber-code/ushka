from .http.request import Request
from .http.response import Response
from .routing.router import Router


class Ushka:
    def __init__(self) -> None:
        self.router = Router()

    async def handle_http_request(self, scope, receive, send):
        request = Request(scope, receive)

        func, params = self.router.get_route(request)

        if callable(func):
            result = str(await func(**params))
            response = Response(result)
        else:
            response = Response("Not Found", 404)

        await response(send)

    async def handle_lifespan(self, receive, send):
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
            return

    async def handle_asgi_call(self, scope, receive, send):
        if scope["type"] == "http":
            await self.handle_http_request(scope, receive, send)

        elif scope["type"] == "lifespan":
            await self.handle_lifespan(receive, send)

        else:
            response = Response("Not Supported", 501)

            await response(send)

    async def __call__(self, scope, receive, send):
        await self.handle_asgi_call(scope, receive, send)
