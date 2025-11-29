import linecache
import os
import traceback
from typing import Dict

SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "key",
    "auth",
    "credential",
    "pass",
    "cookie",
}


def safe_repr(obj, limit=200):
    try:
        value = repr(obj)

        if len(value) > limit:
            return value[:limit] + f"... <len={len(value)}>"
        return value

    except Exception as e:
        try:
            base_repr = object.__repr__(obj)
            return f"{base_repr} (repr failed: {e})"
        except Exception:
            return f"<{type(obj).__name__} instance @ ???>"


def get_safe_locals(frame) -> Dict[str, str]:
    safe_vars = {}

    try:
        for k, v in frame.f_locals.items():
            if any(s in k.lower() for s in SENSITIVE_KEYS):
                safe_vars[k] = "******** (Redacted for Security)"
                continue

            safe_vars[k] = safe_repr(v)

    except Exception:
        return {"<error>": "Could not inspect locals for this frame"}

    return safe_vars


def get_code_lines_context(filename, lineno: int, context=7):
    start = lineno - context
    end = lineno + context
    lines = []

    for i in range(start, end + 1):
        line = linecache.getline(filename, i)
        if not line:
            continue

        lines.append((i, line.rstrip("\n")))

    return lines


def get_copy_paste_traceback(exc: Exception):
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def extract_frames(exc: Exception):
    frame_blocks = []
    tb = exc.__traceback__

    while tb:
        frame = tb.tb_frame
        lineno = tb.tb_lineno
        code_obj = frame.f_code

        func_name = code_obj.co_name

        filename = os.path.relpath(code_obj.co_filename, os.getcwd())

        code_context = get_code_lines_context(filename, lineno)

        safe_locals = get_safe_locals(frame)

        frame_blocks.append(
            {
                "filename": filename,
                "lineno": lineno,
                "function_name": func_name,
                "code": code_context,
                "locals": safe_locals,
            }
        )

        tb = tb.tb_next

    return frame_blocks
