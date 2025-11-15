from .http.request import Request
from .http.response import Response
from .routing.router import Router
import uvicorn
from asyncio import iscoroutinefunction
import inspect


class Ushka:
    def __init__(self, app_path=None) -> None:
        # Get the path of the file that instantiated Ushka
        # stack()[1] refers to the caller's frame
        # .f_globals['__file__'] gets the __file__ attribute from that frame
        if app_path is None:
            app_path = inspect.stack()[1].frame.f_globals["__file__"]

        self.app_path = app_path
        self.router = Router(app_path)
        self.router.autodiscover()

    async def handle_http_request(self, scope, receive, send):
        request = Request(scope, receive)

        func, params = self.router.get_route(request)

        if callable(func):
            if iscoroutinefunction(func):
                result = await func(**params)
            else:
                result = func(**params)

            # check result type to auto detect media type (example html, text, json)

            if "<html>" in result:
                response = Response(result, media_type="text/html")
            else:
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

    def run(self, host="127.0.0.1", port=8000):
        print(f"Starting Ushka server on http://{host}:{port}")
        uvicorn.run(self, host=host, port=port)
