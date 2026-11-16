"""Parse a small multipart/form-data body entirely in memory.

FastAPI's `UploadFile` spools parts larger than 1 MB to a temporary file on disk. Visitor
audio must never be stored, so the voice endpoint reads the (size-capped) body itself and
parses it here with python-multipart's callback parser into memory.
"""

from dataclasses import dataclass, field

from python_multipart.multipart import MultipartParser, parse_options_header


class MultipartError(ValueError):
    pass


@dataclass
class Part:
    name: str
    filename: str | None = None
    content_type: str = ""
    chunks: list[bytes] = field(default_factory=list)

    @property
    def data(self) -> bytes:
        return b"".join(self.chunks)


def boundary_of(content_type: str) -> bytes:
    media_type, options = parse_options_header(content_type)
    boundary = options.get(b"boundary")
    if media_type != b"multipart/form-data" or not boundary:
        raise MultipartError("expected multipart/form-data with a boundary")
    return boundary


def parse_multipart(body: bytes, content_type: str, max_parts: int = 4) -> dict[str, Part]:
    boundary = boundary_of(content_type)
    parts: dict[str, Part] = {}
    headers: dict[bytes, bytes] = {}
    current: list[Part | None] = [None]
    header_field: list[bytes] = []
    header_value: list[bytes] = []

    def on_part_begin() -> None:
        headers.clear()

    def on_header_field(data: bytes, start: int, end: int) -> None:
        header_field.append(data[start:end])

    def on_header_value(data: bytes, start: int, end: int) -> None:
        header_value.append(data[start:end])

    def on_header_end() -> None:
        headers[b"".join(header_field).lower()] = b"".join(header_value)
        header_field.clear()
        header_value.clear()

    def on_headers_finished() -> None:
        disposition, options = parse_options_header(headers.get(b"content-disposition", b""))
        name = options.get(b"name")
        if disposition != b"form-data" or not name:
            raise MultipartError("each part needs a form-data name")
        key = name.decode("utf-8", "replace")
        if key in parts or len(parts) >= max_parts:
            raise MultipartError("duplicate or too many fields")
        filename = options.get(b"filename")
        part = Part(
            name=key,
            filename=filename.decode("utf-8", "replace") if filename is not None else None,
            content_type=headers.get(b"content-type", b"").decode("latin-1"),
        )
        parts[key] = part
        current[0] = part

    def on_part_data(data: bytes, start: int, end: int) -> None:
        if current[0] is not None:
            current[0].chunks.append(data[start:end])

    parser = MultipartParser(
        boundary,
        callbacks={
            "on_part_begin": on_part_begin,
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_headers_finished": on_headers_finished,
            "on_part_data": on_part_data,
        },
    )
    try:
        parser.write(body)
        parser.finalize()
    except MultipartError:
        raise
    except Exception as exc:  # python-multipart raises its own parse errors
        raise MultipartError("malformed multipart body") from exc
    return parts
