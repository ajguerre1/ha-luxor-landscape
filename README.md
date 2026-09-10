# FX Luminaire Luxor for Home Assistant

Landscape lighting control for FX Luminaire **Luxor ZD, ZDC and ZDTWO** controllers, with per-light
colour that survives the controller's own nightly schedule.

> **Status: running in production on one system since 2026-09-09.**
> Sixty-five light groups, three theme scenes and an all-off button on a ZDTWO, replacing
> `dcramer/hass-luxor` in place with no entity moved. Colour has been verified against a direct
> controller read and confirmed to survive a theme activation. One installation is one
> installation: treat it accordingly.

## Why another Luxor integration

There is an existing one, [`dcramer/hass-luxor`](https://github.com/dcramer/hass-luxor) (MIT), and
it works. This project exists because of one thing it cannot do and one thing it cannot stop doing:

- **It cannot set a colour.** Its I/O layer is a client generated from an OpenAPI document that has
  no colour operation at all. Colour is unreachable from that stack by construction.
- **It blocks the event loop twice per boot.** Its generated client builds an `ssl.SSLContext` in
  `async_setup_entry`, reading the CA bundle from disk. The controller is plain HTTP on port 80, so
  the TLS context is never used. The fix lives in an upstream library that last shipped in 2023.

It also passes a `via_device` kwarg that Home Assistant removes in 2027.8.0 — and, for the record,
this integration shipped that same defect in v0.1.0 before a live boot exposed it. Fixed in v0.1.1.

This integration reuses the `luxor` domain and, on first load, reproduces that project's `unique_id`
and device identifier schemes exactly, so replacing it preserves every entity id, device id and
area. From v0.2.0 those inherited schemes are then converted in place to controller-scoped ones —
`async_update_entity` and `async_update_device` change the scheme without moving the entity_id or
device_id. That compatibility is deliberate and it is owed to `dcramer/hass-luxor`, whose entity
model this follows.

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

**If you are replacing `dcramer/hass-luxor`, the order matters and it is not the obvious one.** Both
integrations use `custom_components/luxor/`, and HACS's uninstall deletes that directory wholesale —
so anything installed before the removal is deleted by it.

1. **Register** this repository as a custom repository. Registering writes no files. Do not install.
2. **Remove** `dcramer/hass-luxor`.
3. **Install** this one, then check the files are actually on disk before restarting.

**Do not delete the config entry at any point.** It is what carries your entity ids, and it survives
a HACS uninstall of the files. That is the entire mechanism.

**Rolling back is cheap until v0.2.0 and not afterwards.** v0.1.x leaves the inherited identity
untouched, so re-installing the old integration just works. v0.2.0 converts it, after which the old
integration would no longer recognise your entities.

## Development

The protocol package under `custom_components/luxor/luxor/` imports nothing from Home Assistant, so
it runs under pytest anywhere, including Windows:

```bash
pip install -r requirements-test.txt
sh scripts/preflight.sh     # ruff, the full suite, and the strings/translations diff
```

`scripts/preflight.sh` exits non-zero on any failure and is meant to gate a push. That matters more
than it sounds: the site-data guard below can only run where the denylist exists, so CI cannot catch
that class of problem and a local check that does not block is not a check.

`tests/ha/` needs `pytest-homeassistant-custom-component`, which pulls in Home Assistant, which
cannot be imported on Windows. Those run in CI. The top-level `conftest.py` detects this and skips
the directory rather than failing collection — and if a Home Assistant import ever drifts into the
protocol package, the offline suite stops collecting instead of quietly passing.

**Brand images** are generated from FX Luminaire's own marks by `scripts/make_brand_assets.py`,
which keys the lettering off its navy background onto transparency and produces both polarities —
near-black ink for a light theme, the original white for a dark one. The `dark_` variants are not
optional decoration: the source is white-on-navy, and white lettering measures **1.07:1** against
Home Assistant's light card, which reads as no icon at all. `tests/test_brand_assets.py` measures
that rather than assuming it.

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
