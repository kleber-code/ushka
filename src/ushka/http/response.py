class Response:
    def __init__(self, content, status_code=200, media_type="text/plain") -> None:

        self.content = content

        self.status_code = status_code

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
