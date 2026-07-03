# Weather widget

Time: 30 minutes. Difficulty: Intermediate.

A borderless rounded-rect widget that shows the current temperature
and a 6-hour forecast for your location. Demonstrates async data
fetching, periodic refresh, and a glass-card layout.

## Prerequisites

- `pip install elysium-ui`.
- Walked through [Aurora Clock](../getting-started/aurora-clock-01-window.md)
  at least once.

We use the public `Open-Meteo` API; no key required.

## Window

```python
import elysium as ely

ROUNDED = (
    "M 24,0 L 296,0 A 24,24 0 0 1 320,24 "
    "L 320,176 A 24,24 0 0 1 296,200 "
    "L 24,200 A 24,24 0 0 1 0,176 "
    "L 0,24 A 24,24 0 0 1 24,0 Z"
)

app = ely.App(title="Weather", identifier="dev.example.weather")
window = app.window(
    transparent=True, title_bar=False, resizable=False,
    initial_size=(320, 200),
    level=3,
)
window.set_hit_test_path(ROUNDED)
```

## Skin

`weather.esk/document.json`:

```json
{
  "placements": [
    { "id": "card", "kind": "rounded_rect",
      "x": 0, "y": 0, "width": 320, "height": 200,
      "radius": 24, "material": "glass-dark", "fill": "#1e1b4be0" },
    { "id": "city", "kind": "label",
      "x": 0, "y": 16, "width": 320, "height": 18,
      "text": " ", "font_size": 13, "fill": "#c4b5fdff", "align": "center" },
    { "id": "temp", "kind": "label",
      "x": 0, "y": 40, "width": 320, "height": 72,
      "text": " °", "font_size": 60, "fill": "#ffffffff", "align": "center" },
    { "id": "summary", "kind": "label",
      "x": 0, "y": 116, "width": 320, "height": 16,
      "text": "loading…", "font_size": 11, "fill": "#a78bfaff", "align": "center" },
    { "id": "forecast", "kind": "canvas",
      "x": 16, "y": 140, "width": 288, "height": 44 }
  ]
}
```

Load:

```python
from pathlib import Path
window.load_skin(str(Path(__file__).parent / "weather.esk"))
```

## Fetch the data

Use `webview` to fetch JSON without needing `requests` in the
bundle:

```python
from elysium.webview import WebView
import asyncio, json

CITY = "Lisbon"
LAT, LON = 38.7223, -9.1393   # Lisbon

URL = (f"https://api.open-meteo.com/v1/forecast"
       f"?latitude={LAT}&longitude={LON}"
       f"&current=temperature_2m,weather_code"
       f"&hourly=temperature_2m,weather_code&forecast_days=1")


async def fetch_weather():
    # Use the framework's tiny HTTP helper (under the hood: urllib).
    import urllib.request
    data = await asyncio.to_thread(
        lambda: json.loads(urllib.request.urlopen(URL).read()))
    return data
```

For complex APIs (auth headers, retries), reach for the WebView's
JS bridge or add `httpx` to your bundle.

## Render

```python
from elysium.reactive import signal, effect
import elysium as ely

current = signal({"temp": None, "code": None})
hourly  = signal([])


def code_summary(code):
    return {
        0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 51: "Light drizzle", 61: "Light rain", 63: "Rain",
        71: "Light snow", 80: "Showers", 95: "Thunderstorm",
    }.get(code, " ")


@effect
def push_current():
    c = current()
    if c["temp"] is None:
        return
    window.city.text = CITY
    window.temp.text = f"{c['temp']:.0f}°"
    window.summary.text = code_summary(c["code"])


@effect
def push_forecast():
    hours = hourly()
    if not hours:
        return
    dl = ely.DisplayList()
    n = min(6, len(hours))
    bar_w = 288 / n
    base_y = 36
    min_t = min(h["temp"] for h in hours[:n])
    max_t = max(h["temp"] for h in hours[:n])
    rng = (max_t - min_t) or 1
    path = ely.Path()
    for i, h in enumerate(hours[:n]):
        x = i * bar_w + bar_w / 2
        y = 4 + (max_t - h["temp"]) / rng * 24
        (path.move_to if i == 0 else path.line_to)(x, y)
    dl.stroke_color((1.0, 0.69, 0.99, 1.0))     # pink
    dl.stroke_width(2.0)
    dl.stroke_path(path)
    window.forecast.publish_display_list(dl)
```

## Refresh loop

```python
async def refresh_loop():
    while True:
        try:
            data = await fetch_weather()
            current.set({
                "temp": data["current"]["temperature_2m"],
                "code": data["current"]["weather_code"],
            })
            hourly.set([
                {"temp": t, "code": c}
                for t, c in zip(
                    data["hourly"]["temperature_2m"][:6],
                    data["hourly"]["weather_code"][:6],
                )
            ])
        except Exception as e:
            print("fetch failed:", e)
        await asyncio.sleep(300)    # 5 minutes


asyncio.get_event_loop().create_task(refresh_loop())
```

## Run

```python
app.run()
```

The widget loads " °" then fills in once the first fetch returns;
refreshes every 5 minutes.

## Ship

```sh
elysium pack weather.py --name "Weather" \
  --identifier dev.example.weather --include weather.esk
```

## Variations

- Auto-detect location via the OS (`platform.get_location()`  
  requires user permission on macOS).
- Add a forecast graph for the next 24 hours instead of 6.
- Theme-switch on sunrise / sunset using the API's daylight data.

## See also

- [WebView guide](../guides/webview.md): for API auth and richer
  data sources.
- [Recipes: long task without blocking](../recipes/23-long-task-without-blocking.md)
- [Rendering guide](../guides/rendering.md)
