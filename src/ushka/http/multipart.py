from tempfile import SpooledTemporaryFile
from typing import TYPE_CHECKING, Any, Callable, Dict, Union

from python_multipart.multipart import MultipartParser as LowLevelParser
from python_multipart.multipart import parse_options_header

if TYPE_CHECKING:
    from ushka.http.request import Request
else:
    Request = None

from ushka.http.exceptions import HTTPBadRequest, HTTPPayloadTooLarge


class MultiPartCollector:
    def __init__(
        self,
        charset="utf-8",
        max_ram_size_kb=2048,
        max_file_size_kb=51200,
        max_text_field_size_kb=64,
    ):
        self.charset = charset
        self.form_data: Dict[str, Any] = {}
        self.files: Dict[str, Any] = {}

        self.max_ram_size = int(max_ram_size_kb * 1024)
        self.max_file_size = int(max_file_size_kb * 1024)
        self.max_text_size = int(max_text_field_size_kb * 1024)

        self._current_headers: Dict[str, bytes] = {}
        self._current_header_name: bytearray = bytearray()
        self._current_header_value: bytearray = bytearray()
        self._current_field_name: str = ""
        self._current_file: Union[SpooledTemporaryFile, None] = None
        self._is_file: bool = False
        self._data_buffer: bytearray = bytearray()

        self._current_part_size = 0

    def on_part_begin(self):
        self._current_headers = {}
        self._current_header_name = bytearray()
        self._current_header_value = bytearray()
        self._current_file = None
        self._is_file = False
        self._data_buffer = bytearray()
        self._current_part_size = 0

    def on_header_field(self, data: bytes, start: int, end: int):
        self._current_header_name.extend(data[start:end])

    def on_header_value(self, data: bytes, start: int, end: int):
        self._current_header_value.extend(data[start:end])

    def on_header_end(self):
        key = self._current_header_name.decode("latin-1").lower()
        self._current_headers[key] = bytes(self._current_header_value)
        self._current_header_name = bytearray()
        self._current_header_value = bytearray()

    def on_headers_finished(self):
        disposition_header = self._current_headers.get("content-disposition", b"")
        disposition, options = parse_options_header(disposition_header)

        self._current_field_name = options.get(b"name", b"").decode(self.charset)

        if b"filename" in options:
            self._is_file = True
            filename = options.get(b"filename", b"").decode(self.charset)
            content_type = self._current_headers.get(
                "content-type", b"application/octet-stream"
            ).decode("latin-1")

            self._current_file = SpooledTemporaryFile(
                max_size=self.max_ram_size, mode="w+b"
            )

            self.files[self._current_field_name] = {
                "filename": filename,
                "content_type": content_type,
                "file": self._current_file,
            }
        else:
            self._is_file = False

    def on_part_data(self, data: bytes, start: int, end: int):
        chunk_len = end - start

        self._current_part_size += chunk_len

        if self._is_file:
            # DISK ATTACK PROTECT
            if self._current_part_size > self.max_file_size:
                raise HTTPPayloadTooLarge(
                    f"File '{self._current_field_name}' exceeds limit of {self.max_file_size} bytes"
                )

            if self._current_file:
                self._current_file.write(data[start:end])
        else:
            # RAM ATTACK PROTECT
            if self._current_part_size > self.max_text_size:
                raise HTTPPayloadTooLarge(
                    f"Form field '{self._current_field_name}' exceeds limit of {self.max_text_size} bytes"
                )

            self._data_buffer.extend(data[start:end])

    def on_part_end(self):
        if self._is_file and self._current_file:
            self._current_file.seek(0)
        else:
            self.form_data[self._current_field_name] = self._data_buffer.decode(
                self.charset
            )

    def get_callbacks(self) -> Dict[str, Callable]:
        return {
            "on_part_begin": self.on_part_begin,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_part_data": self.on_part_data,
            "on_part_end": self.on_part_end,
        }


async def parse_multipart_asgi(request: Request, max_ram_kb=2048, max_disk_kb=51200):
    content_type = request.headers.get("content-type", "")

    ct_header, params = parse_options_header(content_type)
    boundary = params.get(b"boundary")
    if not boundary:
        raise HTTPBadRequest("Multipart Boundary Not Found")

    collector = MultiPartCollector(
        charset="utf-8", max_ram_size_kb=max_ram_kb, max_file_size_kb=max_disk_kb
    )

    parser = LowLevelParser(boundary, callbacks=collector.get_callbacks())

    try:
        async for chunk in request.stream():
            parser.write(chunk)
    except HTTPBadRequest as e:
        if collector._current_file:
            collector._current_file.close()
        raise e

    parser.finalize()

    return collector.form_data, collector.files
