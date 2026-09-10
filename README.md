# FX Luminaire Luxor for Home Assistant

Control your FX Luminaire Luxor landscape lighting from Home Assistant.

Each of your light groups appears as a normal Home Assistant light, so you can turn it on and off,
dim it, and on colour-capable systems pick a colour. Your existing themes appear as scenes, and
there is a button to turn everything off.

Colour works the way you would expect it to: a colour you set stays set, including after your
controller's own sunset schedule runs.

Works with Luxor ZD, ZDC and ZDTWO controllers. Colour needs a ZDC or ZDTWO.

## Features

- **Your light groups as Home Assistant lights.** On, off and dimming for every group.
- **Colour**, on ZDC and ZDTWO systems. Pick a colour and it stays, evening after evening.
- **Your themes as scenes.** Activate any theme from Home Assistant, an automation or a dashboard.
- **An all-off button** for the whole system.
- **A save-to-theme action**, for when you want a brightness or colour change to be permanent.
- **Nothing to configure by hand.** Point it at your controller and it finds your groups and themes.

### A couple of things worth knowing

**Brightness resets each evening, and that is deliberate.** Your controller stores a brightness for
every group inside each theme, and re-applies it whenever that theme runs. So if you dim a light
from Home Assistant, the next scheduled evening brings it back to whatever the theme says. If you
want a change to stick, use the save action below. Colour is handled for you and needs none of this.

**To make a change permanent**, use the `Luxor: Save to theme` action. It takes the light's current
brightness and colour and writes them into a theme, so your controller's own schedule comes up that
way from then on.

```yaml
action: luxor.save_to_theme
target:
  entity_id: light.front_path
```

By default it saves into the theme chosen in the integration's options. You can point it at a
different theme if you want one light to differ from the rest. Choose carefully, because alarm
modes are themes too.

**There is no all-on button.** Luxor's own manual states the physical all-on control is off-only,
and the controller's all-on command wipes the colour settings for every group on the system.
Turning on a theme, or an individual group, does the job safely.

## Installation

You will need Home Assistant 2026.9.0 or newer, and a Luxor controller reachable on your network.

1. In HACS, open the three-dot menu and choose **Custom repositories**.
2. Add this repository, with category **Integration**.
3. Install it, then restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and search for **Luxor**.
5. Enter your controller's address when asked.

Your groups, themes and the all-off button appear automatically.

### If you are replacing the older `dcramer/hass-luxor`

The order matters here, and it is not the obvious one. Both versions install into the same folder,
and removing the old one deletes that folder, so anything you install first gets deleted with it.

1. **Add** this repository as a custom repository. This only registers it and writes no files.
   Do not install yet.
2. **Remove** the old integration in HACS.
3. **Now install** this one, then restart.

**Do not delete the Luxor entry under Settings at any point during this.** It is what keeps your
existing light names, history and dashboards working, and it survives the swap on its own.

Once you are past version 0.2.0, going back to the older integration is no longer supported, so take
a backup first if that matters to you.

## Uninstallation

1. Go to **Settings → Devices & services**, find **Luxor**, and delete it. This removes the lights,
   scenes and button from Home Assistant.
2. In HACS, find this integration and choose **Remove**.
3. Restart Home Assistant.

Nothing is changed on your controller. Your groups, themes and colours stay exactly as they are, and
your Luxor app and wall controller keep working as before.

## Troubleshooting

**The lights show as unavailable.**
Home Assistant cannot reach the controller. Check that it is powered on and on the network, and that
the address you entered is still correct. If your controller gets its address automatically, a
router restart can change it, so a fixed address is worth setting up.

**I cannot set a colour.**
Colour needs a ZDC or ZDTWO controller. On an original ZD the lights are dimmable only. If you do
have a colour-capable controller and one particular light still will not take a colour, that fixture
is most likely a plain white one.

**My brightness goes back to full every evening.**
That is expected, and it is your controller doing it rather than Home Assistant. See the note above,
and use the save action to make a level permanent.

**A colour changed back on its own.**
Colours are saved into a theme. If the theme that runs on your schedule is not the one this
integration is set to write, you will see exactly this. Check the theme selected under
**Settings → Devices & services → Luxor → Configure**.

**Setup fails when I add the integration.**
The controller speaks plain HTTP on port 80. Enter just the address, with no `https` and no port
number. It also handles one request at a time, so make sure nothing else is talking to it right then.

**I renamed a theme and its scene vanished.**
Restart Home Assistant and it will pick up the new name.

**Something else.**
Please open an issue, and include your controller model and what you were doing at the time. Turning
on debug logging for the integration first will make the report far more useful.

## Credits

This project builds on work by others and would not exist without it.

- [`dcramer/hass-luxor`](https://github.com/dcramer/hass-luxor) — the original Home Assistant
  integration, and the model this one follows so that switching over keeps your existing setup
  intact.
- [`tagyoureit/homebridge-luxor`](https://github.com/tagyoureit/homebridge-luxor) and
  [`tagyoureit/hubitat-luxor`](https://github.com/tagyoureit/hubitat-luxor) — the original
  reverse-engineering of how Luxor colour works.
- [`dcramer/luxor-openapi`](https://github.com/dcramer/luxor-openapi) — documentation of the
  controller's theme commands, which are what make lasting colour possible.
- [`scottlamb/luxor`](https://github.com/scottlamb/luxor) — protocol documentation for the ZD.

Not affiliated with or endorsed by FX Luminaire or Hunter Industries. FX Luminaire and the FX mark
are trademarks of Hunter Industries.

## Licence

MIT. See [LICENSE](LICENSE).
