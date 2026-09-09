# FX Luminaire Luxor for Home Assistant

Landscape lighting control for FX Luminaire **Luxor ZD, ZDC and ZDTWO** controllers, with per-light
colour that survives the controller's own nightly schedule.

> **Status: early. Not installable yet.**
> The protocol layer is complete and tested against captured hardware responses. The Home Assistant
> platforms are not written, so `manifest.json` declares `config_flow: false` and there is nothing
> to set up. Installing this today gets you a package that loads and does nothing. Watch the
> releases.

## Why another Luxor integration

There is an existing one, [`dcramer/hass-luxor`](https://github.com/dcramer/hass-luxor) (MIT), and
it works. This project exists because of one thing it cannot do and one thing it cannot stop doing:

- **It cannot set a colour.** Its I/O layer is a client generated from an OpenAPI document that has
  no colour operation at all. Colour is unreachable from that stack by construction.
- **It blocks the event loop twice per boot.** Its generated client builds an `ssl.SSLContext` in
  `async_setup_entry`, reading the CA bundle from disk. The controller is plain HTTP on port 80, so
  the TLS context is never used. The fix lives in an upstream library that last shipped in 2023.

It also passes a `via_device` kwarg that Home Assistant removes in 2027.8.0.

This integration reuses the `luxor` domain and reproduces that project's `unique_id` and device
identifier schemes exactly, so replacing it preserves every entity id, device id and area. That
compatibility is deliberate and it is owed to `dcramer/hass-luxor`, whose entity model this follows.

## The one thing worth knowing about Luxor colour

**A light group does not own its colour. The theme does.**

A group carries a `Colr`, which is an index into a shared 250-slot palette. But that index is not a
setting the group holds — it is whatever the last theme to run painted onto it. Every theme stores
its own per-group colour, and re-applies it on activation. On a controller with an astronomic
schedule, that happens every evening.

So an integration that writes colour at the group level produces a colour that works, looks correct
all evening, and is silently reverted at sunset. Both existing open-source Luxor projects do this;
the Homebridge plugin's own configuration calls the mode `"legacy behavior"` and defaults it off.

This integration writes the **theme**, then points the group at the same palette slot. The nightly
re-apply then writes the value that is already there, so it becomes a no-op instead of a fight.

## Safety

The controller executes some commands on an empty request body, because a method with no required
parameters has nothing to be missing. Finding out whether a method exists by calling it is therefore
indistinguishable from commanding it. This was learned the hard way, on real hardware.

The protocol client enforces two rules that make that unrepeatable:

- **A method allowlist.** Anything not explicitly permitted raises rather than being sent, and the
  refusal says why. `IlluminateAll` in particular is permanently denied: it sets every group to
  `Colr 0`, destroying the colour configuration across the whole system. There is no sanctioned
  all-on — the manual states the physical control is off-only. All-off uses `ExtinguishAll`, which
  was measured not to disturb colour.
- **Client-side field validation.** Every required field is checked before a socket is opened,
  because the controller treats a missing field as a default rather than an error.

`tests/test_allowlist.py` was written before the client it guards, and it asserts against what
reached the wire rather than against a return value.

## Requirements

- An FX Luminaire Luxor controller reachable over HTTP on your network. Colour needs a ZDC or ZDTWO.
- Home Assistant 2026.9.0 or newer.

## Installation

HACS → ⋮ → Custom repositories → add this repository, category **Integration** → install → restart.

If you are replacing `dcramer/hass-luxor`: **add this repository before removing that one**, verify
the files are on disk, then restart. Do not delete the config entry at any point — the entry is what
carries your entity ids, and it survives a HACS uninstall of the files.

## Development

The protocol package under `custom_components/luxor/luxor/` imports nothing from Home Assistant, so
it runs under pytest anywhere, including Windows:

```bash
pip install -r requirements-test.txt
pytest tests/ -v
ruff check . && ruff format --check .
```

`tests/ha/` needs `pytest-homeassistant-custom-component`, which pulls in Home Assistant, which
cannot be imported on Windows. Those run in CI. The top-level `conftest.py` detects this and skips
the directory rather than failing collection — and if a Home Assistant import ever drifts into the
protocol package, the offline suite stops collecting instead of quietly passing.

**Every fixture in `tests/fixtures/` is a captured response**, not an invented one. The only edit is
that group and theme names were replaced with generic ones and the controller serial zeroed, because
those identify a specific property. Every number is exactly what the hardware returned. A fixture is
a claim about hardware, and inventing one makes the whole suite agree with a misreading.

## Credits

- [`dcramer/hass-luxor`](https://github.com/dcramer/hass-luxor) (MIT) — the entity model, and the
  `unique_id` and device identifier schemes this integration reproduces for compatibility.
- [`tagyoureit/homebridge-luxor`](https://github.com/tagyoureit/homebridge-luxor) and
  [`tagyoureit/hubitat-luxor`](https://github.com/tagyoureit/hubitat-luxor) — the original
  reverse-engineering of the colour protocol, including the palette model and the status codes.
- [`dcramer/luxor-openapi`](https://github.com/dcramer/luxor-openapi) (Apache-2.0) — the request and
  response schemas, including `ThemeGet` and `ThemeSet`, which are what make durable colour possible.
- [`scottlamb/luxor`](https://github.com/scottlamb/luxor) — protocol documentation for the ZD.

Not affiliated with or endorsed by FX Luminaire or Hunter Industries.

## Licence

MIT.
