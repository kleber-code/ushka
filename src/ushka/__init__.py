from .application import Ushka
from .http.request import Request
from .http.response import Response


app = Ushka()


async def hello():
    return "Hello"


app.router.add_route("GET", "/home", hello)
