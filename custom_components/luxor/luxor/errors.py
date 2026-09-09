"""Errors raised by the Luxor protocol layer.

These deliberately do not inherit from anything in Home Assistant. This package has no Home
Assistant imports, which is what lets it be tested on a machine where Home Assistant cannot be
imported at all, and what would make contributing this integration to core a move rather than a
rewrite.
"""

from __future__ import annotations

from .const import STATUS_TEXT


class LuxorError(Exception):
    """Base class for every error this package raises."""


class LuxorConnectionError(LuxorError):
    """The controller could not be reached, or did not answer in time."""


class LuxorStatusError(LuxorError):
    """The controller answered, and refused.

    Carries the numeric status so a caller can branch on it. `Status: 1` in particular means the
    method does not exist on this controller, which is how the candidate integration's colour
    support was found to target an endpoint that is not there.
    """

    def __init__(self, method: str, status: int) -> None:
        self.method = method
        self.status = status
        text = STATUS_TEXT.get(status, "Unknown status")
        super().__init__(f"{method} returned status {status} ({text})")


class MethodNotAllowedError(LuxorError):
    """A method outside the allowlist was requested.

    Raised rather than sent. This is the guard that makes the 2026-09-09 incident unrepeatable
    from inside the integration: three methods on this controller execute on an empty body, so
    "just probing" is indistinguishable from commanding.
    """


class EmptyBodyError(LuxorError):
    """A request was about to be sent with no fields.

    The controller treats a missing field as a default rather than an error on at least three
    methods, so an empty body is never a safe way to ask a question.
    """


class GroupNameError(LuxorError, ValueError):
    """A group name that cannot be sent safely.

    `GroupListEdit` carries the name as a payload field with no `OldName`, so every call is an
    unconditional rename. A name that is empty, over the byte cap, or already used by another
    group would rename or collide rather than fail cleanly.
    """


class ColourRangeError(LuxorError, ValueError):
    """A hue, saturation or palette index outside the controller's range."""


class IntensityRangeError(LuxorError, ValueError):
    """An intensity outside 0-100."""
