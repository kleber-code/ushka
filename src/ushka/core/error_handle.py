"""This module provides utilities for handling errors and tracebacks.

It includes functions for extracting detailed, yet safe, traceback information,
including code context and local variables. A key feature is the automatic
redaction of sensitive data (e.g., passwords, tokens) from local variables
to prevent them from being exposed in logs or debug pages.
"""

import linecache
import os
import traceback
from types import FrameType
from typing import Any, Dict, List, Tuple

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


def safe_repr(obj: Any, limit: int = 200) -> str:
    """Creates a safe string representation of an object.

    It truncates long representations and handles potential errors during the
    `repr()` call.

    Args:
        obj: The object to represent.
        limit: The maximum length of the string representation before
            truncation.

    Returns:
        A safe, string representation of the object.
    """
    try:
        value = repr(obj)

        if len(value) > limit:
            return str(value[:limit] + f"... <len={len(value)}>")
        return value
    except Exception as e:  # pylint: disable=broad-except
        try:
            base_repr = object.__repr__(obj)
            return f"{base_repr} (repr failed: {e})"
        except Exception as inner_e:  # pylint: disable=broad-except
            return f"<{type(obj).__name__} instance @ ???> (repr_fallback failed: {inner_e})"


def get_safe_locals(frame: FrameType) -> Dict[str, str]:
    """Retrieves local variables from a frame, redacting sensitive information.

    It inspects the local variables of a given frame and redacts any values
    whose keys match a list of sensitive keywords (e.g., 'password', 'token').

    Args:
        frame: The frame object to inspect.

    Returns:
        A dictionary of local variables with sensitive values redacted.
    """
    safe_vars = {}

    try:
        for k, v in frame.f_locals.items():
            if any(s in k.lower() for s in SENSITIVE_KEYS):
                safe_vars[k] = "******** (Redacted for Security)"
                continue

            safe_vars[k] = safe_repr(v)

    except Exception as e:  # pylint: disable=broad-except
        return {"<error>": f"Could not inspect locals for this frame: {e}"}

    return safe_vars


def get_code_lines_context(
    filename: str, lineno: int, context: int = 7
) -> List[Tuple[int, str]]:
    """Retrieves a block of code lines surrounding a specific line number.

    Args:
        filename: The path to the source file.
        lineno: The central line number to get context around.
        context: The number of lines to show before and after the central line.

    Returns:
        A list of tuples, where each tuple contains a line number and the
        corresponding line of code.
    """
    start = lineno - context
    end = lineno + context
    lines = []

    for i in range(start, end + 1):
        line = linecache.getline(filename, i)
        if not line:
            continue

        lines.append((i, line.rstrip("\\n")))

    return lines


def get_copy_paste_traceback(exc: Exception) -> str:
    """Formats an exception's traceback into a plain string.

    This is useful for creating a simple, copy-pasteable version of the
    traceback for logs or issue reports.

    Args:
        exc: The exception object.

    Returns:
        The formatted traceback as a single string.
    """
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def extract_frames(exc: Exception) -> List[Dict[str, Any]]:
    """Extracts detailed information from each frame of a traceback.

    This function walks through an exception's traceback and, for each frame,
    gathers the file path, line number, function name, code context, and a
    sanitized dictionary of local variables.

    Args:
        exc: The exception object.

    Returns:
        A list of dictionaries, where each dictionary represents a single
        frame from the traceback.
    """
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
                "filepath": filename,
                "line": lineno,
                "function_name": func_name,
                "context": code_context,
                "locals": safe_locals,
            }
        )

        tb = tb.tb_next

    return frame_blocks
