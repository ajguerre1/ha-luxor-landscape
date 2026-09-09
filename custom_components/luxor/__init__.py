"""FX Luminaire Luxor landscape lighting.

Nothing is wired up yet. The protocol layer under `luxor/` is complete and tested; the Home
Assistant surface arrives with T8 onward. This module exists so hassfest and HACS can validate the
integration's shape, and so the first release is a skeleton rather than an untested platform.
"""

from __future__ import annotations

from .const import DOMAIN

__all__ = ["DOMAIN"]
