import json
from urllib.parse import parse_qs

MAX_BODY = int(2.5 * 1024 * 1024)


class Request:
    def __init__(self, scope, receive):
        self.scope = scope
        self.method = str(scope["method"]).upper()
        self.path = str(scope["path"])
        self.headers = scope["headers"]

        self._receive = receive
        self._body = None
        self._text = None
        self._json = None
        self._query = None
        self._form = None

    async def _load_body(self):
        chunks = []
        size = 0

        while True:
            # TODO Upload Multipart
            msg = await self._receive()
            chunk = msg.get("body", b"")
            size += len(chunk)
            if size > MAX_BODY:
                raise ValueError("body too large")

            chunks.append(chunk)

            if not msg.get("more_body", False):
                break

        self._body = b"".join(chunks)
        return self._body

    async def body(self) -> bytes:
        if self._body is None:
            return await self._load_body()
        return self._body

    async def text(self) -> str:
        if self._text is None:
            self._text = (await self.body()).decode()
        return self._text

    async def json(self):
        if self._json is None:
            self._json = await json.loads(await self.body())
        return self._json

    async def query(self):
        if self._query is None:
            raw = self.scope.get("query_string", b"")
            parsed = parse_qs(raw.decode())

            self._query = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        return self._query

    async def form(self):
        # TODO Multipart form
        if self._form is None:
            body = await self.body()
            parsed = parse_qs(body.decode())
            self._form = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        return self._form
