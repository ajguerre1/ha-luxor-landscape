"""HTTP client for an FX Luminaire Luxor controller.

No Home Assistant imports. The session is injected so this runs under pytest on a machine where
Home Assistant cannot be imported at all; the integration passes Home Assistant's shared session.

Three properties are load-bearing and none of them are optional:

1. **One request in flight, ever.** The controller refuses a second concurrent request. A single
   lock is the only thing that serialises `light` against `scene`, because Home Assistant's
   `PARALLEL_UPDATES` semaphore is per platform.
2. **A method allowlist.** `IlluminateAll` sets every group to `Colr 0`, destroying the colour
   configuration this integration exists to provide. It is unreachable from here, along with every
   method that administers rather than controls.
3. **Client-side field validation.** The controller treats a missing field as a default rather
   than an error on at least three methods, so an under-specified request is a command, not a
   question.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import (
    ALLOWED_METHODS,
    DEFAULT_TIMEOUT,
    DENIED_METHODS,
    HUE_MAX,
    HUE_MIN,
    INTENSITY_MAX,
    INTENSITY_MIN,
    MAX_GROUP_NAME_BYTES,
    MIN_REQUEST_GAP,
    PALETTE_MAX,
    PALETTE_MIN,
    PARAMETERLESS_METHODS,
    REQUIRED_FIELDS,
    SATURATION_MAX,
    SATURATION_MIN,
    STATUS_OK,
)
from .errors import (
    ColourRangeError,
    EmptyBodyError,
    GroupNameError,
    IntensityRangeError,
    LuxorConnectionError,
    LuxorStatusError,
    MethodNotAllowedError,
)
from .model import Colour, Group, Theme, ThemeGroup

_LOGGER = logging.getLogger(__name__)


class LuxorClient:
    """Speaks the Luxor JSON-over-HTTP protocol, safely."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        min_gap: float = MIN_REQUEST_GAP,
    ) -> None:
        self._host = host.removeprefix("http://").removeprefix("https://").rstrip("/")
        self._session = session
        self._timeout = timeout
        self._min_gap = min_gap
        self._lock = asyncio.Lock()
        self._last_request: float = 0.0

    @property
    def host(self) -> str:
        return self._host

    # --- the one place a request is built ------------------------------------------------------

    async def request(self, method: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send one request, after proving it is one we are allowed to send.

        Every check here happens *before* the socket is touched, because on this controller an
        ill-formed request is not rejected -- it is interpreted.
        """
        if method in DENIED_METHODS:
            raise MethodNotAllowedError(
                f"{method} is denied by this integration: {DENIED_METHODS[method]}"
            )
        if method not in ALLOWED_METHODS:
            raise MethodNotAllowedError(
                f"{method} is not in the allowlist. Adding a method here is a deliberate act: "
                "read what it does to the controller first."
            )

        payload = dict(body or {})
        if not payload and method not in PARAMETERLESS_METHODS:
            raise EmptyBodyError(
                f"{method} requires {sorted(REQUIRED_FIELDS.get(method, frozenset()))} and was "
                "given nothing. This controller executes some methods on an empty body."
            )
        missing = REQUIRED_FIELDS.get(method, frozenset()) - payload.keys()
        if missing:
            raise EmptyBodyError(f"{method} is missing required field(s): {sorted(missing)}")

        async with self._lock:
            await self._pace()
            url = f"http://{self._host}/{method}.json"
            try:
                async with self._session.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json", "cache-control": "no-cache"},
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                ) as response:
                    response.raise_for_status()
                    # The controller answers with `Content-Type: text/html`, so aiohttp's own
                    # content-type check has to be disabled or every read raises.
                    data = await response.json(content_type=None)
            except TimeoutError as err:
                raise LuxorConnectionError(f"{method} timed out after {self._timeout}s") from err
            except aiohttp.ClientError as err:
                raise LuxorConnectionError(f"{method} failed: {err}") from err
            finally:
                self._last_request = time.monotonic()

        status = int(data.get("Status", -1))
        if status != STATUS_OK:
            # Never degraded into a fake success carrying stale cached data. The reference
            # Homebridge plugin does exactly that, which makes a failed write indistinguishable
            # from a successful one.
            raise LuxorStatusError(method, status)
        return data

    async def _pace(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if self._last_request and elapsed < self._min_gap:
            await asyncio.sleep(self._min_gap - elapsed)

    # --- reads ---------------------------------------------------------------------------------

    async def controller_name(self) -> str:
        return str((await self.request("ControllerName"))["Controller"])

    async def group_list(self) -> list[Group]:
        data = await self.request("GroupListGet")
        return [Group.from_json(raw) for raw in data.get("GroupList", [])]

    async def theme_list(self) -> list[Theme]:
        data = await self.request("ThemeListGet")
        return [Theme.from_json(raw) for raw in data.get("ThemeList", [])]

    async def themes_restricted(self) -> bool:
        """Whether theme writes are blocked at the controller's own setup menu.

        Checked at runtime rather than assumed: it is 0 on the reference controller today and can
        be changed on the faceplate, after which every theme write returns 252.
        """
        return int((await self.request("ThemeListGet")).get("Restricted", 0)) != 0

    async def theme_groups(self, theme_index: int) -> list[ThemeGroup]:
        """The theme's per-group intensity and colour. This is where colour actually lives."""
        data = await self.request("ThemeGet", {"ThemeIndex": theme_index})
        return [ThemeGroup.from_json(raw) for raw in data.get("Groups", [])]

    async def colour_list(self) -> list[Colour]:
        data = await self.request("ColorListGet")
        return [Colour.from_json(raw) for raw in data.get("ColorList", [])]

    async def colour_wheels(self) -> list[dict[str, Any]]:
        return list((await self.request("ColorWheelListGet")).get("CWList", []))

    # --- writes --------------------------------------------------------------------------------

    async def illuminate_group(self, group_number: int, intensity: int) -> None:
        if not INTENSITY_MIN <= intensity <= INTENSITY_MAX:
            raise IntensityRangeError(
                f"intensity {intensity} outside {INTENSITY_MIN}-{INTENSITY_MAX}"
            )
        await self.request("IlluminateGroup", {"GroupNumber": group_number, "Intensity": intensity})

    async def illuminate_theme(self, theme_index: int, on: bool) -> None:
        await self.request("IlluminateTheme", {"ThemeIndex": theme_index, "OnOff": 1 if on else 0})

    async def extinguish_all(self) -> None:
        """All off, in one request.

        Cleared by measurement on 2026-09-09 and not by reading: run from the ON state, with
        `IlluminateTheme(OnOff=0)` from the same on state as a control, it left every group's
        `Colr` untouched. The first attempt ran it against already-off lights, where it had
        nothing to change and proved nothing.
        """
        await self.request("ExtinguishAll")

    async def set_palette_colour(self, index: int, hue: int, saturation: int) -> None:
        """Define what a palette slot means.

        Must happen BEFORE anything is pointed at the slot. Point first and the group visibly
        lights in whatever the slot used to mean.
        """
        if not PALETTE_MIN <= index <= PALETTE_MAX:
            raise ColourRangeError(f"palette index {index} outside {PALETTE_MIN}-{PALETTE_MAX}")
        if not HUE_MIN <= hue <= HUE_MAX:
            raise ColourRangeError(f"hue {hue} outside {HUE_MIN}-{HUE_MAX}")
        if not SATURATION_MIN <= saturation <= SATURATION_MAX:
            raise ColourRangeError(
                f"saturation {saturation} outside {SATURATION_MIN}-{SATURATION_MAX}"
            )
        await self.request("ColorListSet", {"C": index, "Hue": hue, "Sat": saturation})

    async def set_theme_groups(self, theme_index: int, groups: list[ThemeGroup]) -> None:
        """Write a theme's complete membership.

        `Groups` is the whole theme, not a patch: a partial list is a claim about every group in
        it. Callers must read-modify-write, and this refuses an empty list because sending one
        would strip the theme rather than leave it alone.
        """
        if not groups:
            raise EmptyBodyError(
                "ThemeSet with an empty Groups list would empty the theme. Read the theme, modify "
                "the entry you mean, and send the whole list back."
            )
        await self.request(
            "ThemeSet",
            {"ThemeIndex": theme_index, "Groups": [group.to_json() for group in groups]},
        )

    async def point_group_at_colour(self, group_number: int, name: str, colour: int) -> None:
        """Point a group at a palette slot, so the colour applies now.

        **This is the only dangerous call in the integration.** `GroupListEdit` carries the name
        as a payload field and has no `OldName`, so every call is an unconditional rename. The
        name must come from a `GroupListGet` read taken inside the same operation, byte for byte,
        and never from the Home Assistant entity registry, which the user may have renamed.

        Collision checking is the caller's job, because it needs the whole group list; this
        enforces only what can be checked from one name.
        """
        if not name:
            raise GroupNameError("GroupListEdit requires a name; an empty one would clear it")
        encoded = len(name.encode("utf-8"))
        if encoded > MAX_GROUP_NAME_BYTES:
            raise GroupNameError(
                f"group name is {encoded} bytes, over the controller's {MAX_GROUP_NAME_BYTES}-byte "
                "cap; it would be silently truncated, possibly mid-character"
            )
        if not PALETTE_MIN <= colour <= PALETTE_MAX:
            raise ColourRangeError(f"palette index {colour} outside {PALETTE_MIN}-{PALETTE_MAX}")
        await self.request(
            "GroupListEdit", {"Name": name, "GroupNumber": group_number, "Color": colour}
        )
