# fb4_kessler.py - self-playing asteroids-style demo using the fb4 module
# You are an orbital cleanup crew: break up space junk around Earth before
# it causes a Kessler syndrome cascade. Big junk splits into smaller,
# faster pieces; small pieces are worth the most points. Touch is not wired
# up yet, so the ship flies itself: it turns toward the nearest chunk,
# leads its shots and thrusts away from collisions.
import math
import time
import random
import fb4

print("kessler v2: iss + edge spawns")

BG = 0
RED = 1
GREEN = 2
BLUE = 3
YELLOW = 4
CYAN = 5
PURPLE = 8
WHITE = 9
GRAY = 15

SW = 320
SH = 240

TWO_PI = 2 * math.pi
TURN_RATE = 0.13          # rad per frame
THRUST = 0.09
FRICTION = 0.985
MAX_V = 2.4
SHIP_R = 6

SIZE_R = {3: 14, 2: 9, 1: 5}
SIZE_PTS = {3: 20, 2: 50, 1: 100}

fb = fb4.FB4()


def fill_circle(cx, cy, r, col):
    r2 = r * r
    for dy in range(-r, r + 1):
        w = int((r2 - dy * dy) ** 0.5)
        fb.fill_rect(cx - w, cy + dy, 2 * w + 1, 1, col)


def draw_poly(pts, col):
    """Draw a closed polyline whose points may straddle the screen wrap.

    Each edge is unwrapped to the copy nearest its start point, drawn there,
    and - if it runs off the screen - drawn again translated to the opposite
    edge, so only genuinely visible fragments appear (fb clips the rest).
    """
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        if bx - ax > SW / 2:
            bx -= SW
        elif bx - ax < -SW / 2:
            bx += SW
        if by - ay > SH / 2:
            by -= SH
        elif by - ay < -SH / 2:
            by += SH
        fb.line(int(ax), int(ay), int(bx), int(by), col)
        ox = 0
        oy = 0
        if bx < 0:
            ox = SW
        elif bx >= SW:
            ox = -SW
        if by < 0:
            oy = SH
        elif by >= SH:
            oy = -SH
        if ox or oy:
            fb.line(int(ax + ox), int(ay + oy), int(bx + ox), int(by + oy),
                    col)


def wrap_x(x):
    return x % SW


def wrap_y(y):
    return y % SH


def make_junk(x, y, size, wave):
    n = 7 + random.getrandbits(8) % 4
    verts = []
    for i in range(n):
        verts.append((i / n, 0.65 + (random.getrandbits(8) % 35) / 100))
    sp = (random.getrandbits(8) / 255 * 0.5 + 0.25) * (1 + 0.12 * wave)
    a = random.getrandbits(8) / 255 * TWO_PI
    return {
        "x": x, "y": y,
        "vx": sp * math.cos(a), "vy": sp * math.sin(a),
        "r": SIZE_R[size], "size": size,
        "rot": random.getrandbits(8) / 255 * TWO_PI,
        "vr": ((random.getrandbits(8) / 255) - 0.5) * 0.15,
        "verts": verts,
    }


def spawn_ok(x, y):
    """New junk needs clearance from the player and the ISS."""
    dx = x - ship[0]
    dy = y - ship[1]
    if dx * dx + dy * dy < 70 * 70:
        return False
    if iss is not None:
        dx = x - iss[0]
        dy = y - iss[1]
        if dx * dx + dy * dy < 70 * 70:
            return False
    return True


def spawn_one(wave):
    """Create one chunk entering from a random edge, aimed inward.
    Returns None when clearance rules block every attempt."""
    m = 24
    for _try in range(30):
        side = random.getrandbits(8) % 4
        if side == 0:
            x = random.getrandbits(9) % SW
            y = -m
        elif side == 1:
            x = random.getrandbits(9) % SW
            y = SH + m
        elif side == 2:
            x = -m
            y = random.getrandbits(8) % SH
        else:
            x = SW + m
            y = random.getrandbits(8) % SH
        if spawn_ok(x, y):
            break
    else:
        return None
    j = make_junk(x, y, 3, wave)
    # drift roughly toward the middle of the screen
    tx = 60 + random.getrandbits(8) % 200
    ty = 40 + random.getrandbits(8) % 160
    sp = math.sqrt(j["vx"] ** 2 + j["vy"] ** 2)
    dxn = tx - x
    dyn = ty - y
    dn = math.sqrt(dxn * dxn + dyn * dyn) or 1
    j["vx"] = dxn / dn * sp
    j["vy"] = dyn / dn * sp
    return j


def spawn_wave(wave):
    global junk
    junk = []
    n = min(3 + wave, 7)
    for _ in range(n):
        j = spawn_one(wave)
        if j is not None:
            junk.append(j)


ship = [160.0, 120.0, 0.0, 0.0, -math.pi / 2]   # x y vx vy heading
bullets = []          # {"x","y","vx","vy","ttl"}
junk = []
iss = None            # [x, y, vx] while a station is passing through
iss_hp = 100          # hull integrity persists between passes
score = 0
lives = 3
wave = 1
fire_cd = 0
invuln = 0
frame = 0
spawn_timer = 300       # frames until the next top-up chunk
station_lost = False    # set when the ISS hull hits zero -> game over
iss_spawn_timer = 100   # while the ISS is around: junk every ~5 s


def reset():
    global ship, bullets, junk, score, lives, wave, fire_cd, invuln
    global iss, spawn_timer, iss_hp, iss_spawn_timer
    iss = None
    iss_hp = 100
    ship = [160.0, 120.0, 0.0, 0.0, -math.pi / 2]
    bullets = []
    score = 0
    lives = 3
    wave = 1
    fire_cd = 0
    invuln = 90
    spawn_timer = 300
    iss_spawn_timer = 100
    random.seed(int(time.ticks_ms()) & 1023)
    spawn_wave(1)


def split_junk(j, idx, bvx, bvy):
    """Remove hit junk, spawn children, award points."""
    global score
    size = j["size"]
    junk.pop(idx)
    score += SIZE_PTS[size]
    if size > 1:
        for k in (-1, 1):
            c = make_junk(j["x"], j["y"], size - 1, wave)
            c["vx"] = j["vx"] + k * 0.45 - bvx * 0.02
            c["vy"] = j["vy"] + 0.3 * k - bvy * 0.02
            junk.append(c)


def autopilot():
    """Turn toward nearest junk, fire when lined up, dodge when crowded."""
    global fire_cd
    x, y, vx, vy, hdg = ship
    if not junk:
        return
    # nearest visible chunk (accounting for wrap is overkill; plain dist)
    best = None
    bd = 1 << 30
    for j in junk:
        d = (j["x"] - x) ** 2 + (j["y"] - y) ** 2
        if d < bd:
            bd = d
            best = j
    tx = best["x"]
    ty = best["y"]
    # lead the target: solve |rel_pos + rel_v*t| == bullet_speed * t so we
    # shoot where the chunk will be when the bullet arrives
    jvx = best["vx"]
    jvy = best["vy"]
    rx = tx - x
    ry = ty - y
    qa = jvx * jvx + jvy * jvy - 25.0     # bullet speed 5 -> 5^2
    qb = 2.0 * (rx * jvx + ry * jvy)
    qc = rx * rx + ry * ry
    t_hit = None
    if abs(qa) < 1e-6:
        if qb != 0:
            t_hit = -qc / qb
    else:
        disc = qb * qb - 4 * qa * qc
        if disc >= 0:
            sq = math.sqrt(disc)
            t_hit = min(((-qb - sq) / (2 * qa), (-qb + sq) / (2 * qa)))
    if t_hit is not None and 0 <= t_hit <= 60:
        tx += jvx * t_hit
        ty += jvy * t_hit
    want = math.atan2(ty - y, tx - x)
    diff = (want - hdg + math.pi) % TWO_PI - math.pi
    if diff > TURN_RATE:
        ship[4] += TURN_RATE
    elif diff < -TURN_RATE:
        ship[4] -= TURN_RATE
    else:
        ship[4] = want
    # fire when roughly aligned
    if fire_cd <= 0 and abs(diff) < 0.18 and len(bullets) < 4 \
            and bd < 260 * 260:
        ca = math.cos(ship[4])
        sa = math.sin(ship[4])
        bullets.append({"x": x + ca * SHIP_R, "y": y + sa * SHIP_R,
                        "vx": ca * 5, "vy": sa * 5, "ttl": 26})
        fire_cd = 6
    # thrust: keep some motion, flee close chunks and the station
    danger = None
    dd = 60 * 60
    for j in junk:
        d = (j["x"] - x) ** 2 + (j["y"] - y) ** 2
        if d < dd:
            dd = d
            danger = (x - j["x"], y - j["y"])
    if iss is not None:
        d = (iss[0] - x) ** 2 + (iss[1] - y) ** 2
        if d < dd:
            dd = d
            danger = (x - iss[0], y - iss[1])
    if danger is not None:
        away = math.atan2(danger[1], danger[0])
        ship[2] += THRUST * 1.6 * math.cos(away)
        ship[3] += THRUST * 1.6 * math.sin(away)
    elif bd > 140 * 140 and random.getrandbits(8) < 12:
        ship[2] += THRUST * 2.2 * math.cos(ship[4])
        ship[3] += THRUST * 2.2 * math.sin(ship[4])


def update_iss():
    """Spawn/move the station. Junk vaporizes on its hull, costing HP.
    Damage persists across passes; losing the hull loses the mission."""
    global iss, iss_hp, station_lost
    if iss is None:
        if random.getrandbits(8) < 1:
            y = 46 + random.getrandbits(7) % 110
            if random.getrandbits(8) % 2 == 0:
                iss = [-40.0, float(y), 0.7]
            else:
                iss = [SW + 40.0, float(y), -0.7]
        return
    iss[0] += iss[2]
    iss[1] += math.sin(frame / 40) * 0.3
    if iss[0] < -70 or iss[0] > SW + 70:
        iss = None
        return
    r = 24
    r2 = r * r
    for i in range(len(junk) - 1, -1, -1):
        j = junk[i]
        dx = j["x"] - iss[0]
        dy = j["y"] - iss[1]
        if dx * dx + dy * dy < r2:
            size = j["size"]
            d = math.sqrt(dx * dx + dy * dy) or 0.01
            nx = dx / d
            ny = dy / d
            junk.pop(i)
            # large/medium chunks break up like a bullet strike, and both
            # halves are pushed away from the hull so they cannot hit it
            # again straight away
            if size > 1:
                t_x = -ny
                t_y = nx
                off = r + SIZE_R[size - 1] + 3
                for k in (-1, 1):
                    c = make_junk(iss[0] + nx * off + t_x * k * 5,
                                  iss[1] + ny * off + t_y * k * 5,
                                  size - 1, wave)
                    c["vx"] = nx * 0.9 + t_x * k * 0.5
                    c["vy"] = ny * 0.9 + t_y * k * 0.5
                    junk.append(c)
            iss_hp -= {3: 32, 2: 16, 1: 8}[size]
            if iss_hp <= 0:
                print("ISS lost!")
                iss = None
                station_lost = True
                return


def draw_iss():
    if iss is None:
        return
    cx = int(iss[0])
    cy = int(iss[1])
    fb.fill_rect(cx - 16, cy - 1, 32, 2, GRAY)   # truss
    fb.fill_rect(cx - 4, cy - 2, 8, 4, WHITE)    # core module
    fb.fill_rect(cx - 14, cy - 6, 10, 5, BLUE)   # solar wings
    fb.fill_rect(cx - 14, cy + 1, 10, 5, BLUE)
    fb.fill_rect(cx + 4, cy - 6, 10, 5, BLUE)
    fb.fill_rect(cx + 4, cy + 1, 10, 5, BLUE)
    if frame % 30 < 15:
        fb.fill_rect(cx + 12, cy - 2, 1, 1, RED)  # beacon


def draw_iss_bar():
    if iss is None:
        return
    fb.text("ISS", 92, 13, GRAY)
    fb.rect(120, 13, 80, 8, WHITE)
    hp = iss_hp
    col = GREEN if hp > 50 else (YELLOW if hp > 25 else RED)
    fw = (78 * hp) // 100
    if fw > 0:
        fb.fill_rect(121, 15, fw, 4, col)


def update_ship():
    global fire_cd, invuln
    s = ship
    spd2 = s[2] * s[2] + s[3] * s[3]
    if spd2 > MAX_V * MAX_V:
        f = MAX_V / math.sqrt(spd2)
        s[2] *= f
        s[3] *= f
    s[2] *= FRICTION
    s[3] *= FRICTION
    s[0] = wrap_x(s[0] + s[2])
    s[1] = wrap_y(s[1] + s[3])
    if fire_cd:
        fire_cd -= 1
    if invuln:
        invuln -= 1
    # ship vs junk
    if invuln == 0:
        for i in range(len(junk)):
            j = junk[i]
            dx = j["x"] - s[0]
            dy = j["y"] - s[1]
            if dx * dx + dy * dy < (j["r"] + SHIP_R) ** 2:
                return True
        # ramming the station is just as fatal
        if iss is not None:
            dx = iss[0] - s[0]
            dy = iss[1] - s[1]
            if dx * dx + dy * dy < (22 + SHIP_R) ** 2:
                return True
    return False


def update_junk_and_bullets():
    """Move everything; handle bullet hits. Returns True on wave cleared."""
    global score, iss, iss_hp, station_lost
    for j in junk:
        j["x"] = wrap_x(j["x"] + j["vx"])
        j["y"] = wrap_y(j["y"] + j["vy"])
        j["rot"] += j["vr"]
    for b in bullets[:]:
        b["x"] = wrap_x(b["x"] + b["vx"])
        b["y"] = wrap_y(b["y"] + b["vy"])
        b["ttl"] -= 1
        # stray rounds chip the station's hull too
        if iss is not None:
            dx = b["x"] - iss[0]
            dy = b["y"] - iss[1]
            if dx * dx + dy * dy < 22 * 22:
                iss_hp -= 5
                bullets.remove(b)
                if iss_hp <= 0:
                    print("ISS lost!")
                    iss = None
                    station_lost = True
                continue
        hit = False
        for i in range(len(junk)):
            j = junk[i]
            dx = j["x"] - b["x"]
            dy = j["y"] - b["y"]
            rr = j["r"] + 1
            if dx * dx + dy * dy < rr * rr:
                split_junk(j, i, b["vx"], b["vy"])
                hit = True
                break
        if hit or b["ttl"] <= 0:
            bullets.remove(b)
    return len(junk) == 0


def draw_earth():
    # big blue planet rising from the bottom of the screen
    fill_circle(160, 300, 96, BLUE)
    # landmasses + polar cap peeking over the limb
    fill_circle(128, 240, 15, GREEN)
    fill_circle(196, 246, 11, GREEN)
    fill_circle(158, 224, 6, GREEN)
    fb.fill_rect(148, 210, 24, 4, WHITE)
    fb.ellipse(160, 300, 98, 98, CYAN)    # thin atmosphere glow


def draw_ship():
    if invuln and (frame // 4) % 2:
        return
    x, y = ship[0], ship[1]
    h = ship[4]
    ca = math.cos(h)
    sa = math.sin(h)
    pts = []
    for ox, oy in ((10, 0), (-7, 6), (-4, 0), (-7, -6)):
        pts.append((x + ox * ca - oy * sa,
                    y + ox * sa + oy * ca))
    draw_poly(pts, WHITE)
    # engine flare when moving fast
    if ship[2] ** 2 + ship[3] ** 2 > 1.2:
        fx = x - 8 * ca
        fy = y - 8 * sa
        fb.fill_rect(int(fx), int(fy), 2, 2, YELLOW)


def draw_junk_piece(j):
    pts = []
    for frac, rf in j["verts"]:
        a = j["rot"] + frac * TWO_PI
        r = j["r"] * rf
        pts.append((j["x"] + r * math.cos(a),
                    j["y"] + r * math.sin(a)))
    col = GRAY if j["size"] == 3 else (CYAN if j["size"] == 2 else YELLOW)
    draw_poly(pts, col)


def draw():
    fb.fill(BG)
    for sx, sy in STARS:
        fb.fill_rect(sx, sy, 1, 1, GRAY)
    draw_earth()
    draw_iss()
    for j in junk:
        draw_junk_piece(j)
    for b in bullets:
        fb.fill_rect(int(b["x"]), int(b["y"]), 1, 1, YELLOW)
    draw_ship()
    fb.text("SCORE {}".format(score), 4, 2, WHITE)
    fb.text("W{}".format(wave), 146, 2, CYAN)
    draw_iss_bar()
    for i in range(lives):
        fill_circle(306 - i * 14, 10, 5, GREEN)
    fb.show()


STARS = []
for _ in range(60):
    STARS.append(((random.getrandbits(9)) % SW, (random.getrandbits(8)) % 105))

games = 0
while True:
    games += 1
    reset()
    alive = True
    while alive:
        autopilot()
        if update_ship():
            lives -= 1
            ship[0] = 160.0
            ship[1] = 120.0
            ship[2] = 0.0
            ship[3] = 0.0
            invuln = 110
            if lives <= 0:
                alive = False
        if update_junk_and_bullets():
            score += 200
            print("wave {} cleared".format(wave))
            wave += 1
            spawn_wave(wave)
        update_iss()
        if station_lost:
            station_lost = False
            lives = 0
            alive = False
        # junk traffic thickens as the game goes on
        spawn_timer -= 1
        if spawn_timer <= 0:
            spawn_timer = max(100, 380 - wave * 35)
            if len(junk) < min(6 + wave, 12):
                j = spawn_one(wave)
                if j is not None:
                    junk.append(j)
        # extra pressure while the station is passing through
        if iss is not None:
            iss_spawn_timer -= 1
            if iss_spawn_timer <= 0:
                iss_spawn_timer = 100   # ~5 s
                if len(junk) < min(8 + wave, 14):
                    j = spawn_one(wave)
                    if j is not None:
                        junk.append(j)
        draw()
        time.sleep_ms(28)
    draw()
    print("game {} over, score {}".format(games, score))
    fb.fill_rect(124, 110, 72, 24, BG)
    fb.rect(124, 110, 72, 24, WHITE)
    t1 = "GAME OVER"
    fb.text(t1, 160 - 4 * len(t1), 114, RED)
    t2 = str(score)
    fb.text(t2, 160 - 4 * len(t2), 125, WHITE)
    fb.show()
    time.sleep_ms(2500)
