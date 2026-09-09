"""Test doubles for an FX Luminaire Luxor ZDTWO.

READ THIS BEFORE TRUSTING A GREEN RUN.

Every response this simulator returns is a **captured** one, held in `tests/fixtures/`. The only
edit made to a capture is that group and theme names were replaced with generic ones and the
controller's serial was zeroed, because those are site data. Every number -- status codes, group
numbers, intensities, palette indices, hues, saturations, list sizes -- is exactly what the
hardware said on 2026-09-09.

That distinction is the point. A fixture is a claim about hardware, and a claim is only worth what
measured it. Twice in this workspace a device double has modelled a device more conveniently than
it behaves and the whole suite agreed with it.

| Modelled here | Evidence |
|---|---|
| `Status: 1` for a method the controller lacks | `SetHueSat.json`, probed live |
| an empty body EXECUTES on IlluminateAll, ExtinguishAll | all three answered `Status: 0` |
| and GroupListDelete | |
| IlluminateAll sets every group to `Inten 75`, `Colr 0` | isolated live; 75 matches the one |
| | published description |
| ExtinguishAll leaves `Colr` untouched | run from ON, against a control |
| a theme activation repaints every member group's `Colr` | theme 0 restored all 65 exactly |
| `GroupListEdit` with no name returns 201 | probed |
| a colliding group name returns 202 | names are a unique key |
| `ColorListSet` out of range returns 151 | probed |
| `IlluminateGroup` with no group returns 242 | probed |
| JSON arrives as `Content-Type: text/html` | observed |

What is NOT modelled, and must not be assumed by any test here: whether `GroupListDelete` also
wipes colour (untested by choice -- `IlluminateAll` accounts for the observed damage and the
integration denies `GroupListDelete` permanently), the controller's own astronomic schedule, and
anything about colour wheels beyond the list being empty.

The protocol package is placed on `sys.path` as a top-level `luxor` rather than reached through
`custom_components.luxor`. That is not a shortcut: importing the parent package would execute
`custom_components/luxor/__init__.py`, which will import Home Assistant once the platforms land and
therefore cannot run on Windows. It also enforces the separation structurally -- if a Home
Assistant import is ever added to `luxor/`, this suite stops collecting rather than passing on a
technicality.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "luxor"
if str(_PACKAGE) not in sys.path:
    sys.path.insert(0, str(_PACKAGE))

#: Skip the Home Assistant suite wherever Home Assistant cannot be imported, rather than letting it
#: fail collection. Detected rather than keyed to the platform: what matters is whether the
#: dependency is installed. The whole directory is ignored because pytest loads a conftest before
#: it applies any file-level ignore.
if importlib.util.find_spec("homeassistant") is None:
    collect_ignore = ["ha"]

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture(name: str) -> dict[str, Any]:
    """Load a captured response."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@dataclass
class Sent:
    """One request as it reached the wire."""

    method: str
    body: dict[str, Any]


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def json(self, content_type: str | None = None) -> dict[str, Any]:
        # `content_type=None` is how the client disables aiohttp's own check. The real controller
        # answers JSON with `Content-Type: text/html`, so a double that accepted only
        # `application/json` would hide a bug the hardware would show immediately.
        return self._payload


@dataclass
class FakeSession:
    """A session-shaped double that speaks the captured protocol.

    Deliberately stateful about the things that have side effects, because a stateless double
    cannot express the only interesting fact about this controller: that a theme activation and an
    `IlluminateAll` both rewrite every group's colour.
    """

    sent: list[Sent] = field(default_factory=list)
    #: Methods the controller does not implement. Answering `Status: 1` rather than raising is what
    #: the hardware does, and it is what makes a "does this exist?" probe indistinguishable from a
    #: command for methods that take no arguments.
    unknown: set[str] = field(default_factory=lambda: {"SetHueSat"})
    fail_with: dict[str, int] = field(default_factory=dict)
    raise_on: dict[str, Exception] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.groups = {g["Grp"]: dict(g) for g in fixture("group_list_get")["GroupList"]}
        self.themes = {t["ThemeIndex"]: dict(t) for t in fixture("theme_list_get")["ThemeList"]}
        self.theme_groups = {i: fixture(f"theme_get_{i}")["Groups"] for i in (0, 1, 2)}
        self.colours = {c["C"]: dict(c) for c in fixture("color_list_get")["ColorList"]}
        self.restricted = fixture("theme_list_get")["Restricted"]

    # --- the session surface the client uses ---------------------------------------------------

    def post(self, url: str, *, json: dict[str, Any], **_: Any) -> _Response:
        method = url.rsplit("/", 1)[-1].removesuffix(".json")
        self.sent.append(Sent(method, dict(json)))
        if method in self.raise_on:
            raise self.raise_on[method]
        return _Response(self._dispatch(method, json))

    # --- behaviour -----------------------------------------------------------------------------

    def _dispatch(self, method: str, body: dict[str, Any]) -> dict[str, Any]:
        if method in self.unknown:
            return {"Status": 1}
        if method in self.fail_with:
            return {"Status": self.fail_with[method]}
        handler = getattr(self, f"_do_{method}", None)
        if handler is None:
            return {"Status": 1}
        return handler(body)

    def _group_list(self) -> dict[str, Any]:
        return {"Status": 0, "GroupList": [dict(g) for g in self.groups.values()]}

    def _do_ControllerName(self, body: dict[str, Any]) -> dict[str, Any]:
        return fixture("controller_name")

    def _do_GroupListGet(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._group_list()

    def _do_ThemeListGet(self, body: dict[str, Any]) -> dict[str, Any]:
        return {
            "Status": 0,
            "Restricted": self.restricted,
            "ThemeList": [dict(t) for t in self.themes.values()],
        }

    def _do_ThemeGet(self, body: dict[str, Any]) -> dict[str, Any]:
        index = body["ThemeIndex"]
        if index not in self.theme_groups:
            return {"Status": 243}
        return {"Status": 0, "Groups": [dict(g) for g in self.theme_groups[index]]}

    def _do_ColorListGet(self, body: dict[str, Any]) -> dict[str, Any]:
        return {"Status": 0, "ListSize": 250, "ColorList": [dict(c) for c in self.colours.values()]}

    def _do_ColorWheelListGet(self, body: dict[str, Any]) -> dict[str, Any]:
        return fixture("color_wheel_list_get")

    def _do_IlluminateGroup(self, body: dict[str, Any]) -> dict[str, Any]:
        number = body.get("GroupNumber")
        if number not in self.groups:
            return {"Status": 242}
        self.groups[number]["Inten"] = body["Intensity"]
        return {"Status": 0}

    def _do_IlluminateTheme(self, body: dict[str, Any]) -> dict[str, Any]:
        index = body.get("ThemeIndex")
        if index not in self.themes:
            return {"Status": 251}
        on = body["OnOff"] == 1
        self.themes[index]["OnOff"] = 1 if on else 0
        # The measured behaviour, and the reason this integration writes the theme rather than the
        # group: activating a theme repaints every member group's colour.
        for entry in self.theme_groups[index]:
            group = self.groups.get(entry["GroupNumber"])
            if group is None:
                continue
            group["Colr"] = entry["Color"]
            group["Inten"] = entry["Intensity"] if on else 0
        return {"Status": 0}

    def _do_ExtinguishAll(self, body: dict[str, Any]) -> dict[str, Any]:
        # Intensity only. Colour is deliberately NOT touched -- proved from the ON state with a
        # control. Modelling it as destructive would be more "cautious" and would be a lie.
        for group in self.groups.values():
            group["Inten"] = 0
        for theme in self.themes.values():
            theme["OnOff"] = 0
        return {"Status": 0}

    def _do_IlluminateAll(self, body: dict[str, Any]) -> dict[str, Any]:
        # Present so the allowlist test can prove the client refuses it. If the guard ever breaks,
        # this is what would happen: every group to 75% and every colour assignment destroyed.
        for group in self.groups.values():
            group["Inten"] = 75
            group["Colr"] = 0
        return {"Status": 0}

    def _do_GroupListDelete(self, body: dict[str, Any]) -> dict[str, Any]:
        # Accepts an empty body and answers Ok, exactly as the hardware did. What it does beyond
        # that is untested, so this changes nothing -- the point is only that it does not refuse.
        return {"Status": 0}

    def _do_ColorListSet(self, body: dict[str, Any]) -> dict[str, Any]:
        index, hue, sat = body.get("C"), body.get("Hue"), body.get("Sat")
        if not (1 <= index <= 250) or not (0 <= hue <= 360) or not (0 <= sat <= 100):
            return {"Status": 151}
        self.colours[index] = {"C": index, "Hue": hue, "Sat": sat}
        return {"Status": 0}

    def _do_GroupListEdit(self, body: dict[str, Any]) -> dict[str, Any]:
        name, number, colour = body.get("Name"), body.get("GroupNumber"), body.get("Color")
        if not name or number is None:
            return {"Status": 201}
        if any(g["Name"] == name and g["Grp"] != number for g in self.groups.values()):
            return {"Status": 202}
        if number not in self.groups:
            return {"Status": 242}
        # Note that this renames. There is no OldName field; the name is not optional and not
        # advisory. A caller that passes the wrong string renames the group.
        self.groups[number]["Name"] = name
        self.groups[number]["Colr"] = colour
        return {"Status": 0}

    def _do_ThemeSet(self, body: dict[str, Any]) -> dict[str, Any]:
        index, groups = body.get("ThemeIndex"), body.get("Groups")
        if self.restricted:
            return {"Status": 252}
        if index not in self.theme_groups:
            return {"Status": 243}
        # A whole-theme write. Sending a partial list replaces the membership; it does not merge.
        self.theme_groups[index] = [dict(g) for g in groups]
        return {"Status": 0}


@pytest.fixture
def load_fixture():
    """The captured-response loader, as a fixture.

    `tests/` is a package, so a bare `from conftest import ...` does not resolve. Handing the
    loader out this way keeps the fixtures reachable without a sys.path trick.
    """
    return fixture


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def client(session: FakeSession):
    from luxor import LuxorClient

    # No pacing in tests. The gap is real behaviour and it is asserted explicitly in
    # test_client.py; leaving it on everywhere would add 50 ms to every request for no signal.
    return LuxorClient("192.0.2.10", session, min_gap=0.0)
