import json
from urllib.parse import parse_qs
from typing import Any, Dict

MAX_BODY = int(2.5 * 1024 * 1024)

class Request:
    def __init__(self, scope, receive):
        self.scope = scope
        self.method = str(scope["method"]).upper()
        self.path = str(scope["path"])
            
        self._receive = receive
        
        # Cache interno
        self._headers = None
        self._body = None
        self._text = None
        self._json = None
        self._query = None
        self._form = None


    @property
    def headers(self) -> Dict[str, str]:
        if self._headers is None:
            self._headers = {
                k.decode("latin-1"): v.decode("latin-1") 
                for k, v in self.scope["headers"]
            }
        return self._headers

    @property
    def query(self) -> Dict[str, Any]:
        if self._query is None:
            raw = self.scope.get("query_string", b"")
            parsed = parse_qs(raw.decode())
            self._query = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        return self._query


    async def _load_body(self):
        chunks = []
        size = 0
        while True:
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
    
    @property
    async def body(self) -> bytes:
        if self._body is None:
            return await self._load_body()
        return self._body

    @property
    async def text(self) -> str:
        if self._text is None:
            self._text = (await self.body).decode()
        return self._text

    @property
    async def json(self):
        if self._json is None:
            body_data = await self.body
            self._json = json.loads(body_data) 
        return self._json

    @property
    async def form(self):
        if self._form is None:
            body = await self.body
            parsed = parse_qs(body.decode())
            self._form = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        return self._form
