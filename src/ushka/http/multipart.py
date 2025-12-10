"""
This module provides utilities for parsing multipart/form-data requests,
commonly used for file uploads in web applications.

It includes the `MultiPartCollector` class, which acts as a callback handler
for a low-level multipart parser, and `parse_multipart_asgi` for integrating
with ASGI requests.
"""

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
    """Collects and processes data parts from a multipart HTTP request.

    This class acts as a callback handler for a low-level multipart parser,
    collecting form fields and files, and enforcing size limits to prevent
    denial-of-service attacks.
    """

    def __init__(
        self,
        charset="utf-8",
        max_ram_size_kb=2048,
        max_file_size_kb=51200,
        max_text_field_size_kb=64,
    ):
        """Initializes the MultiPartCollector.

        Parameters
        ----------
        charset : str, optional
            The character set to use for decoding field names and values.
            Defaults to "utf-8".
        max_ram_size_kb : int, optional
            The maximum size (in KB) a file part can occupy in RAM before
            being written to a temporary disk file. Defaults to 2048 KB.
        max_file_size_kb : int, optional
            The maximum allowed size (in KB) for any single file uploaded.
            Exceeding this raises `HTTPPayloadTooLarge`. Defaults to 51200 KB.
        max_text_field_size_kb : int, optional
            The maximum allowed size (in KB) for any non-file (text) field.
            Exceeding this raises `HTTPPayloadTooLarge`. Defaults to 64 KB.
        """
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
        """Callback invoked at the beginning of parsing a new multipart part.

        Resets internal state variables for the new part, including headers,
        field name, file status, and data buffers.
        """
        self._current_headers = {}
        self._current_header_name = bytearray()
        self._current_header_value = bytearray()
        self._current_file = None
        self._is_file = False
        self._data_buffer = bytearray()
        self._current_part_size = 0

    def on_header_field(self, data: bytes, start: int, end: int):
        """Callback invoked when a header field name is parsed.

        Appends the chunk of data to the `_current_header_name` buffer.

        Parameters
        ----------
        data : bytes
            The raw bytes of the header.
        start : int
            The starting index of the current chunk in `data`.
        end : int
            The ending index (exclusive) of the current chunk in `data`.
        """
        self._current_header_name.extend(data[start:end])

    def on_header_value(self, data: bytes, start: int, end: int):
        """Callback invoked when a header field value is parsed.

        Appends the chunk of data to the `_current_header_value` buffer.

        Parameters
        ----------
        data : bytes
            The raw bytes of the header.
        start : int
            The starting index of the current chunk in `data`.
        end : int
            The ending index (exclusive) of the current chunk in `data`.
        """
        self._current_header_value.extend(data[start:end])

    def on_header_end(self):
        """Callback invoked when a header field (name and value) has finished parsing.

        Stores the parsed header in `_current_headers` and resets buffers for the next header.
        """
        key = self._current_header_name.decode("latin-1").lower()
        self._current_headers[key] = bytes(self._current_header_value)
        self._current_header_name = bytearray()
        self._current_header_value = bytearray()

    def on_headers_finished(self):
        """Callback invoked when all headers for a part have been parsed.

        Determines if the part is a file based on 'content-disposition' and
        prepares the `_current_file` (SpooledTemporaryFile) or `_data_buffer`
        accordingly.
        """
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
        """Callback invoked when a chunk of data for a part is parsed.

        Appends the data chunk to the appropriate buffer (`_current_file` for
        files, `_data_buffer` for text fields) and enforces size limits.

        Parameters
        ----------
        data : bytes
            The raw bytes of the part data.
        start : int
            The starting index of the current chunk in `data`.
        end : int
            The ending index (exclusive) of the current chunk in `data`.

        Raises
        ------
        HTTPPayloadTooLarge
            If the part's size exceeds `max_file_size` (for files) or
            `max_text_size` (for text fields).
        """
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
        """Callback invoked when parsing of a multipart part has finished.

        If the part was a file, its temporary file handle is reset to the beginning.
        If it was a text field, its decoded value is stored in `form_data`.
        """
        if self._is_file and self._current_file:
            self._current_file.seek(0)
        else:
            self.form_data[self._current_field_name] = self._data_buffer.decode(
                self.charset
            )

    def get_callbacks(self) -> Dict[str, Callable]:
        """Returns a dictionary of callback functions for the multipart parser.

        These callbacks are used by the `python-multipart` library to process
        different events during the parsing of a multipart request.

        Returns
        -------
        Dict[str, Callable]
            A dictionary where keys are event names and values are the
            corresponding callback methods of this collector.
        """
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
    """Parses a multipart/form-data ASGI request.

    This asynchronous function processes the incoming request stream,
    collecting form fields and uploaded files, while enforcing configured size limits.

    Parameters
    ----------
    request : Request
        The incoming ASGI request object.
    max_ram_kb : int, optional
        The maximum size (in KB) a file part can occupy in RAM before
        being written to a temporary disk file. Defaults to 2048 KB.
    max_disk_kb : int, optional
        The maximum allowed size (in KB) for any single file uploaded.
        Exceeding this raises `HTTPPayloadTooLarge`. Defaults to 51200 KB.

    Returns
    -------
    tuple[dict, dict]
        A tuple containing two dictionaries:
        - `form_data`: Key-value pairs of standard form fields.
        - `files`: Key-value pairs of uploaded files, where values are dictionaries
          containing 'filename', 'content_type', and a `SpooledTemporaryFile` object.

    Raises
    ------
    HTTPBadRequest
        If the 'Content-Type' header is missing a boundary.
    HTTPPayloadTooLarge
        If any form field or file exceeds its configured size limit.
    """
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
