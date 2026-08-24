# fb4_dashboard1.py - self-playing system dashboard demo using fb4
# Displays animated gauges, bar charts, and scrolling metrics on a dark
# background. All values are simulated and update continuously.
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
GRAY = 15
DGRAY = 8

fb = fb4.FB4()

# cool blue tech palette
fb.set_palette(0, 10, 10, 20)     # BG - dark navy
fb.set_palette(1, 200, 50, 50)    # RED
fb.set_palette(2, 50, 200, 80)    # GREEN
fb.set_palette(3, 40, 80, 200)    # BLUE
fb.set_palette(4, 220, 180, 50)   # YELLOW
fb.set_palette(5, 50, 200, 220)   # CYAN
fb.set_palette(8, 40, 40, 55)     # DGRAY
fb.set_palette(9, 220, 220, 230)  # WHITE
fb.set_palette(15, 80, 80, 100)   # GRAY

# simulated metrics
cpu_hist = [0] * 40
mem_hist = [0] * 40
net_in = 0
net_out = 0
temp = 42.0
uptime_s = 0
tasks = 0

def draw_gauge(cx, cy, r, val, max_val, col, label):
    fb.text(label, cx - len(label) * 4, cy - r - 14, WHITE)
    # draw arc background and filled portion using line segments
    sa = math.radians(-45)
    ea = math.radians(225)
    # outline arc
    n = 20
    for i in range(n):
        a1 = sa + (ea - sa) * i / n
        a2 = sa + (ea - sa) * (i + 1) / n
        x1 = int(cx + r * math.cos(a1))
        y1 = int(cy + r * math.sin(a1))
        x2 = int(cx + r * math.cos(a2))
        y2 = int(cy + r * math.sin(a2))
        fb.line(x1, y1, x2, y2, DGRAY)
    # filled arc up to value
    end_a = sa + (ea - sa) * min(val, max_val) / max(max_val, 1)
    for i in range(n):
        a1 = sa + (ea - sa) * i / n
        a2 = sa + (ea - sa) * (i + 1) / n
        if a1 > end_a:
            break
        x1 = int(cx + r * math.cos(a1))
        y1 = int(cy + r * math.sin(a1))
        x2 = int(cx + r * math.cos(min(a2, end_a)))
        y2 = int(cy + r * math.sin(min(a2, end_a)))
        fb.line(x1, y1, x2, y2, col)
    fb.text(str(int(val)), cx - 8, cy + r + 4, col)

def draw_bar(x, y, w, h, val, max_val, col, label):
    fb.text(label, x, y - 10, WHITE)
    fb.rect(x, y, w, h, DGRAY)
    fill_w = int(w * min(val, max_val) / max(max_val, 1))
    if fill_w > 0:
        fb.fill_rect(x + 1, y + 1, fill_w - 1, h - 2, col)
    fb.text(str(int(val)), x + w + 3, y + 2, col)

def draw_line_chart(x, y, w, h, data, col):
    fb.rect(x, y, w, h, DGRAY)
    if len(data) < 2:
        return
    n = len(data)
    step = w / max(n - 1, 1)
    mx = max(max(data), 1)
    prev_x = x
    prev_y = y + h - 1
    for i in range(n):
        px = int(x + i * step)
        py = int(y + h - 1 - (data[i] / mx) * (h - 2))
        fb.line(prev_x, prev_y, px, py, col)
        prev_x = px
        prev_y = py

def draw_sparkline(x, y, w, data, col):
    if len(data) < 2:
        return
    mx = max(max(data), 1)
    step = w / max(len(data) - 1, 1)
    prev_x = x
    prev_y = y + 5 - int(data[0] / mx * 5)
    for i in range(1, len(data)):
        px = int(x + i * step)
        py = y + 5 - int(data[i] / mx * 5)
        fb.line(prev_x, prev_y, px, py, col)
        prev_x = px
        prev_y = py

# header divider
fb.fill(BG)
fb.fill_rect(0, 0, 320, 1, GRAY)
fb.fill_rect(0, 13, 320, 1, GRAY)
fb.text("SYSTEM MONITOR", 4, 2, CYAN)
fb.show()

frame = 0
while True:
    # simulate values
    cpu = 35 + 25 * math.sin(frame * 0.07) + random.randint(-5, 5)
    cpu = max(0, min(100, cpu))
    mem = 55 + 15 * math.sin(frame * 0.03) + random.randint(-3, 3)
    mem = max(0, min(100, mem))
    net_in = max(0, int(45 + 30 * math.sin(frame * 0.11) + random.randint(-10, 10)))
    net_out = max(0, int(20 + 15 * math.sin(frame * 0.09) + random.randint(-8, 8)))
    temp = 38 + 8 * math.sin(frame * 0.05) + random.uniform(-1, 1)
    uptime_s += 1
    tasks = int(12 + 6 * math.sin(frame * 0.13))

    cpu_hist.append(cpu)
    cpu_hist.pop(0)
    mem_hist.append(mem)
    mem_hist.pop(0)

    fb.fill(BG)

    # header
    fb.fill_rect(0, 0, 320, 1, GRAY)
    fb.fill_rect(0, 13, 320, 1, GRAY)
    fb.text("SYSTEM MONITOR", 4, 2, CYAN)

    # uptime
    hrs = uptime_s // 3600
    mins = (uptime_s % 3600) // 60
    secs = uptime_s % 60
    ut = "{}:{:02d}:{:02d}".format(hrs, mins, secs)
    fb.text("UP " + ut, 220, 2, GREEN)

    # row 1: gauges (CPU, MEM, TEMP)
    draw_gauge(55, 70, 28, cpu, 100, CYAN, "CPU%")
    draw_gauge(160, 70, 28, mem, 100, GREEN, "MEM%")
    draw_gauge(265, 70, 28, temp, 80, RED, "TEMP")

    # row 2: bar chart - network
    fb.fill_rect(0, 105, 320, 1, GRAY)
    draw_bar(10, 125, 80, 12, net_in, 100, CYAN, "NET IN")
    draw_bar(110, 125, 80, 12, net_out, 100, YELLOW, "NET OUT")
    draw_bar(210, 125, 80, 12, tasks, 20, GREEN, "TASKS")

    # row 3: sparklines
    fb.fill_rect(0, 148, 320, 1, GRAY)
    fb.text("CPU HISTORY", 4, 153, WHITE)
    draw_sparkline(120, 152, 195, cpu_hist, CYAN)
    fb.text("MEM HISTORY", 4, 168, WHITE)
    draw_sparkline(120, 167, 195, mem_hist, GREEN)

    # row 4: line charts
    fb.fill_rect(0, 180, 320, 1, GRAY)
    fb.text("CPU LOAD", 4, 185, WHITE)
    draw_line_chart(4, 195, 150, 38, cpu_hist, CYAN)
    fb.text("MEMORY", 165, 185, WHITE)
    draw_line_chart(165, 195, 150, 38, mem_hist, GREEN)

    # footer
    fb.fill_rect(0, 237, 320, 3, GRAY)

    fb.show()
    time.sleep_ms(500)
    frame += 1
