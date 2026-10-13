# ESP32 Display Home Assistant app

A Home Assistant app (formerly called an add-on) with its own web interface and
sidebar entry. Enter up to three characters manually, or select a Home Assistant
sensor/helper to follow. The ESP32 runs a display receiver: calculations, formatting
decisions and source freshness belong in Home Assistant. Its existing ESPHome
connection transports the result. There is no custom integration to install.

## Install the firmware first

1. Back up the working ESPHome YAML. Replace it in ESPHome Builder with
   `esphome/esp32.yaml` from this package. Keep your working Wi-Fi/API/OTA secrets;
   the required names are shown in `esphome/secrets.example.yaml`. Do not paste Python or Docker files
   into ESPHome Builder.
2. Keep the device name consistent with your own ESPHome device. If needed, add
   `wifi.use_address` locally using its current address; do not commit that address.
3. Disconnect display 12 V, run Validate, then Install. Existing ESPHome firmware
   allows a wireless update when reachable and the current OTA password matches.
4. Reconnect the ESPHome device in Home Assistant. The new firmware exposes a text
   entity named **Display value**, usually `text.esp32_display_value`. Find its
   actual entity ID on the ESPHome device page. It starts at Err until a value arrives.
5. Disable the old `update_outlook` automation if installed: that bank-payload API
   action is replaced by the generic Display value entity. Demo cycling is removed.

## Install the app

This package targets Home Assistant OS with Supervisor and an App store.

1. Unzip the package on your computer. Copy the **entire `esp32_display` folder**
   to the Home Assistant **`local_apps`** Samba share, or to `/local_apps` using
   the SSH app. The result must be `/local_apps/esp32_display/config.yaml`.
   Older installations may still label this local-app directory `addons`.
   Do not place it under `/config/custom_components` or `/config/esphome`.
2. Open **Settings > Apps > App store**. From the top-right menu choose
   **Check for updates**, then refresh the page. Find **ESP32 Display** under
   Local apps and click **Install**. The first install downloads the Python base
   image and builds the app, so Home Assistant needs internet access.
3. Click **Start**, enable **Start on boot**, and enable **Show in sidebar**.
   Click **Open Web UI** or its sidebar entry.
4. Select the ESP32 **Display value** destination. In **Manual value**, enter
   `123` and click **Send value**. **Test 888** lights all seven segments on each
   digit. **Clear display** sends an empty string and blanks all three digits.
5. For automatic updates, select **Follow Home Assistant**, choose your source
   sensor/helper and choose text or integer formatting. Click **Start following**.

The app uses Home Assistant's authenticated ingress and Supervisor-provided API
token. No long-lived access token, MQTT broker, host port, or bank credential is
required. Settings are saved under the app's persistent `/data` directory.

## Home Assistant owns the calculation

Create the desired sensor with a Template helper, automation, existing integration
or other Home Assistant calculation. Select that entity in the app. The app reads
its state every five seconds and sends changes, then renews unchanged values every
60 seconds by default. Integer mode rounds halves away from zero. In text mode,
the source must already contain the final display text.

An optional numeric template example is in `examples/template_sensor.yaml`.
Replace its source entity with your own and merge it into the existing `template:`
section; do not create a duplicate top-level key. The bank connector and financial
forecast calculation are outside this generic display app.

In manual mode the app keeps the entered value refreshed and resumes it after app
restart. Sending a manual value stops following the source. Follow mode sends Err
when the source is unavailable, too long, unsupported or out of numeric range.
The app does not infer whether a reachable source contains stale bank information:
your Home Assistant calculation must expose Err or unavailable for stale inputs.

## Display contract and unchanged wiring

Values have **0 to 3 characters**; empty means blank. Short values align right.
Values are never truncated. Integers fit from **-99 to 999**, including the minus.
Characters supported: digits, space, `-`, `_`, and letters **A B C D E F G H I J L
N O P R S T U Y** in either case. Seven-segment letters are approximations; B/D/N/R/T
look like lowercase b/d/n/r/t, G resembles 6 and S resembles 5.

| Function | GPIOs |
| --- | --- |
| Segments A B C D E F G | 13, 14, 16, 17, 18, 19, 21 |
| Left, middle, right digit switches | 25, 26, 27 |
| Physical button to GND | 32 |

This matches the supported three-digit breadboard layout and its active-HIGH
BC547/BC557 segment driver and 2N2222A digit switches. The physical button is exposed
to Home Assistant as a binary sensor for an automation; it no longer selects demo
states. The display supply, common ground and existing resistor network are unchanged.

Your **7S-018-BLU-CC** display has a decimal-point feature. The supplied layout
explicitly leaves DP **nc (not connected)**. This package leaves it that way and
rejects decimal points in values. Driving DP would require an additional segment
driver, current-limiting resistor selected for DP, an extra GPIO and firmware support.
The model's physical pins must be matched using its actual pinout; the drawing labels
segments by function rather than reproducing the 5-top/5-bottom package arrangement.

Use the existing external transistor drivers and base pull-downs. Never connect the
12 V rail to ESP32 power or GPIO pins. The vendor pinout resource is linked below.
This review does not verify breadboard continuity or transistor physical pinouts.

## Timeout and diagnostics

The scan task keeps running independently of Home Assistant/network activity.
At boot or after **180 seconds** without a valid received value it displays Err.
This timeout measures display delivery, not the freshness of upstream calculations.
The app refreshes even manual values while running, so they persist normally.
Set `display_timeout_seconds: '0'` in ESPHome and reinstall if you intentionally
want values held indefinitely. Keep the default for normal automatic use.

Set `single_segment_test: 'true'` and reinstall for the original one-segment
current measurement, then return it to false. Otherwise the display stays on
segment A regardless of app values. Do not use Test 888 until the driver wiring
and one-segment current have been checked.

The UI preview is **the last value sent**, not confirmation of electrical output.
Check the physical display and ESPHome entity to verify delivery. If no destination
appears, install this firmware, reconnect the ESPHome integration, then Reload entities.

## Validation

Thirteen Python tests pass: rendering limits/alignment, numeric boundaries, invalid
sources, manual/follow takeover, interval refresh, persistent restart, failed-send
recovery, ingress endpoints, authenticated REST delivery and exact agreement between
all app and firmware glyph masks. YAML is parsed with duplicate-key checks; the
browser JavaScript passes Node syntax checking. See `VALIDATION.md`.

Docker Desktop's Linux engine is not running here, so the app image was not built.
No Home Assistant Supervisor install, browser interaction or physical display test
has been performed. The new ESPHome YAML has not been compiled locally. The earlier
firmware's successful boot establishes the underlying board/task approach, but does
not verify this changed configuration. Run ESPHome Validate/Install and install the
app on Home Assistant to complete that verification.

## References

- [Home Assistant app installation tutorial](https://developers.home-assistant.io/docs/apps/tutorial/)
- [Home Assistant app configuration](https://developers.home-assistant.io/docs/apps/configuration/)
- [App-to-Home-Assistant API communication](https://developers.home-assistant.io/docs/apps/communication/)
- [ESPHome text entities](https://esphome.io/components/text/template/)
- [7S-018-BLU-CC product and pinout](https://www.robotics.org.za/7S-018-BLU-CC)
- [Vendor datasheet repository](https://github.com/microrobotics/7S-018-XXX-CC)
