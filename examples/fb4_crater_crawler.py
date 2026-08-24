# fb4_crater_crawler.py - self-playing Moon Patrol style demo using fb4
# The crawler drives itself over the lunar surface: it hops craters and
# rocks, blasts boulders with its cannon and takes pot shots at passing
# UFOs. Features the iconic parallax mountain ridges in the background.
import math
import time
import random
import fb4

print("crater crawler v8")

# palette indices
BG = 0
RED = 1
GREEN = 2
YELLOW = 4
CYAN = 5
PURPLE = 8
WHITE = 9
MAROON = 10
NAVY = 12
GRAY = 15

SW = 320
SH = 240
STEP = 2                 # terrain column width in px
NCOLS = SW // STEP       # 160 columns visible
FAR_BASE = 138           # far ridge line
NEAR_BASE = 166          # near ridge line
GROUND_BASE = 202        # average ground height
BUGGY_X = 80
LEVEL_LEN_M = 400        # metres per level

# --- difficulty parameters (set by set_level) ---------------------------
speed = 4                # px scrolled per frame
crater_w_max = 7         # widest crater in columns
flat_min = 60            # minimum flat stretch between features (columns)
rock_chance = 5          # per-frame rock spawn chance out of 256
big_lim = 45             # rock is a boulder if getrandbits(8) < big_lim
dive_chance = 1          # ufo dive initiation chance out of 256

fb = fb4.FB4()

# --- static star field -------------------------------------------------
stars = []
for _ in range(48):
    stars.append((random.getrandbits(8) * 5 % SW, random.getrandbits(7) * 3 % 130))


# --- tileable parallax ridge profiles ----------------------------------
def make_ridge(base, a1, a2, k1, k2, phase):
    arr = []
    for i in range(NCOLS):
        h = base + a1 * math.sin(2 * math.pi * k1 * i / NCOLS + phase) \
            + a2 * math.sin(2 * math.pi * k2 * i / NCOLS)
        arr.append(int(h))
    return arr


far_ridge = make_ridge(FAR_BASE, 20, 8, 2, 5, 0.7)
near_ridge = make_ridge(NEAR_BASE, 14, 7, 3, 8, 2.1)


def fill_circle(cx, cy, r, col):
    r2 = r * r
    for dy in range(-r, r + 1):
        w = int((r2 - dy * dy) ** 0.5)
        fb.fill_rect(cx - w, cy + dy, 2 * w + 1, 1, col)


def draw_ridge(arr, off_px, col):
    """Draw a scrolling ridge as merged horizontal runs."""
    i0 = int(off_px) // STEP
    run_start = 0
    run_h = arr[i0 % NCOLS]
    for sx in range(STEP, SW, STEP):
        h = arr[(i0 + sx // STEP) % NCOLS]
        if h != run_h:
            fb.fill_rect(run_start, run_h, sx - run_start, SH - run_h, col)
            run_start = sx
            run_h = h
    fb.fill_rect(run_start, run_h, SW - run_start, SH - run_h, col)


# --- world state ---------------------------------------------------------
cols = []            # visible ground columns: height y, or -1 for crater
rocks = []           # {"x": screen x, "h": ground y}
ufos = []            # {"x","y0","ph"}
bullets = []         # {"x","y","vx","vy"}
score = 0
lives = 3
dist_m = 0
world_cols = 0       # total columns scrolled away
by = 0               # buggy wheel-bottom y
vy = 0
airborne = False
invuln = 0
fire_cd = 0
frame = 0
gen_flat = 30        # columns of flat ground before next feature
level = 1
since_jump = 999     # frames since last jump
last_jump_d = -1     # hazard distance at takeoff


def ground_h_at(sx):
    i = min(NCOLS - 1, max(0, sx // STEP))
    return cols[i]


def gen_column():
    """Produce the next ground column height off-screen right.

    gen_flat counts down flat columns; negative counts crater columns; after
    a crater there is always a stretch of flat ground so gaps never exceed
    one jump.
    """
    global gen_flat
    if gen_flat > 0:
        gen_flat -= 1
        return GROUND_BASE + (random.getrandbits(8) % 3) * STEP - STEP
    if gen_flat < 0:
        gen_flat += 1
        if gen_flat == 0:
            gen_flat = flat_min // 2 + 20
        return -1
    if random.getrandbits(8) < 100:
        w = 6 + random.getrandbits(8) % max(1, crater_w_max - 5)
        gen_flat = -w
        return -1
    gen_flat = flat_min + random.getrandbits(8) % 50
    return GROUND_BASE + (random.getrandbits(8) % 3) * STEP - STEP


def spawn_rock():
    """Spawn a rock or big boulder at the right edge on local solid ground,
    never on/beside a crater and never clumped with another rock."""
    for i in range(NCOLS - 46, NCOLS):
        if cols[i] == -1:
            return
    for rk in rocks:
        if rk["x"] > SW - 70:
            return
    h = GROUND_BASE
    for i in range(NCOLS - 1, NCOLS - 12, -1):
        if cols[i] > 0:
            h = cols[i]
            break
    rocks.append({"x": SW + 8, "h": h, "big": random.getrandbits(8) < 70})


def set_level(n):
    """Deterministic layout + difficulty for level n."""
    global level, speed, crater_w_max, flat_min, rock_chance, big_lim
    global dive_chance
    level = n
    random.seed(2027 + n * 101)
    speed = min(4 + (n - 1) // 3, 7)
    crater_w_max = min(7 + n // 2, 13)
    flat_min = max(24, 64 - 5 * n)
    rock_chance = min(4 + n, 14)
    big_lim = min(40 + 5 * n, 85)
    dive_chance = min(1 + n // 2, 4)


def reset():
    global cols, rocks, ufos, bullets, score, lives, dist_m, world_cols
    global by, vy, airborne, invuln, fire_cd, gen_flat, since_jump
    global last_jump_d
    cols = []
    for _ in range(NCOLS):
        cols.append(GROUND_BASE)
    rocks = []
    ufos = []
    bullets = []
    score = 0
    lives = 3
    dist_m = 0
    world_cols = 0
    by = GROUND_BASE
    vy = 0
    airborne = False
    invuln = 0
    fire_cd = 0
    gen_flat = 60
    since_jump = 999
    last_jump_d = -1
    set_level(1)
    print("crater crawler level 1")


def scroll():
    """Shift terrain left, generate fresh ground, move entities."""
    global world_cols, dist_m
    for _ in range(speed // STEP):
        cols.pop(0)
        c = gen_column()
        cols.append(c)
        world_cols += 1
    dist_m = world_cols * STEP // 10
    for rk in rocks:
        rk["x"] -= speed
    for u in ufos:
        if u.get("mode") == "dive":
            u["x"] += u["vx"]
            u["y"] += u["vy"]
            if u["y"] > GROUND_BASE - 36:
                u["y"] = GROUND_BASE - 36  # pull up, never into the ground
        else:
            u["x"] -= 3
            u["ph"] += 0.15
            u["y"] = u["y0"] + int(10 * math.sin(u["ph"]))
    for b in bullets:
        b["x"] += b["vx"]
        b["y"] += b["vy"]
    if random.getrandbits(8) < rock_chance and len(rocks) < 3:
        spawn_rock()


def jump():
    global vy, airborne
    if not airborne:
        vy = -20
        airborne = True


def _fill_craters():
    for i in range(NCOLS):
        if cols[i] == -1:
            cols[i] = GROUND_BASE


def autopilot():
    global fire_cd
    # hop craters before any wheel crosses the lip. Decision distance varies
    # randomly so we can learn which timings clear and which do not, but the
    # scan always covers a fixed window so nothing sneaks in under a low roll.
    global since_jump, last_jump_d
    if not airborne:
        trig = 8 + random.getrandbits(8) % 19          # decide at 8..26 px
        for i in range((BUGGY_X + 2) // STEP,
                       min(NCOLS, (BUGGY_X + 30) // STEP)):
            if cols[i] == -1:
                d = i * STEP - BUGGY_X
                if d <= trig:
                    jump()
                    since_jump = 0
                    last_jump_d = d
                    print("JUMP crater d={} speed={} lvl={}".format(
                        d, speed, level))
                break
        else:
            tr = 12 + random.getrandbits(8) % 30       # 12..41 px
            for rk in rocks:
                d = rk["x"] - BUGGY_X
                if 0 < d < (tr + 20 if rk["big"] else tr):
                    jump()
                    since_jump = 0
                    last_jump_d = d
                    print("JUMP rock d={} big={} speed={} lvl={}".format(
                        d, rk["big"], speed, level))
                    break
    if fire_cd <= 0:
        gy = ground_h_at(BUGGY_X)
        # vertical shot at ufos passing overhead
        for u in ufos:
            if abs(u["x"] - (BUGGY_X + 14)) < 16 and u["y"] < GROUND_BASE - 20:
                bullets.append({"x": BUGGY_X + 14, "y": gy - 18,
                                "vx": 0, "vy": -8})
                fire_cd = 6
                break
        else:
            # horizontal cannon shot at small rocks ahead
            for rk in rocks:
                d = rk["x"] - BUGGY_X
                if 20 < d < 110 and not rk["big"]:
                    bullets.append({"x": BUGGY_X + 14, "y": rk["h"] - 10,
                                    "vx": 8, "vy": 0})
                    fire_cd = 5
                    break


def update_entities():
    """Move/collide bullets, rocks, ufos. Returns True on a buggy crash."""
    global score, invuln, fire_cd
    # bullets vs rocks / ufos
    for b in bullets[:]:
        hit = False
        for rk in rocks[:]:
            top = 18 if rk["big"] else 14
            if abs(rk["x"] - b["x"]) < (11 if rk["big"] else 9) \
                    and b["y"] > rk["h"] - top:
                if rk["big"]:
                    pass  # boulders shrug off cannon fire
                else:
                    rocks.remove(rk)
                    score += 25
                hit = True
                break
        if not hit:
            for u in ufos[:]:
                if abs(u["x"] - b["x"]) < 10 and abs(u["y"] - b["y"]) < 7:
                    ufos.remove(u)
                    score += 100
                    hit = True
                    break
        if hit or b["x"] > SW + 10 or b["y"] < 0 or b["y"] > SH:
            bullets.remove(b)
    crashed = False
    # ufos may start a dive at the buggy
    for u in ufos:
        if u.get("mode") != "dive" and u["x"] < SW - 40 \
                and random.getrandbits(8) < dive_chance:
            dx = BUGGY_X - u["x"]
            # pull up well above the road surface
            ty = min(GROUND_BASE - 46, by - 40)
            dy = ty - u["y"]
            n = max(1, (abs(dx) + abs(dy)) // 3)
            u["mode"] = "dive"
            u["vx"] = dx // n
            u["vy"] = max(-3, min(3, dy // n)) if dy else 1
    # a diving ufo reaching the buggy is a crash (cruisers are harmless)
    if invuln == 0:
        for u in ufos[:]:
            if u.get("mode") == "dive" \
                    and abs(u["x"] - BUGGY_X) < 13 \
                    and abs(u["y"] - (by - 8)) < 12:
                ufos.remove(u)
                crashed = True
                break
    # rocks vs buggy
    if invuln == 0 and not crashed:
        for rk in rocks[:]:
            lim = 15 if rk["big"] else 11
            if abs(rk["x"] - BUGGY_X) < lim and not airborne:
                rocks.remove(rk)
                crashed = True
                break
    # drove into a crater?
    if not airborne and not crashed and ground_h_at(BUGGY_X) == -1:
        crashed = True
    if invuln:
        invuln -= 1
    if fire_cd:
        fire_cd -= 1
    # spawn ufos now and then (always well above the ground)
    if random.getrandbits(8) < 3 and len(ufos) < 2:
        y0 = 36 + (random.getrandbits(8) % 19) * 4
        ufos.append({"x": SW + 20, "y0": y0, "y": y0, "ph": 0})
    ufos[:] = [u for u in ufos if -40 < u["x"] < SW + 60 and u["y"] < SH + 30]
    rocks[:] = [r for r in rocks if r["x"] > -20]
    return crashed


def physics():
    """Buggy vertical motion; returns True on a crash.

    While descending, any wheel over solid ground catches the rim, so a
    jump that nearly clears still lands instead of dying.
    """
    global by, vy, airborne
    gh = ground_h_at(BUGGY_X)
    if airborne:
        by += vy // 2
        vy += 3
        if vy >= 0:
            c_rear = ground_h_at(max(0, BUGGY_X - 12))
            c_front = ground_h_at(min(SW - 1, BUGGY_X + 12))
            support = None
            for c in (c_rear, gh, c_front):
                if c > 0 and by >= c:
                    support = c
                    break
            if support is not None:
                by = support
                airborne = False
                vy = 0
            elif by > SH + 20 or (
                    by > GROUND_BASE + 14
                    and c_rear == -1 and gh == -1 and c_front == -1):
                _fill_craters()
                return True  # fully inside a crater
    else:
        # strict rule: any wheel over the void while grounded = crash
        c_rear2 = ground_h_at(max(0, BUGGY_X - 12))
        c_front2 = ground_h_at(min(SW - 1, BUGGY_X + 12))
        if gh == -1 or c_rear2 == -1 or c_front2 == -1:
            _fill_craters()
            return True
        by = gh
    return False


def draw_buggy():
    x = BUGGY_X
    y = by
    if invuln and (frame // 4) % 2:
        return  # blink while invulnerable
    # wheels
    fill_circle(x - 8, y - 4, 4, GRAY)
    fill_circle(x + 8, y - 4, 4, GRAY)
    spoke = (frame // 3) % 2
    fb.fill_rect(x - 9 + spoke * 2, y - 5, 2, 2, BG)
    fb.fill_rect(x + 7 + spoke * 2, y - 5, 2, 2, BG)
    # body
    fb.fill_rect(x - 13, y - 12, 26, 5, YELLOW)
    fb.fill_rect(x - 9, y - 16, 12, 4, YELLOW)
    # turret + dish
    fb.fill_rect(x + 2, y - 20, 2, 8, YELLOW)
    fb.fill_rect(x - 14, y - 17, 3, 2, GRAY)


def draw():
    global frame
    fb.fill(BG)
    for sx, sy in stars:
        fb.fill_rect(sx, sy, 1, 1, GRAY)
    draw_ridge(far_ridge, world_cols * STEP * 0.2, NAVY)
    draw_ridge(near_ridge, world_cols * STEP * 0.45, PURPLE)
    # ground with craters rendered as dark pits, merged runs
    i = 0
    last_solid = GROUND_BASE
    while i < NCOLS:
        h = cols[i]
        j = i
        while j < NCOLS and cols[j] == h:
            j += 1
        x0 = i * STEP
        if h > 0:
            w = (j - i) * STEP
            fb.fill_rect(x0, h, w, SH - h, MAROON)
            fb.fill_rect(x0, h, w, 2, GRAY)
            last_solid = h
            i = j
        else:
            while j < NCOLS and cols[j] == -1:
                j += 1
            if j < NCOLS:
                right_h = cols[j]
            else:
                right_h = last_solid
            n = j - i
            surf = min(last_solid, right_h)
            # rounded bowl: elliptical depth profile across the crater
            for c in range(n):
                tt = (c + 0.5) / n
                depth = int(26 * math.sqrt(max(0, 1 - (2 * tt - 1) ** 2)))
                x = (i + c) * STEP
                if depth == 0:
                    continue
                fb.fill_rect(x, surf, STEP, depth, BG)
                fb.fill_rect(x, surf + depth, STEP, SH - surf - depth, MAROON)
                if depth <= 4:
                    fb.fill_rect(x, surf, STEP, 1, GRAY)  # rim lip
            i = j
    # rocks and boulders
    for rk in rocks:
        r = 8 if rk["big"] else 5
        fill_circle(rk["x"], rk["h"] - r, r, GRAY)
        fb.fill_rect(rk["x"] - 2, rk["h"] - r - 3, 2, 2, WHITE)
    # ufos
    for u in ufos:
        uy = u["y"]
        col = RED if u.get("mode") == "dive" else CYAN
        fb.fill_rect(u["x"] - 9, uy, 18, 4, col)
        fb.fill_rect(u["x"] - 4, uy - 3, 8, 3, col)
        for i in range(-6, 7, 4):
            fb.fill_rect(u["x"] + i, uy + 4, 2, 1, RED)
    # bullets
    for b in bullets:
        if b["vx"]:
            fb.fill_rect(b["x"], b["y"], 3, 1, WHITE)
        else:
            fb.fill_rect(b["x"], b["y"], 1, 4, WHITE)
    draw_buggy()
    fb.text("SCORE {}".format(score), 4, 2, WHITE)
    fb.text("{}m".format(dist_m), 130, 2, CYAN)
    for i in range(lives):
        fill_circle(306 - i * 14, 10, 5, GREEN)
    fb.show()
    frame += 1


games = 0
while True:
    games += 1
    reset()
    alive = True
    while alive:
        crashed = physics()
        if not crashed:
            autopilot()
            scroll()
            since_jump += 1
            if dist_m >= level * LEVEL_LEN_M:
                set_level(level + 1)
                print("-- level {} --".format(level))
            if update_entities():
                crashed = True
        if crashed:
            dbg_r = [(r["x"] - BUGGY_X, r["big"]) for r in rocks
                     if abs(r["x"] - BUGGY_X) < 40]
            dbg_u = [(u["x"] - BUGGY_X, int(u["y"]), u.get("mode"))
                     for u in ufos]
            dbg_ghs = [ground_h_at(max(0, min(SW - 1, BUGGY_X + o)))
                       for o in (-12, 0, 12)]
            print("CRASH air={} by={} ghs={} rocks={} ufos={} "
                  "jump_d={} ago={}".format(
                      airborne, by, dbg_ghs, dbg_r, dbg_u,
                      last_jump_d, since_jump))
            lives -= 1
            invuln = 80
            by = GROUND_BASE
            _fill_craters()
            vy = 0
            airborne = False
            if lives <= 0:
                alive = False
        draw()
        time.sleep_ms(35)
    draw()
    print("game {} over, score {} dist {}m".format(games, score, dist_m))
    fb.fill_rect(124, 110, 72, 24, BG)
    fb.rect(124, 110, 72, 24, WHITE)
    fb.text("GAME OVER", 126, 114, RED)
    fb.text(str(score), 160 - 4 * len(str(score)), 125, WHITE)
    fb.show()
    time.sleep_ms(2500)
