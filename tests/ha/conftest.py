"""Fixtures for the Home Assistant half of the suite.

These run in CI only. Home Assistant cannot be imported on Windows (`homeassistant.runner` imports
POSIX-only `fcntl`), and the top-level conftest skips this directory wherever it is not installed.

Empty for now: the Home Assistant platforms land in T8 onward. The directory exists so the split
is structural from the first commit rather than retrofitted, which is what stops a Home Assistant
import drifting into the protocol package.
"""

from __future__ import annotations
