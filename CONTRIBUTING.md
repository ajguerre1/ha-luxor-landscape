# Contributing

Developer notes. For installation and day-to-day use, see the [README](README.md).

## Running the tests

The protocol package under `custom_components/luxor/luxor/` imports nothing from Home Assistant, so
it runs under pytest anywhere, including Windows:

```bash
pip install -r requirements-test.txt
sh scripts/preflight.sh     # ruff, the full suite, and the strings/translations diff
```

`scripts/preflight.sh` exits non-zero on any failure and is meant to gate a push. That matters more
than it sounds: the site-data guard below can only run where the denylist exists, so CI cannot catch
that class of problem, and a local check that does not block is not a check.

`tests/ha/` needs `pytest-homeassistant-custom-component`, which pulls in Home Assistant, which
cannot be imported on Windows. Those run in CI. The top-level `conftest.py` detects this and skips
the directory rather than failing collection. If a Home Assistant import ever drifts into the
protocol package, the offline suite stops collecting instead of quietly passing.

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

This integration reuses the `luxor` domain and, on first load, reproduced that project's `unique_id`
and device identifier schemes exactly, so replacing it preserved every entity id, device id and
area. From v0.2.0 those inherited schemes are converted in place to controller-scoped ones —
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

The same is true of brightness. A theme stores its own per-group intensity and re-applies it on
every run, which is why brightness is transient by default and `luxor.save_to_theme` exists.

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

`GroupListDelete` is permanently denied and stays untested by choice: testing it means deleting
someone's group, and the denial means nothing is bought by proving it works.

## Fixtures

**Every fixture in `tests/fixtures/` is a captured response**, not an invented one. The only edit is
that group and theme names were replaced with generic ones and the controller serial zeroed, because
those identify a specific property. Every number is exactly what the hardware returned. A fixture is
a claim about hardware, and inventing one makes the whole suite agree with a misreading.

## Brand images

Generated from FX Luminaire's own marks by `scripts/make_brand_assets.py`, which keys the lettering
off its navy background onto transparency and produces both polarities — near-black ink for a light
theme, the original white for a dark one.

The `dark_` variants are not optional decoration: the source is white-on-navy, and white lettering
measures **1.07:1** against Home Assistant's light card, which reads as no icon at all.
`tests/test_brand_assets.py` measures that rather than assuming it, and carries a disarmed control,
because legibility on both cards would also pass if the generator had written one image to both
names.

A local `brand/` directory is the only route for a custom integration. `home-assistant/brands`
explicitly refuses pull requests for custom components, so a 404 from `brands.home-assistant.io` is
normal and means nothing.

## Releases

HACS installs from the latest **release**, not from the default branch. Pushing to `main` reaches
nobody until a release is tagged, and the restart that appears to "fix" a missing update fails
silently. Bump the version in `custom_components/luxor/manifest.json` and tag.
