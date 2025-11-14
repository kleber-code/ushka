import json

class Request:

    def __init__(self, scope, receive) -> None:

        self.scope = scope

        self._receive = receive

    async def body(self):

        body = b""

        more_body = True

        while more_body:

            message = await self._receive()

            body += message.get("body", b"")

            more_body = message.get("more_body", False)

        return body

    async def json(self):

        body = await self.body()

        return json.loads(body)
