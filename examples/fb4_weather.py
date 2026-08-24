# fb4_weather.py - self-playing weather display demo using fb4
# Shows animated weather conditions, temperature, forecast panels, and
# wind/humidity gauges with a cool blue sky palette. All data simulated.
import time
import random
import math
import fb4

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

# sky blue palette
fb.set_palette(0, 20, 30, 60)     # BG - dark sky
fb.set_palette(1, 220, 80, 60)    # RED
fb.set_palette(2, 80, 200, 80)    # GREEN
fb.set_palette(3, 60, 120, 220)   # BLUE
fb.set_palette(4, 240, 200, 60)   # YELLOW (sun)
fb.set_palette(5, 100, 200, 240)  # CYAN
fb.set_palette(8, 30, 35, 50)     # DGRAY
fb.set_palette(9, 230, 235, 240)  # WHITE
fb.set_palette(15, 100, 110, 130) # LGRAY

fb.set_palette(6, 50, 50, 70)     # 6 = cloud dark
fb.set_palette(7, 140, 150, 170)  # 7 = cloud light

# --- weather states ---
CONDITIONS = ["SUNNY", "PARTLY CLOUDY", "OVERCAST", "RAINY", "STORMY", "FOGGY", "SNOWY"]
CLOUD = 6
CLIGHT = 7

frame = 0
weather_idx = 0
weather_timer = 0
WEATHER_CYCLE = 300  # frames per weather change

# simulated data
temp = 22.0
humidity = 55
wind_dir = 0  # degrees
wind_speed = 12
pressure = 1013
uv_idx = 5
visibility = 10

# forecast: (condition, hi, lo)
forecast = [
    ("SUNNY", 28, 18),
    ("PARTLY", 26, 17),
    ("OVERCAST", 22, 15),
    ("RAINY", 19, 13),
    ("STORMY", 17, 12),
]

# cloud positions for animation
clouds = []
for i in range(6):
    clouds.append({
        'x': random.randint(0, 320),
        'y': random.randint(15, 55),
        'w': random.randint(20, 40),
        'speed': random.uniform(0.3, 1.0),
    })

# rain drops
rain = []
for i in range(30):
    rain.append([random.randint(0, 320), random.randint(60, 240), random.randint(2, 4)])

# snowflakes
snow = []
for i in range(40):
    snow.append([random.randint(0, 320), random.randint(60, 240), random.randint(1, 2)])

# lightning flash
lightning_timer = 0

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
        alpha_w = 60 + int(20 * math.sin(frame * 0.05 + i))
        fb.fill_rect(0, y, 320, 8, LGRAY)
        fb.fill_rect(0, y + 8, 320, 4, BG)

def draw_lightning():
    global lightning_timer
    lightning_timer -= 1
    if lightning_timer <= 0 and random.random() < 0.02:
        lightning_timer = 3
        x = random.randint(80, 240)
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
    # N S E W labels
    fb.text("N", cx - 2, cy - r - 8, col)
    fb.text("S", cx - 2, cy + r + 2, col)
    fb.text("E", cx + r + 2, cy - 2, col)
    fb.text("W", cx - r - 8, cy - 2, col)
    # needle
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

def draw_weather_icon(cx, cy, cond):
    if cond == "SUNNY" or cond == "SUN":
        draw_sun(cx, cy, 12, YELLOW)
    elif cond in ("PARTLY CLOUDY", "PARTLY"):
        draw_sun(cx - 10, cy - 5, 8, YELLOW)
        draw_cloud(cx + 8, cy, 28, CLOUD, CLIGHT)
    elif cond in ("OVERCAST", "CLOUDY"):
        draw_cloud(cx - 5, cy - 3, 35, CLOUD, CLIGHT)
        draw_cloud(cx + 10, cy + 4, 25, CLIGHT, CLOUD)
    elif cond in ("RAINY", "RAIN"):
        draw_cloud(cx, cy - 8, 35, CLOUD, CLIGHT)
        for dx in (-8, 0, 8):
            fb.line(cx + dx, cy + 8, cx + dx - 2, cy + 16, CYAN)
    elif cond in ("STORMY", "STORM"):
        draw_cloud(cx, cy - 8, 35, CLOUD, CLIGHT)
        fb.line(cx, cy + 5, cx - 3, cy + 14, YELLOW)
        fb.line(cx - 3, cy + 14, cx + 2, cy + 14, YELLOW)
        fb.line(cx + 2, cy + 14, cx - 1, cy + 20, YELLOW)
    elif cond in ("FOGGY", "FOG"):
        for dy in range(-8, 12, 5):
            fb.fill_rect(cx - 18, cy + dy, 36, 3, LGRAY)
    elif cond in ("SNOWY", "SNOW"):
        draw_cloud(cx, cy - 8, 30, CLOUD, CLIGHT)
        for dx in (-8, -2, 4, 10):
            fb.fill_rect(cx + dx, cy + 8, 2, 2, WHITE)
            fb.fill_rect(cx + dx + 3, cy + 14, 2, 2, WHITE)

# --- init ---
fb.fill(BG)
fb.show()

while True:
    weather_timer += 1
    if weather_timer >= WEATHER_CYCLE:
        weather_timer = 0
        weather_idx = (weather_idx + 1) % len(CONDITIONS)

    cond = CONDITIONS[weather_idx]

    # slowly drift values
    temp += random.uniform(-0.3, 0.3)
    temp = max(-5, min(40, temp))
    humidity = max(10, min(100, humidity + random.randint(-2, 2)))
    wind_dir = (wind_dir + random.randint(-10, 10)) % 360
    wind_speed = max(0, min(60, wind_speed + random.randint(-2, 2)))
    pressure = max(980, min(1050, pressure + random.randint(-1, 1)))

    fb.fill(BG)

    # top bar
    fb.fill_rect(0, 0, 320, 13, 15)
    fb.text("WEATHER STATION", 4, 2, BG)
    fb.text(cond, 200, 2, BG)

    # main weather icon
    draw_weather_icon(80, 50, cond)

    # temperature big
    temp_str = "{:.1f}".format(temp)
    fb.text(temp_str, 170, 30, WHITE)
    fb.text("C", 170 + len(temp_str) * 8 + 2, 30, CYAN)
    fb.text("H:{}%".format(humidity), 170, 46, CYAN)
    fb.text("W:{}km/h".format(wind_speed), 170, 58, GREEN)

    # animated rain/snow
    if cond in ("RAINY", "STORMY"):
        draw_rain_drops()
    elif cond == "SNOWY":
        draw_snow_flakes()
    elif cond == "FOGGY":
        draw_fog()

    # lightning flash
    if cond == "STORMY":
        draw_lightning()

    # divider
    fb.fill_rect(0, 88, 320, 1, LGRAY)

    # wind rose (compact)
    draw_wind_rose(35, 120, 20, wind_dir, CYAN)
    fb.text("{}km/h".format(wind_speed), 5, 153, WHITE)

    # humidity bar
    fb.text("HUM", 80, 93, WHITE)
    draw_mini_bar(80, 102, 16, 50, humidity, 100, CYAN)
    fb.text("{}%".format(humidity), 100, 120, WHITE)

    # pressure
    fb.text("HPA", 130, 93, WHITE)
    draw_mini_bar(130, 102, 16, 50, pressure - 980, 70, GREEN)
    fb.text("{}".format(pressure), 150, 120, WHITE)

    # UV index
    fb.text("UV", 180, 93, WHITE)
    uv_col = GREEN if uv_idx <= 5 else (YELLOW if uv_idx <= 7 else RED)
    draw_mini_bar(180, 102, 16, 50, uv_idx, 11, uv_col)
    fb.text(str(uv_idx), 200, 120, uv_col)

    # visibility
    fb.text("VIS", 225, 93, WHITE)
    draw_mini_bar(225, 102, 16, 50, visibility, 20, LGRAY)
    fb.text("{}km".format(visibility), 245, 120, WHITE)

    # divider
    fb.fill_rect(0, 168, 320, 1, LGRAY)

    # forecast strip - 5 days with inline icons
    fb.text("5-DAY FORECAST", 104, 176, WHITE)
    fw = 62
    for i, (fcond, fhi, flo) in enumerate(forecast):
        fx = 4 + i * fw
        fy = 208
        draw_weather_icon(fx + 14, fy, fcond)
        fb.text("{}/{}".format(fhi, flo), fx + 2, fy + 24, WHITE)

    fb.show()
    time.sleep_ms(150)
    frame += 1
