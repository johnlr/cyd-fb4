# fb4_dashboard2.py - self-playing sci-fi data dashboard demo using fb4
# Displays rotating radar sweep, network nodes, event log, and live
# system stats with a warm amber/orange theme. All values simulated.
import time
import random
import math
import fb4

BG = 0
AMBER = 4
ORANGE = 7
RED = 1
GREEN = 2
CYAN = 5
WHITE = 9
DGRAY = 8
LGRAY = 15

fb = fb4.FB4()

# warm amber palette
fb.set_palette(0, 15, 12, 8)      # BG - near black
fb.set_palette(1, 200, 60, 40)    # RED
fb.set_palette(2, 60, 180, 60)    # GREEN
fb.set_palette(4, 220, 160, 40)   # AMBER
fb.set_palette(5, 50, 180, 200)   # CYAN
fb.set_palette(7, 200, 120, 40)   # ORANGE
fb.set_palette(8, 30, 28, 25)     # DGRAY
fb.set_palette(9, 230, 220, 200)  # WHITE
fb.set_palette(15, 70, 65, 55)    # LGRAY

# network nodes
nodes = []
for i in range(8):
    angle = i * (2 * math.pi / 8)
    nodes.append({
        'x': int(55 + 40 * math.cos(angle)),
        'y': int(55 + 40 * math.sin(angle)),
        'load': random.randint(10, 90),
        'alive': True,
    })

# event log
events = [
    "BOOT SEQUENCE COMPLETE",
    "NODE 0: ONLINE",
    "NODE 1: ONLINE",
    "SCANNING NETWORK...",
    "HANDSHAKE OK",
    "SYNC COMPLETE",
    "UPLINK ESTABLISHED",
]

frame = 0
sweep_angle = 0.0
uptime_s = 0
packets = 0
alerts = 0

def draw_radar(cx, cy, r, angle):
    fb.ellipse(cx, cy, r, r, DGRAY, 0)
    fb.ellipse(cx, cy, r // 2, r // 2, DGRAY, 0)
    fb.fill_rect(cx - 1, cy - 1, 3, 3, AMBER)
    # crosshairs
    fb.line(cx - r, cy, cx + r, cy, DGRAY)
    fb.line(cx, cy - r, cx, cy + r, DGRAY)
    # sweep line
    ex = int(cx + r * math.cos(angle))
    ey = int(cy + r * math.sin(angle))
    fb.line(cx, cy, ex, ey, GREEN)
    # sweep cone
    for a_off in range(20):
        sa = angle - a_off * 0.015
        sx = int(cx + r * math.cos(sa))
        sy = int(cy + r * math.sin(sa))
        fb.line(cx, cy, sx, sy, GREEN)

def draw_node_map(x, y, w, h):
    fb.rect(x, y, w, h, DGRAY)
    fb.text("NODE MAP", x + 4, y + 2, AMBER)
    cx = x + w // 2
    cy = y + h // 2
    # draw connections
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if random.random() < 0.3:
                fb.line(nodes[i]['x'] + (x - 110), nodes[i]['y'] + (y - 10),
                        nodes[j]['x'] + (x - 110), nodes[j]['y'] + (y - 10), DGRAY)
    # draw nodes
    for n in nodes:
        nx = n['x'] + (x - 110)
        ny = n['y'] + (y - 10)
        col = GREEN if n['alive'] else RED
        fb.fill_rect(nx - 3, ny - 3, 7, 7, col)

def draw_event_log(x, y, w, h, log):
    fb.rect(x, y, w, h, DGRAY)
    fb.text("EVENT LOG", x + 4, y + 2, AMBER)
    visible = min(len(log), (h - 14) // 8)
    start = max(0, len(log) - visible)
    for i in range(visible):
        entry = log[start + i]
        if len(entry) > w // 8 - 2:
            entry = entry[:w // 8 - 2]
        fb.text(entry, x + 4, y + 14 + i * 8, GREEN if i % 2 == 0 else CYAN)

def draw_mini_graph(x, y, w, h, vals, col):
    fb.rect(x, y, w, h, DGRAY)
    if len(vals) < 2:
        return
    mx = max(max(vals), 1)
    step = w / max(len(vals) - 1, 1)
    prev_x = x + 1
    prev_y = y + h - 1 - int(vals[0] / mx * (h - 4))
    for i in range(1, len(vals)):
        px = int(x + 1 + i * step)
        py = y + h - 1 - int(vals[i] / mx * (h - 4))
        fb.line(prev_x, prev_y, px, py, col)
        prev_x = px
        prev_y = py

# init
fb.fill(BG)
fb.show()

pkt_hist = [0] * 30
load_hist = [0] * 30
log = list(events)

while True:
    fb.fill(BG)

    uptime_s += 1
    packets += random.randint(50, 200)
    sweep_angle += 0.15

    cpu_load = 30 + 25 * math.sin(frame * 0.06) + random.randint(-5, 5)
    load_hist.append(int(cpu_load))
    load_hist.pop(0)
    pkt_rate = random.randint(80, 250)
    pkt_hist.append(pkt_rate)
    pkt_hist.pop(0)

    # randomly toggle a node
    if random.random() < 0.05:
        idx = random.randint(0, len(nodes) - 1)
        nodes[idx]['alive'] = not nodes[idx]['alive']
        if nodes[idx]['alive']:
            log.append("NODE {}: ONLINE".format(idx))
        else:
            log.append("NODE {}: OFFLINE".format(idx))
            alerts += 1
        if len(log) > 20:
            log.pop(0)

    # --- layout ---
    # top bar
    fb.fill_rect(0, 0, 320, 12, 15)
    fb.text("SCI-FI DASHBOARD", 4, 2, BG)
    hrs = uptime_s // 3600
    mins = (uptime_s % 3600) // 60
    fb.text("{:02d}:{:02d}".format(hrs, mins), 260, 2, BG)

    # radar
    draw_radar(55, 75, 42, sweep_angle)

    # node map
    draw_node_map(110, 14, 100, 110)

    # event log
    draw_event_log(216, 14, 100, 110, log)

    # bottom section
    fb.fill_rect(0, 128, 320, 1, AMBER)

    # stats boxes
    fb.text("PKT/S", 4, 134, AMBER)
    fb.text(str(pkt_rate), 4, 144, WHITE)
    draw_mini_graph(80, 132, 100, 24, pkt_hist, AMBER)

    fb.text("LOAD", 4, 162, AMBER)
    fb.text(str(int(cpu_load)) + "%", 4, 172, WHITE)
    draw_mini_graph(80, 160, 100, 24, load_hist, CYAN)

    fb.text("TOTAL: {}K".format(packets // 1000), 200, 134, GREEN)
    fb.text("ALERTS: {}".format(alerts), 200, 150, RED)

    alive_count = sum(1 for n in nodes if n['alive'])
    fb.text("NODES: {}/{}".format(alive_count, len(nodes)), 200, 166, GREEN if alive_count == len(nodes) else ORANGE)

    # bottom bar
    fb.fill_rect(0, 190, 320, 1, AMBER)
    draw_mini_graph(4, 200, 312, 35, pkt_hist, AMBER)

    fb.show()
    time.sleep_ms(200)
    frame += 1
