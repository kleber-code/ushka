from typing import Any, Dict, List

from ushka.core.exceptions import ContentToJsonParserFailed, ContentToTextParserFailed


class Response:
    def __init__(
        self, content: str | int | Dict | List = "", status_code=200, media_type=None
    ) -> None:
        self._content = ""

        self.status_code = status_code

        if media_type is None:
            self.content = content
        else:
            self._content = content
            self.media_type = media_type

    async def __call__(self, send):
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": [[b"content-type", self.media_type.encode()]],
            }
        )

        await send({"type": "http.response.body", "body": self.content.encode()})

    @property
    def content(self) -> str:
        return str(self._content)

    @content.setter
    def content(self, value: str | int | Dict[Any, Any] | List[Any]):
        if isinstance(value, str):
            if "<!DOCTYPE html>" in value:
                self.media_type = "text/html"
            else:
                self.media_type = "text/plain"

            try:
                self._content = str(value)
            except Exception as e:
                raise ContentToTextParserFailed(e)

        elif isinstance(value, Dict) or isinstance(value, List):
            self.media_type = "application/json"

            import json

            try:
                self._content = json.dumps(value)
            except Exception as e:
                raise ContentToJsonParserFailed(e)
