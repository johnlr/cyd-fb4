# fb4_gp.py - BBC Grand Prix style 3D racing with cockpit view
# Fixed-point projection, sin/cos LUT, stylized rotating-dashboard cockpit
import math, time, random, array, framebuf, fb4

BG = 0; RED = 1; GREEN = 2; BLUE = 3; YELLOW = 4; CYAN = 5
MAGENTA = 6; DKRED = 7; WHITE = 9; MAROON = 10; DKGREEN = 11
NAVY = 12; TEAL = 13; GRAY = 14; LTGRAY = 15

SW, SH = 320, 240
HORIZON = 82
COCK_Y = 178
BAND = 2
ROWS = (COCK_Y - 1 - HORIZON) // BAND

fb = fb4.FB4()

CAM_H_F   = 1800
ROAD_HW_F = 2805
RUMB_HW_F = 180
LAT_F     = 225

_SIN_LUT = array.array("h", (0,) * 73)
for _i in range(73):
    _SIN_LUT[_i] = int(math.sin(_i * 5 * math.pi / 180) * 1000)

def isin(deg):
    deg = deg % 360
    idx = deg // 5
    frac = deg - idx * 5
    if idx >= 72:
        return _SIN_LUT[0]
    return _SIN_LUT[idx] + (_SIN_LUT[idx + 1] - _SIN_LUT[idx]) * frac // 5

def icos(deg):
    return isin(deg + 90)

MONACO = (
    (170,  0.0), (58,  2.4), (165, -0.9), (48, -2.6), (58,  2.7),
    (115,  0.0), (44,  2.9), (66, -4.3),  (86,  2.3), (205, 1.1),
    (28, -3.3), (24,  3.3), (135,  0.0), (66, -2.4), (52, -2.9),
    (44,  2.9), (54, -2.7), (40,  3.1),  (105, 0.0), (36,  4.1),
    (40,  3.3),
)
TRACK_L = 2048
MAX_SPD = 8.0
_GEAR_MAX = (2.0, 3.5, 5.0, 6.5, 8.0)

CURVE = array.array("f", (0.0 for _ in range(TRACK_L)))
i = 0
for seg_len, seg_curv in MONACO:
    seg_len = min(seg_len, TRACK_L - i)
    for k in range(seg_len):
        CURVE[i + k] = seg_curv
    i += seg_len
while i < TRACK_L:
    CURVE[i] = 0.0
    i += 1

CS = array.array("f", (0.0 for _ in range(TRACK_L + 1)))
for i in range(TRACK_L):
    CS[i + 1] = CS[i] + CURVE[i]

Q = array.array("f", (0.0 for _ in range(TRACK_L + 1)))
for i in range(TRACK_L):
    Q[i + 1] = Q[i] + CS[i]

def curve_avg(base, span):
    return (CS[(base + span) % TRACK_L] - CS[base]) / span

def curve_max(base, span):
    m = 0.0
    for k in range(span):
        c = abs(CURVE[(base + k) % TRACK_L])
        if c > m:
            m = c
    return m

SKYLINE = []
random.seed(1950)
sx = 0
while sx < SW:
    w = 18 + random.getrandbits(6) % 34
    SKYLINE.append((sx, w, 4 + random.getrandbits(5) % 14))
    sx += w
STARS = []
for _ in range(30):
    STARS.append((random.getrandbits(9) % SW,
                  random.getrandbits(7) % (HORIZON - 20)))

NCARS = 6
car_pos = [0.0] * NCARS
car_lane = [0.0] * NCARS
car_spd = [0.0] * NCARS
car_col = [CYAN, YELLOW, MAGENTA, DKRED, GREEN, LTGRAY]

def init_cars():
    gap = TRACK_L // (NCARS + 1)
    for i in range(NCARS):
        car_pos[i] = float((i + 1) * gap)
        car_lane[i] = -0.6 if i % 2 == 0 else 0.6
        car_spd[i] = 1.5 + random.random() * 1.5

def update_cars():
    for i in range(NCARS):
        car_pos[i] += car_spd[i]
        if car_pos[i] > TRACK_L * (laps + 2):
            car_pos[i] -= TRACK_L

def draw_cars():
    base = int(pos) % TRACK_L
    q0 = Q[base]
    px_i = int(px * 100)
    visible = []
    for i in range(NCARS):
        dd = car_pos[i] - pos
        if dd < 10 or dd > 1100:
            continue
        k = base + int(dd)
        if k < TRACK_L:
            d_q = Q[k] - q0
        else:
            d_q = Q[k - TRACK_L] + Q[TRACK_L] - q0
        xo = int(d_q * LAT_F // (int(dd) * 1000))
        hw = max(2, ROAD_HW_F // int(dd))
        cx = SW // 2 + xo - px_i * hw // 100
        cx = max(hw + 2, min(SW - hw - 2, cx))
        cy = HORIZON + CAM_H_F // int(dd)
        if cy < HORIZON + 2 or cy >= COCK_Y:
            continue
        visible.append((dd, cx, cy, hw, i))
    visible.sort(key=lambda x: -x[0])
    for dd, cx, cy, hw, i in visible:
        cw = max(2, hw // 3)
        ch = max(2, hw // 5)
        ccx = cx + int(car_lane[i] * 60) * hw // 100
        fb.fill_rect(ccx - cw, cy - ch, cw * 2, ch, car_col[i])
        fb.fill_rect(ccx - cw + 1, cy - ch - ch // 2, cw * 2 - 2, ch // 2, car_col[i])
        tw = max(1, cw // 3)
        th = max(1, ch // 2)
        # rear tyres (white outline)
        fb.rect(ccx - cw - tw - 1, cy - th - 1, tw + 2, th + 2, WHITE)
        fb.rect(ccx + cw - 1, cy - th - 1, tw + 2, th + 2, WHITE)
        # front tyres (smaller, white outline)
        ftw = max(1, tw - 2)
        fth = max(1, th - 1)
        fb.rect(ccx - cw - ftw - 1, cy - ch - fth, ftw + 2, fth + 2, WHITE)
        fb.rect(ccx + cw - 1, cy - ch - fth, ftw + 2, fth + 2, WHITE)
        if dd < 80:
            fb.fill_rect(ccx - cw - 1, cy - ch, 2, ch, WHITE)
            fb.fill_rect(ccx + cw - 1, cy - ch, 2, ch, WHITE)

def check_collision():
    global spd
    for i in range(NCARS):
        dd = car_pos[i] - pos
        if dd > 0 and dd < 20:
            dl = abs(px - car_lane[i])
            if dl < 0.5:
                spd = max(0.5, spd * 0.6)
                return True
    return False

pos = 0.0
px = 0.0
spd = 0.0
gear = 1
frame = 0
laps = 0
score = 0
fps_t0 = 0
heading = 0.0
steer_angle = 0.0

def reset():
    global pos, px, spd, gear, laps, score, frame, heading
    pos = 0.0; px = 0.0; spd = 0.0; gear = 1
    laps = 0; score = 0; frame = 0; heading = 0.0; steer_angle = 0.0
    init_cars()

def autopilot():
    global px, spd, gear, steer_angle
    base = int(pos) % TRACK_L
    avg_n = 0.0
    for k in range(46):
        avg_n += CURVE[(base + k) % TRACK_L]
    avg_n /= 46
    avg_f = 0.0
    for k in range(150):
        avg_f += CURVE[(base + 46 + k) % TRACK_L]
    avg_f /= 150
    inst = CURVE[(base + 10) % TRACK_L]
    tgt = -(avg_n * 0.5 + avg_f * 0.22 + inst * 0.18)
    tgt = max(-0.85, min(0.85, tgt))
    px += (tgt - px) * 0.09
    px = max(-1.0, min(1.0, px))
    danger = 0.0
    for k in range(90):
        c = abs(CURVE[(base + k) % TRACK_L])
        if c > danger:
            danger = c
    tgt_spd = MAX_SPD - min(5.0, danger * 1.1)
    if spd < tgt_spd:
        spd = min(tgt_spd, spd + 0.08)
    else:
        spd = max(tgt_spd, spd - 0.12)
    gear = max(1, min(5, int(spd / MAX_SPD * 5) + 1))
    if spd > 2.5 and gear < 3:
        gear = 3
    curv = CURVE[base]
    steer_angle += (-curv * 0.3 - steer_angle) * 0.15

def render():
    global frame, heading
    heading += CURVE[int(pos) % TRACK_L] * spd * 0.01
    sky_off = int(heading * 6) % SW
    fb.fill_rect(0, 0, SW, HORIZON, NAVY)
    for sx, sy in STARS:
        fb.fill_rect(sx, sy, 1, 1, LTGRAY)
    base0 = int(pos) % TRACK_L
    for bx, bw, bh in SKYLINE:
        x0 = (bx + sky_off) % SW
        fb.fill_rect(x0, HORIZON - bh, bw, bh, MAROON)
        if x0 + bw > SW:
            fb.fill_rect(x0 - SW, HORIZON - bh, bw, bh, MAROON)
    fb.fill_rect(0, HORIZON, SW, 2, GREEN)

    base = int(pos) % TRACK_L
    q0 = Q[base]
    px_i = int(px * 100)
    prev = None
    for r in range(ROWS):
        y = COCK_Y - 1 - r * BAND
        if y <= HORIZON + 1:
            break
        dy = y - HORIZON
        if dy < 1:
            dy = 1
        dd = CAM_H_F // dy
        k = base + dd
        if k < TRACK_L:
            d_q = Q[k] - q0
        else:
            d_q = Q[k - TRACK_L] + Q[TRACK_L] - q0
        xo = int(d_q * LAT_F // (dd * 1000))
        hw = max(2, ROAD_HW_F // dd)
        rw = max(1, RUMB_HW_F // dd)
        cx = SW // 2 + xo - px_i * hw // 100
        stripe = ((base + dd) >> 3) % 2
        cur = (y, cx, hw, stripe, rw)
        if prev is not None:
            _draw_band(prev, cur)
        prev = cur

def _draw_band(p, c):
    y_top = c[0]
    span = p[0] - y_top
    if span <= 0:
        return
    stripe = c[3]
    grass = GREEN
    rumble = RED if stripe else WHITE
    cx = (c[1] + p[1]) >> 1
    hw = (c[2] + p[2]) >> 1
    rw = (c[4] + p[4]) >> 1
    wr = hw + rw
    if cx + wr < 0 or cx - wr >= SW:
        return
    fb.fill_rect(0, y_top, cx - wr, span, grass)
    fb.fill_rect(cx - wr, y_top, rw, span, rumble)
    fb.fill_rect(cx - hw, y_top, hw * 2, span, BG)
    fb.fill_rect(cx + hw, y_top, rw, span, rumble)
    fb.fill_rect(cx + wr, y_top, SW - (cx + wr), span, grass)
    if stripe == 0:
        dw = max(1, hw >> 4)
        fb.fill_rect(cx - dw, y_top, dw * 2, span, WHITE)

# --- dashboard: red/black/white stylized cockpit -------------------------
# Static background drawn once; only needles + spokes redrawn each frame.

_GAUGE_ARC = []
for _deg in range(0, 271, 6):
    _vf = _deg / 270.0
    _a = 225 - _deg
    _GAUGE_ARC.append((icos(_a), isin(_a), _vf > 0.8))
del _deg, _vf, _a

_TICK_DEGS = []
for _deg in range(0, 271, 45):
    _a = 225 - _deg
    _TICK_DEGS.append((_a,))
del _deg, _a

# gauge positions: (cx, cy, r, label)
_SGAUGE = (60,  COCK_Y + 28, 24, "SPD")
_RGAUGE = (260, COCK_Y + 28, 24, "RPM")
# steering position
_SWX, _SWY, _SWR = 160, COCK_Y + 54, 45

# old dynamic state (for erase-before-redraw)
_old_sn = (0, 0)
_old_rn = (0, 0)
_old_gear_s = ""

def draw_cockpit_static():
    """Draw the entire dashboard once. Call after reset()."""
    # dark background with red accent stripe
    fb.fill_rect(0, COCK_Y, SW, SH - COCK_Y, BG)
    fb.fill_rect(0, COCK_Y, SW, 3, RED)
    fb.fill_rect(0, COCK_Y + 3, SW, 1, WHITE)
    fb.fill_rect(0, COCK_Y + 4, SW, SH - COCK_Y - 4, DKRED)
    # gauge backgrounds
    _draw_gauge_static(*_SGAUGE)
    _draw_gauge_static(*_RGAUGE, True)
    # gear display box (right of tacho)
    fb.fill_rect(292, COCK_Y + 20, 28, 22, BG)
    fb.rect(292, COCK_Y + 20, 28, 22, WHITE)
    # steering wheel ring (8px thick black ring) + center hub
    cx, cy, r = _SWX, _SWY, _SWR
    ri = r - 8
    hr = 8
    for dy in range(-r, r + 1):
        wy = cy + dy
        if wy < COCK_Y:
            continue
        sq = r * r - dy * dy
        if sq < 0:
            continue
        ox = int(math.sqrt(sq))
        sq2 = ri * ri - dy * dy
        if sq2 > 0:
            ix = int(math.sqrt(sq2))
            fb.fill_rect(cx - ox, wy, ox - ix, 1, BG)
            fb.fill_rect(cx + ix, wy, ox - ix + 1, 1, BG)
        else:
            fb.fill_rect(cx - ox, wy, ox * 2 + 1, 1, BG)
    for dy in range(-hr, hr + 1):
        wy = cy + dy
        if wy < COCK_Y:
            continue
        sq = hr * hr - dy * dy
        if sq < 0:
            continue
        hx = int(math.sqrt(sq))
        fb.fill_rect(cx - hx, wy, hx * 2 + 1, 1, BG)

def _draw_gauge_static(cx, cy, r, label, redline=False):
    fb.fill_rect(cx - r - 1, cy - r - 1, r * 2 + 3, r * 2 + 3, BG)
    fb.rect(cx - r - 1, cy - r - 1, r * 2 + 3, r * 2 + 3, RED)
    for c_x, c_y, is_red in _GAUGE_ARC:
        fb.fill_rect(cx + r * c_x // 1000, cy - r * c_y // 1000, 1, 1, RED if (redline and is_red) else WHITE)
    for (a,) in _TICK_DEGS:
        x1 = cx + (r - 3) * icos(a) // 1000
        y1 = cy - (r - 3) * isin(a) // 1000
        x2 = cx + (r + 1) * icos(a) // 1000
        y2 = cy - (r + 1) * isin(a) // 1000
        fb.line(x1, y1, x2, y2, WHITE)
    fb.fill_rect(cx - 1, cy - 1, 3, 3, WHITE)
    fb.text(label, cx - 8, cy + r + 3, WHITE)

def _needle_end(cx, cy, r, val, mx):
    v = min(1.0, val / mx)
    na = int(225 - v * 270)
    nr = r - 5
    return (cx + nr * icos(na) // 1000, cy - nr * isin(na) // 1000, na)

def _thick_line(x0, y0, x1, y1, hw, c):
    dx = x1 - x0
    dy = y1 - y0
    adx = abs(dx)
    ady = abs(dy)
    if adx >= ady:
        if adx == 0:
            return
        sx = 1 if dx > 0 else -1
        yf = 0
        ys = (dy << 16) // adx
        for i in range(adx + 1):
            iy = y0 + (yf >> 16)
            if iy >= COCK_Y:
                fb.fill_rect(x0, iy - hw, 1, hw * 2 + 1, c)
            x0 += sx
            yf += ys
    else:
        sy = 1 if dy > 0 else -1
        xf = 0
        xs = (dx << 16) // ady
        for i in range(ady + 1):
            ix = x0 + (xf >> 16)
            if y0 >= COCK_Y:
                fb.fill_rect(ix - hw, y0, hw * 2 + 1, 1, c)
            y0 += sy
            xf += xs

def draw_cockpit_dynamic():
    """Erase old needles/spokes/gear/km, draw new ones."""
    global _old_sn, _old_rn, _old_gear_s
    # --- speedo needle ---
    sx, sy, _ = _needle_end(_SGAUGE[0], _SGAUGE[1], _SGAUGE[2], spd, MAX_SPD)
    ox, oy = _old_sn
    fb.line(_SGAUGE[0], _SGAUGE[1], ox, oy, BG)
    fb.fill_rect(_SGAUGE[0] - 1, _SGAUGE[1] - 1, 3, 3, WHITE)
    fb.line(_SGAUGE[0], _SGAUGE[1], sx, sy, RED)
    fb.fill_rect(_SGAUGE[0] - 1, _SGAUGE[1] - 1, 3, 3, WHITE)
    _old_sn = (sx, sy)
    # --- tacho needle ---
    rx, ry, _ = _needle_end(_RGAUGE[0], _RGAUGE[1], _RGAUGE[2], min(7000, int(spd * 7000 / _GEAR_MAX[gear - 1])), 7000)
    ox, oy = _old_rn
    fb.line(_RGAUGE[0], _RGAUGE[1], ox, oy, BG)
    fb.fill_rect(_RGAUGE[0] - 1, _RGAUGE[1] - 1, 3, 3, WHITE)
    fb.line(_RGAUGE[0], _RGAUGE[1], rx, ry, RED)
    fb.fill_rect(_RGAUGE[0] - 1, _RGAUGE[1] - 1, 3, 3, WHITE)
    _old_rn = (rx, ry)
    # --- gear display ---
    gs = str(gear)
    if gs != _old_gear_s:
        fb.fill_rect(293, COCK_Y + 21, 26, 20, BG)
        fb.text(gs, 302, COCK_Y + 25, WHITE)
        _old_gear_s = gs
    # --- steering wheel (erase circle, redraw ring+hub+spokes) ---
    cx, cy, r = _SWX, _SWY, _SWR
    ri = r - 8
    hr = 8
    hw = 4
    rot = int(steer_angle * 45)
    # filled DKRED circle to erase
    for dy in range(-r, r + 1):
        wy = cy + dy
        if wy < COCK_Y:
            continue
        sq = r * r - dy * dy
        if sq > 0:
            hx = int(math.sqrt(sq))
            fb.fill_rect(cx - hx, wy, hx * 2 + 1, 1, DKRED)
    # black ring from radius ri to r
    for dy in range(-(r), r + 1):
        wy = cy + dy
        if wy < COCK_Y:
            continue
        so = r * r - dy * dy
        si = ri * ri - dy * dy
        if so <= 0:
            continue
        ox = int(math.sqrt(so))
        if si > 0:
            ix = int(math.sqrt(si))
            fb.fill_rect(cx - ox, wy, ox - ix, 1, BG)
            fb.fill_rect(cx + ix, wy, ox - ix + 1, 1, BG)
        else:
            fb.fill_rect(cx - ox, wy, ox * 2 + 1, 1, BG)
    # black hub
    for dy in range(-hr, hr + 1):
        wy = cy + dy
        if wy < COCK_Y:
            continue
        sq = hr * hr - dy * dy
        if sq > 0:
            hx = int(math.sqrt(sq))
            fb.fill_rect(cx - hx, wy, hx * 2 + 1, 1, BG)
    # spokes
    for i in range(3):
        a = i * 120 + rot
        ex = cx + ri * icos(a) // 1000
        ey = cy - ri * isin(a) // 1000
        _thick_line(cx, cy, ex, ey, hw, BG)
    for i in range(3):
        a = i * 120 + rot
        ex = cx + ri * icos(a) // 1000
        ey = cy - ri * isin(a) // 1000
        _thick_line(cx, cy, ex, ey, hw, BG)

def draw_hud():
    fb.text("PTS " + str(score), 250, 2, YELLOW)
    fb.text(str(int(pos * 2) % 10000) + " m", 4, 2, WHITE)

print("gp v3: partial-redraw cockpit")
while True:
    reset()
    draw_cockpit_static()
    # force initial dynamic state
    _old_sn = (_SGAUGE[0], _SGAUGE[1])
    _old_rn = (_RGAUGE[0], _RGAUGE[1])
    _old_gear_s = ""
    running = True
    while running:
        autopilot()
        update_cars()
        check_collision()
        pos += spd
        if int(pos) // TRACK_L > laps:
            laps += 1
            score += 500
            print("lap {} pts {}".format(laps, score))
        if frame == 1:
            fps_t0 = time.ticks_ms()
        render()
        draw_cars()
        draw_cockpit_dynamic()
        draw_hud()
        fb.show()
        frame += 1
        if frame == 60:
            print("avg frame {} ms".format(
                time.ticks_diff(time.ticks_ms(), fps_t0) // 60))
        time.sleep_ms(22)
