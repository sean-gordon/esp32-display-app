# ESP32 Display

Install the matching display-only `esphome/esp32.yaml` first. It exposes a
three-character **Display value** text entity through the existing ESPHome
connection. Keep your existing Wi-Fi, API encryption and OTA secrets.

Start this app and open its web UI. Select the ESP32 Display value destination.
Enter a manual value and Send, use Clear, or choose Follow Home Assistant and
select a calculated sensor/helper. Settings are persisted automatically.

Allowed values: up to three digits or supported seven-segment letters. Integer
range is -99 to 999. Decimal points remain unconnected in the existing hardware.
Invalid/unavailable sources display Err. The app refreshes values every minute
by default and checks followed-source changes every five seconds.

The ESP32 shows Err after 180 seconds without display updates by default.
Upstream data freshness belongs in your Home Assistant calculation.

This app uses the Supervisor-provided API token and authenticated Home Assistant
ingress. It requires no separate token or MQTT configuration. The app must be
running to keep display values refreshed.
