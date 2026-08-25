# fb4_weather.py - self-playing weather display demo using fb4
# Connects to WiFi and shows real-time Melbourne weather from Open-Meteo.
# Shows animated weather conditions, temperature, forecast panels, and
# wind/humidity gauges with a cool blue sky palette.
import time
import random
import math
import network
import usocket
import ujson
import fb4
from wifi_secret import SSID, PASS

BG = 0
RED = 1
GREEN = 2
BLUE = 3
YELLOW = 4
CYAN = 5
WHITE = 9
DGRAY = 8
LGRAY = 15

fb = fb4.FB4()

# sky blue palette - high contrast
fb.set_palette(0, 10, 12, 24)     # BG - near black
fb.set_palette(1, 230, 70, 60)    # RED
fb.set_palette(2, 80, 210, 100)   # GREEN
fb.set_palette(3, 70, 130, 230)   # BLUE
fb.set_palette(4, 250, 210, 50)   # YELLOW (sun)
fb.set_palette(5, 80, 200, 240)   # CYAN
fb.set_palette(8, 60, 65, 80)     # DGRAY (gauges/borders)
fb.set_palette(9, 245, 245, 250)  # WHITE (primary text)
fb.set_palette(15, 140, 145, 160) # LGRAY (secondary text/dividers)
fb.set_palette(6, 55, 60, 80)     # 6 = cloud dark
fb.set_palette(7, 160, 165, 180)  # 7 = cloud light

CLOUD = 6
CLIGHT = 7

def wifi_connect():
    fb.fill(BG)
    fb.text("Connecting WiFi...", 80, 110, CYAN)
    fb.show()
    sta = network.WLAN(network.STA_IF)
    sta.active(False)
    time.sleep(1)
    sta.active(True)
    time.sleep(1)
    sta.connect(SSID, PASS)
    for i in range(30):
        if sta.isconnected():
            break
        time.sleep(1)
    if sta.isconnected():
        ip = sta.ifconfig()[0]
        fb.text("Connected!", 100, 110, GREEN)
        fb.text(ip, 100, 125, WHITE)
        fb.show()
        time.sleep(1)
        return True
    else:
        fb.text("WiFi FAILED", 100, 110, RED)
        fb.show()
        time.sleep(2)
        return False

# --- HTTP client ---
def http_get(host, path):
    ai = usocket.getaddrinfo(host, 80)
    addr = ai[0][4]
    s = usocket.socket()
    s.settimeout(15)
    s.connect(addr)
    s.write("GET {} HTTP/1.0\r\nHost: {}\r\n\r\n".format(path, host))
    resp = b""
    for i in range(40):
        chunk = s.read(256)
        if chunk:
            resp += chunk
        else:
            break
    s.close()
    # strip HTTP headers
    idx = resp.find(b"\r\n\r\n")
    if idx >= 0:
        resp = resp[idx + 4:]
    return resp

# --- WMO weather code mapping ---
def wmo_to_cond(code):
    if code == 0:
        return "SUNNY"
    elif code <= 3:
        return "PARTLY CLOUDY"
    elif code <= 49:
        return "FOGGY"
    elif code <= 59:
        return "RAINY"
    elif code <= 69:
        return "RAINY"
    elif code <= 79:
        return "SNOWY"
    elif code <= 82:
        return "RAINY"
    elif code <= 86:
        return "SNOWY"
    elif code <= 99:
        return "STORMY"
    return "OVERCAST"

def wmo_to_desc(code):
    if code == 0: return "Clear sky"
    if code <= 3: return "Partly cloudy"
    if code <= 49: return "Fog"
    if code <= 59: return "Drizzle"
    if code <= 69: return "Rain"
    if code <= 79: return "Snow"
    if code <= 82: return "Rain showers"
    if code <= 86: return "Snow showers"
    if code <= 99: return "Thunderstorm"
    return "Cloudy"

def fetch_weather():
    path = ("/v1/forecast?latitude=-37.8136&longitude=144.9631"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
            "weather_code,wind_speed_10m,wind_direction_10m,pressure_msl,"
            "uv_index,visibility"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min"
            "&timezone=Australia%2FMelbourne&forecast_days=5")
    try:
        raw = http_get("api.open-meteo.com", path)
        data = ujson.loads(raw)
        cur = data["current"]
        daily = data["daily"]
        result = {
            "temp": cur["temperature_2m"],
            "humidity": cur["relative_humidity_2m"],
            "feels_like": cur["apparent_temperature"],
            "cond": wmo_to_cond(cur["weather_code"]),
            "desc": wmo_to_desc(cur["weather_code"]),
            "wind_speed": cur["wind_speed_10m"],
            "wind_dir": cur["wind_direction_10m"],
            "pressure": cur["pressure_msl"],
            "uv": cur.get("uv_index", 0),
            "visibility": cur.get("visibility", 10000) / 1000,
            "forecast": [],
        }
        for i in range(5):
            fc = wmo_to_cond(daily["weather_code"][i])
            result["forecast"].append((
                fc,
                int(daily["temperature_2m_max"][i]),
                int(daily["temperature_2m_min"][i]),
            ))
        return result
    except Exception as e:
        fb.fill(BG)
        fb.text("API ERROR", 110, 105, RED)
        fb.text(str(e)[:30], 20, 120, WHITE)
        fb.show()
        time.sleep(3)
        return None

# --- weather display data ---
cond = "SUNNY"
temp = 22.0
humidity = 55
wind_dir = 0
wind_speed = 12
pressure = 1013
uv_idx = 5
visibility = 10
forecast = [
    ("SUNNY", 28, 18),
    ("PARTLY CLOUDY", 26, 17),
    ("OVERCAST", 22, 15),
    ("RAINY", 19, 13),
    ("STORMY", 17, 12),
]

# animated particles
rain = [[random.randint(0, 320), random.randint(60, 240), random.randint(2, 4)] for _ in range(30)]
snow = [[random.randint(0, 320), random.randint(60, 240), random.randint(1, 2)] for _ in range(40)]
lightning_timer = 0

# --- drawing functions ---
def draw_sun(cx, cy, r, col):
    fb.ellipse(cx, cy, r, r, col, 1)
    for i in range(8):
        angle = i * math.pi / 4
        sx = int(cx + (r + 4) * math.cos(angle))
        sy = int(cy + (r + 4) * math.sin(angle))
        ex = int(cx + (r + 10) * math.cos(angle))
        ey = int(cy + (r + 10) * math.sin(angle))
        fb.line(sx, sy, ex, ey, col)

def draw_cloud(cx, cy, w, col_dark, col_light):
    h = w // 3
    fb.fill_rect(cx - w // 2, cy, w, h, col_dark)
    fb.ellipse(cx - w // 4, cy, h // 2 + 2, h // 2 + 2, col_light, 1)
    fb.ellipse(cx + w // 6, cy - 2, h // 2 + 4, h // 2 + 4, col_light, 1)
    fb.ellipse(cx + w // 3, cy + 1, h // 2, h // 2, col_dark, 1)

def draw_rain_drops():
    for d in rain:
        d[1] += d[2] + 1
        if d[1] > 240:
            d[1] = 60
            d[0] = random.randint(0, 320)
        fb.line(d[0], d[1], d[0] - 1, d[1] + 4, CYAN)

def draw_snow_flakes():
    for s in snow:
        s[1] += s[2]
        s[0] += int(math.sin(frame * 0.1 + s[1] * 0.05))
        if s[1] > 240:
            s[1] = 60
            s[0] = random.randint(0, 320)
        fb.fill_rect(s[0], s[1], 2, 2, WHITE)

def draw_fog():
    for i in range(8):
        y = 70 + i * 20
        fb.fill_rect(0, y, 320, 8, LGRAY)
        fb.fill_rect(0, y + 8, 320, 4, BG)

def draw_lightning():
    global lightning_timer
    lightning_timer -= 1
    if lightning_timer <= 0 and random.random() < 0.02:
        lightning_timer = 3
        fb.fill_rect(0, 0, 320, 240, WHITE)
        fb.show()
        time.sleep_ms(50)
        return True
    if lightning_timer > 0:
        fb.fill_rect(0, 0, 320, 240, WHITE)
        fb.show()
        time.sleep_ms(30)
        return True
    return False

def draw_wind_rose(cx, cy, r, direction, col):
    fb.ellipse(cx, cy, r, r, DGRAY, 0)
    fb.text("N", cx - 2, cy - r - 8, col)
    fb.text("S", cx - 2, cy + r + 2, col)
    fb.text("E", cx + r + 2, cy - 2, col)
    fb.text("W", cx - r - 8, cy - 2, col)
    rad = math.radians(direction - 90)
    nx = int(cx + (r - 3) * math.cos(rad))
    ny = int(cy + (r - 3) * math.sin(rad))
    fb.line(cx, cy, nx, ny, col)
    fb.ellipse(nx, ny, 2, 2, col, 1)

def draw_mini_bar(x, y, w, h, val, max_val, col):
    fb.rect(x, y, w, h, DGRAY)
    fill_h = int(h * min(val, max_val) / max(max_val, 1))
    if fill_h > 0:
        fb.fill_rect(x + 1, y + h - fill_h, w - 2, fill_h, col)

def draw_weather_icon(cx, cy, c):
    if c == "SUNNY":
        draw_sun(cx, cy, 12, YELLOW)
    elif c == "PARTLY CLOUDY":
        draw_sun(cx - 10, cy - 5, 8, YELLOW)
        draw_cloud(cx + 8, cy, 28, CLOUD, CLIGHT)
    elif c == "OVERCAST":
        draw_cloud(cx - 5, cy - 3, 35, CLOUD, CLIGHT)
        draw_cloud(cx + 10, cy + 4, 25, CLIGHT, CLOUD)
    elif c == "RAINY":
        draw_cloud(cx, cy - 8, 35, CLOUD, CLIGHT)
        for dx in (-8, 0, 8):
            fb.line(cx + dx, cy + 8, cx + dx - 2, cy + 16, CYAN)
    elif c == "STORMY":
        draw_cloud(cx, cy - 8, 35, CLOUD, CLIGHT)
        fb.line(cx, cy + 5, cx - 3, cy + 14, YELLOW)
        fb.line(cx - 3, cy + 14, cx + 2, cy + 14, YELLOW)
        fb.line(cx + 2, cy + 14, cx - 1, cy + 20, YELLOW)
    elif c == "FOGGY":
        for dy in range(-8, 12, 5):
            fb.fill_rect(cx - 18, cy + dy, 36, 3, LGRAY)
    elif c == "SNOWY":
        draw_cloud(cx, cy - 8, 30, CLOUD, CLIGHT)
        for dx in (-8, -2, 4, 10):
            fb.fill_rect(cx + dx, cy + 8, 2, 2, WHITE)
            fb.fill_rect(cx + dx + 3, cy + 14, 2, 2, WHITE)

# --- init ---
fb.fill(BG)
fb.show()

connected = wifi_connect()
if connected:
    w = fetch_weather()
    if w:
        cond = w["cond"]
        temp = w["temp"]
        humidity = w["humidity"]
        wind_dir = w["wind_dir"]
        wind_speed = w["wind_speed"]
        pressure = int(w["pressure"])
        uv_idx = int(w["uv"])
        visibility = w["visibility"]
        forecast = w["forecast"]

frame = 0
FETCH_INTERVAL = 600  # re-fetch every ~90 seconds
fetch_timer = FETCH_INTERVAL - 10  # fetch quickly on first run

while True:
    # periodically re-fetch
    fetch_timer += 1
    if fetch_timer >= FETCH_INTERVAL and connected:
        fetch_timer = 0
        w = fetch_weather()
        if w:
            cond = w["cond"]
            temp = w["temp"]
            humidity = w["humidity"]
            wind_dir = w["wind_dir"]
            wind_speed = w["wind_speed"]
            pressure = int(w["pressure"])
            uv_idx = int(w["uv"])
            visibility = w["visibility"]
            forecast = w["forecast"]

    fb.fill(BG)

    # top bar
    fb.fill_rect(0, 0, 320, 13, 15)
    fb.text("MELBOURNE", 4, 2, BG)
    fb.text(cond, 200, 2, BG)

    # main weather icon
    draw_weather_icon(80, 50, cond)

    # temperature
    temp_str = "{:.1f}".format(temp)
    fb.text(temp_str, 170, 30, WHITE)
    fb.text("C", 170 + len(temp_str) * 8 + 2, 30, CYAN)
    fb.text("H:{}%".format(humidity), 170, 46, CYAN)
    fb.text("W:{}km/h".format(wind_speed), 170, 58, GREEN)

    # animated effects
    if cond in ("RAINY", "STORMY"):
        draw_rain_drops()
    elif cond == "SNOWY":
        draw_snow_flakes()
    elif cond == "FOGGY":
        draw_fog()
    if cond == "STORMY":
        draw_lightning()

    # divider
    fb.fill_rect(0, 88, 320, 1, LGRAY)

    # wind rose
    draw_wind_rose(35, 120, 20, wind_dir, CYAN)
    fb.text("{}km/h".format(wind_speed), 5, 153, WHITE)

    # humidity bar
    fb.text("HUM", 80, 93, WHITE)
    draw_mini_bar(80, 102, 16, 50, humidity, 100, CYAN)
    fb.text("{}%".format(humidity), 100, 120, WHITE)

    # pressure
    fb.text("HPA", 135, 93, WHITE)
    draw_mini_bar(135, 102, 16, 50, pressure - 980, 70, GREEN)
    fb.text("{}".format(pressure), 155, 120, WHITE)

    # UV index
    fb.text("UV", 190, 93, WHITE)
    uv_col = GREEN if uv_idx <= 5 else (YELLOW if uv_idx <= 7 else RED)
    draw_mini_bar(190, 102, 16, 50, uv_idx, 11, uv_col)
    fb.text(str(uv_idx), 210, 120, uv_col)

    # visibility
    fb.text("VIS", 245, 93, WHITE)
    draw_mini_bar(245, 102, 16, 50, visibility, 20, LGRAY)
    fb.text("{}km".format(int(visibility)), 265, 120, WHITE)

    # divider
    fb.fill_rect(0, 168, 320, 1, LGRAY)

    # forecast strip
    fb.text("5-DAY FORECAST", 104, 176, WHITE)
    iw = 56
    gap = (320 - 5 * iw) // 4
    for i, (fcond, fhi, flo) in enumerate(forecast):
        fx = i * (iw + gap)
        fy = 208
        draw_weather_icon(fx + iw // 2, fy, fcond)
        fb.text("{}/{}".format(fhi, flo), fx + 4, fy + 24, WHITE)

    fb.show()
    time.sleep_ms(150)
    frame += 1
