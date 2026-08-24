# fb4_pillman.py - self-playing pac-man style demo using the fb4 module
# Touch is not wired up yet, so pill-mill drives itself: it greedily hunts
# the nearest pellet (BFS pathfinding when few remain) and flees ghosts.
# Ghosts start in the ghost house, are released one by one, chase with some
# randomness, and can be eaten for a while after a power pill is eaten.
import time
import random
import framebuf
import fb4

BG = 0
RED = 1
GREEN = 2
BLUE = 3
YELLOW = 4
CYAN = 5
MAGENTA = 6
ORANGE = 7
WHITE = 9
MAROON = 10
PINK = 14

TS = 16
COLS = 20
ROWS = 15

MAZE = (
    "####################",
    "#........##........#",
    "#.##.###.##.###.##.#",
    "#..................#",
    "#.##.#.##..##.#.##.#",
    "#....#........#....#",
    "####.####..####.####",
    "####.##......##.####",
    "####.##.####.##.####",
    "#......#....#......#",
    "#.####.#.##.#.####.#",
    "#.#......##......#.#",
    "#.#.####.##.####.#.#",
    "#........##........#",
    "####################",
)

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
GHOST_COLORS = (RED, MAGENTA, CYAN, ORANGE)
PSPEED = 4
FEAR_MS = 6000

# ghost house interior (no pellets, ghosts spawn here) and its door tiles
HOUSE = frozenset(
    ((7, 7), (8, 7), (9, 7), (10, 7), (11, 7), (12, 7), (7, 8), (12, 8))
)
DOOR = frozenset(((9, 6), (10, 6)))
BLOCKED = HOUSE | DOOR  # pill-mill may never enter; ghosts only from inside
POWER_POS = frozenset(((1, 3), (18, 3), (1, 11), (18, 11)))

# bonus fruit: appears twice per level below the ghost house, 9 s each time
FRUIT_TILE = (10, 9)
FRUIT_PTS = (100, 300, 500, 700, 1000)
SPRITE_COLS = {"R": RED, "G": GREEN, "O": ORANGE, "M": MAROON, "P": PINK}
FRUITS = (
    # cherry
    ("........",
     "...GG...",
     "..G.....",
     "..G.....",
     ".RR.RR..",
     "RRRR.RR.",
     "RRRR.RRR",
     ".RR..RR."),
    # strawberry
    ("........",
     "...GG...",
     "..GGG...",
     ".RRRRR..",
     "RRRRRRR.",
     "RPRPRPR.",
     ".RRRRR..",
     "..RRR..."),
    # orange
    ("........",
     "...GG...",
     "..GG....",
     ".OOOOO..",
     "OOOOOOO.",
     "OOOOOOO.",
     "OOOOOOO.",
     ".OOOOO.."),
    # apple
    ("........",
     "...G....",
     "..G.....",
     ".MMMMM..",
     "MMMMMMM.",
     "MMMMMMM.",
     "MMMMMMM.",
     ".MMMMM.."),
    # melon
    ("........",
     ".GGGGG..",
     "GGGGGGG.",
     "GGGGGGG.",
     "GGGGGGG.",
     "GGGGGGG.",
     ".GGGGG..",
     "........"),
)

fb = fb4.FB4()

# pre-rendered wall layer, blitted each frame: arcade-style double blue lines
# drawn along the edges where a wall tile faces open corridor
wall_buf = bytearray(320 * 240 // 2)
wall_fb = framebuf.FrameBuffer(wall_buf, 320, 240, framebuf.GS4_HMSB)


def is_wall(tx, ty):
    return tx < 0 or tx >= COLS or ty < 0 or ty >= ROWS or MAZE[ty][tx] == "#"


for ty in range(ROWS):
    for tx in range(COLS):
        if MAZE[ty][tx] != "#":
            continue
        x, y = tx * TS, ty * TS
        if not is_wall(tx, ty - 1):
            wall_fb.hline(x, y + 1, TS, BLUE)
            wall_fb.hline(x, y + 3, TS, BLUE)
        if not is_wall(tx, ty + 1):
            wall_fb.hline(x, y + 14, TS, BLUE)
            wall_fb.hline(x, y + 12, TS, BLUE)
        if not is_wall(tx - 1, ty):
            wall_fb.vline(x + 1, y, TS, BLUE)
            wall_fb.vline(x + 3, y, TS, BLUE)
        if not is_wall(tx + 1, ty):
            wall_fb.vline(x + 14, y, TS, BLUE)
            wall_fb.vline(x + 12, y, TS, BLUE)
# ghost house door: pink gate
wall_fb.hline(9 * TS, 6 * TS + 2, 2 * TS, MAGENTA)


def tile_of(e):
    return ((e[0] - 8) // TS, (e[1] - 8) // TS)


def fill_circle(cx, cy, r, col):
    r2 = r * r
    for dy in range(-r, r + 1):
        w = int((r2 - dy * dy) ** 0.5)
        fb.fill_rect(cx - w, cy + dy, 2 * w + 1, 1, col)


MOUTH = (0, 1, 2, 3, 2, 1)  # wedge openness, cycles while moving
mouth_phase = 0


def draw_pac(cx, cy, hx, hy, ot):
    fill_circle(cx, cy, 6, YELLOW)
    if ot:
        for sy in range(-6, 7):
            for sx in range(-6, 7):
                f = sx * hx + sy * hy
                s = -sy * hx + sx * hy
                if f >= 3 and -((f - 2) * ot) <= s * 3 <= (f - 2) * ot:
                    fb.fill_rect(cx + sx, cy + sy, 1, 1, BG)


def draw_ghost(g, col, fright, flash):
    x, y = g[0], g[1]
    body = (WHITE if flash else BLUE) if fright else col
    fb.fill_rect(x - 5, y - 6, 11, 9, body)
    for i in range(3):
        fb.fill_rect(x - 5 + i * 4, y + 3, 3, 2, body)
    fb.fill_rect(x - 4, y - 4, 3, 3, WHITE)
    fb.fill_rect(x + 2, y - 4, 3, 3, WHITE)
    pupil = BG if fright else BLUE
    fb.fill_rect(x - 3 + g[2], y - 3 + g[3], 2, 2, pupil)
    fb.fill_rect(x + 3 + g[2], y - 3 + g[3], 2, 2, pupil)


pac = [0, 0, 1, 0]
ghosts = [[0, 0, 0, -1] for _ in range(4)]
pellets = set()
power = set()
score = 0
lives = 3
level = 1
release_at = [0, 0, 0, 0]
fright_until = [0, 0, 0, 0]
active = [False, False, False, False]
fruit_on = False
fruit_until = 0
fruit_stage = 0
fruit_at = [0, 0]
fruit_popup_until = 0
fruit_popup_pts = 0


def draw_sprite(spr, px, py):
    for r in range(len(spr)):
        row = spr[r]
        for c in range(len(row)):
            ch = row[c]
            if ch != ".":
                fb.fill_rect(px + c, py + r, 1, 1, SPRITE_COLS[ch])


def init_level():
    global fruit_stage, fruit_on
    pellets.clear()
    power.clear()
    fruit_stage = 0
    fruit_on = False
    for ty in range(ROWS):
        for tx in range(COLS):
            if MAZE[ty][tx] != ".":
                continue
            t = (tx, ty)
            if t in BLOCKED:
                continue
            if t in POWER_POS:
                power.add(t)
            else:
                pellets.add(t)
    total = len(pellets) + len(power)
    fruit_at[0] = total * 2 // 3   # appears when 1/3 eaten
    fruit_at[1] = total // 3       # and when 2/3 eaten


def reset_positions():
    global fruit_on
    fruit_on = False
    now = time.ticks_ms()
    pac[0] = 9 * TS + 8
    pac[1] = 9 * TS + 8
    pac[2] = 1
    pac[3] = 0
    slots = ((7, 7), (9, 7), (11, 7), (12, 7))
    for i, s in enumerate(slots):
        g = ghosts[i]
        g[0] = s[0] * TS + 8
        g[1] = s[1] * TS + 8
        g[2] = 0
        g[3] = -1
        active[i] = False
        fright_until[i] = now
        release_at[i] = time.ticks_add(now, 1200 + i * 1800)


def bfs_dir(stx, sty):
    """BFS to the nearest remaining target; returns the first step direction."""
    targets = pellets or power
    prev = {(stx, sty): None}
    queue = [(stx, sty)]
    qi = 0
    found = None
    while qi < len(queue):
        cx, cy = queue[qi]
        qi += 1
        if (cx, cy) in targets:
            found = (cx, cy)
            break
        for dd in DIRS:
            nx, ny = cx + dd[0], cy + dd[1]
            if is_wall(nx, ny) or (nx, ny) in BLOCKED:
                continue
            if (nx, ny) not in prev:
                prev[(nx, ny)] = (cx, cy)
                queue.append((nx, ny))
    if found is None:
        return None
    cur = found
    while prev[cur] != (stx, sty):
        cur = prev[cur]
    return (cur[0] - stx, cur[1] - sty)


def hunters():
    """Return list of (gi, g) for active, non-frightened ghosts."""
    now = time.ticks_ms()
    out = []
    for gi in range(4):
        if active[gi] and time.ticks_diff(fright_until[gi], now) <= 0:
            out.append((gi, ghosts[gi]))
    return out


def path_threat(tx, ty, dd, hs):
    """Squared distance of the nearest hunter to pill-mill's path if it
    goes direction dd (looks ahead a few tiles down the corridor)."""
    best = 1 << 62
    cx, cy = tx, ty
    for _ in range(3):
        nx, ny = cx + dd[0], cy + dd[1]
        if is_wall(nx, ny) or (nx, ny) in BLOCKED:
            break
        cx, cy = nx, ny
        px, py = cx * TS + 8, cy * TS + 8
        for _, g in hs:
            d = (g[0] - px) ** 2 + (g[1] - py) ** 2
            if d < best:
                best = d
    return best


MISTAKE = 20  # out of 256: chance of NOT dodging (keeps the game fallible)


def ai_pac():
    x, y, pdx, pdy = pac
    tx, ty = tile_of(pac)
    opts = []
    for dd in DIRS:
        nx, ny = tx + dd[0], ty + dd[1]
        if not is_wall(nx, ny) and (nx, ny) not in BLOCKED:
            opts.append(dd)
    if not opts:
        return
    rev = (-pdx, -pdy)
    cand = [dd for dd in opts if dd != rev] or opts
    now = time.ticks_ms()
    hs = hunters()

    # imminent collision ahead? dodge, but allow the odd mistake
    cur_threat = path_threat(tx, ty, (pdx, pdy), hs)
    if cur_threat < 40 * 40 and random.getrandbits(8) >= MISTAKE:
        best, bk, bd = cand[0], 1 << 62, 1 << 62
        for dd in cand:
            t = path_threat(tx, ty, dd, hs)
            md = 1 << 62
            for _, g in hs:
                nx, ny = x + dd[0] * TS, y + dd[1] * TS
                d = (g[0] - nx) ** 2 + (g[1] - ny) ** 2
                if d < md:
                    md = d
            key = t * 4 + (dd != (pdx, pdy))
            if key < bk or (key == bk and md < bd):
                bk, bd, best = key, md, dd
        pac[2], pac[3] = best
        return

    # power mode: chase an edible ghost that is close by
    cg, cgd = None, 100 * 100
    for gi in range(4):
        if active[gi] and time.ticks_diff(fright_until[gi], now) > 0:
            g = ghosts[gi]
            d = (g[0] - x) ** 2 + (g[1] - y) ** 2
            if d < cgd:
                cgd, cg = d, g
    if cg is not None:
        best, bd = cand[0], 1 << 62
        for dd in cand:
            nx, ny = x + dd[0] * TS, y + dd[1] * TS
            d = (cg[0] - nx) ** 2 + (cg[1] - ny) ** 2
            key = d * 4 + (dd != (pdx, pdy))
            if key < bd:
                bd, best = key, dd
        pac[2], pac[3] = best
        return

    if len(pellets) <= 12:
        # endgame: use real pathfinding so pill-mill doesn't dither
        dd = bfs_dir(tx, ty)
        if dd is not None:
            pac[2], pac[3] = dd
            return
        pac[2], pac[3] = cand[0]
    else:
        # hunt nearest target, prefer going straight
        best, bd = cand[0], 1 << 62
        for dd in cand:
            ntx, nty = tx + dd[0], ty + dd[1]
            pd2 = 1 << 62
            for p in pellets:
                d = (p[0] - ntx) ** 2 + (p[1] - nty) ** 2
                if d < pd2:
                    pd2 = d
            for p in power:
                d = ((p[0] - ntx) ** 2 + (p[1] - nty) ** 2) // 2
                if d < pd2:
                    pd2 = d
            key = pd2 * 4 + (dd != (pdx, pdy))
            if key < bd:
                bd, best = key, dd
        pac[2], pac[3] = best


def ai_ghost(gi):
    g = ghosts[gi]
    x, y, gdx, gdy = g[0], g[1], g[2], g[3]
    tx, ty = tile_of(g)
    if (tx, ty) in HOUSE:
        # inside the house: head for the door columns and go up
        if tx < 9:
            g[2], g[3] = 1, 0
        elif tx > 10:
            g[2], g[3] = -1, 0
        else:
            g[2], g[3] = 0, -1
        return
    opts = []
    for dd in DIRS:
        nx, ny = tx + dd[0], ty + dd[1]
        if is_wall(nx, ny) or (nx, ny) in BLOCKED:
            continue
        opts.append(dd)
    if not opts:
        return
    rev = (-gdx, -gdy)
    cand = [dd for dd in opts if dd != rev] or opts
    now = time.ticks_ms()
    if time.ticks_diff(fright_until[gi], now) > 0:
        # frightened: mostly random, sometimes run away
        if random.getrandbits(8) < 70:
            dd = cand[random.getrandbits(8) % len(cand)]
        else:
            bd, dd = -1, cand[0]
            for c in cand:
                nx, ny = x + c[0] * TS, y + c[1] * TS
                d = (pac[0] - nx) ** 2 + (pac[1] - ny) ** 2
                if d > bd:
                    bd, dd = d, c
    else:
        bd, dd = 1 << 62, cand[0]
        for c in cand:
            nx, ny = x + c[0] * TS, y + c[1] * TS
            d = (pac[0] - nx) ** 2 + (pac[1] - ny) ** 2
            if d < bd:
                bd, dd = d, c
    g[2], g[3] = dd


def advance(e, sp):
    """Move e 1px at a time; returns True the moment a tile center is
    crossed so the caller can decide a new direction before moving on."""
    for _ in range(sp):
        e[0] += e[2]
        e[1] += e[3]
        if (e[0] - 8) % TS == 0 and (e[1] - 8) % TS == 0:
            return True
    return False


def draw():
    fb.fill(BG)
    fb.blit(wall_fb, 0, 0)
    for p in pellets:
        fb.fill_rect(p[0] * TS + 7, p[1] * TS + 7, 3, 3, WHITE)
    if (time.ticks_ms() // 250) % 2:
        for p in power:
            fb.fill_rect(p[0] * TS + 5, p[1] * TS + 5, 7, 7, WHITE)
    if fruit_on:
        draw_sprite(
            FRUITS[min(level - 1, len(FRUITS) - 1)],
            FRUIT_TILE[0] * TS + 4,
            FRUIT_TILE[1] * TS + 4,
        )
    if time.ticks_diff(fruit_popup_until, time.ticks_ms()) > 0:
        fb.text(str(fruit_popup_pts), FRUIT_TILE[0] * TS - 6, FRUIT_TILE[1] * TS, PINK)
    now = time.ticks_ms()
    for gi in range(4):
        rem = time.ticks_diff(fright_until[gi], now)
        fr = rem > 0
        flash = fr and rem < 2000 and (now // 250) % 2
        draw_ghost(ghosts[gi], GHOST_COLORS[gi], fr, flash)
    draw_pac(pac[0], pac[1], pac[2], pac[3], MOUTH[mouth_phase])
    fb.text("SCORE {}".format(score), 4, 2, WHITE)
    for i in range(lives):
        fill_circle(306 - i * 14, 10, 5, YELLOW)
    fb.show()


games = 0
while True:
    games += 1
    score = 0
    lives = 3
    level = 1
    init_level()
    reset_positions()
    running = True
    while running:
        now = time.ticks_ms()
        gspeed = min(3 + (level - 1), 5)
        if advance(pac, PSPEED):
            t = tile_of(pac)
            if t in pellets:
                pellets.discard(t)
                score += 10
            elif t in power:
                power.discard(t)
                score += 50
                for i in range(4):
                    fright_until[i] = time.ticks_add(now, FEAR_MS)
            if fruit_on and t == FRUIT_TILE:
                fruit_on = False
                fruit_popup_pts = FRUIT_PTS[min(level - 1, len(FRUITS) - 1)]
                score += fruit_popup_pts
                fruit_popup_until = time.ticks_add(now, 1200)
            ai_pac()
        if pac[2] or pac[3]:
            mouth_phase = (mouth_phase + 1) % len(MOUTH)
        remaining = len(pellets) + len(power)
        if not fruit_on and fruit_stage < 2 and remaining <= fruit_at[fruit_stage]:
            fruit_on = True
            fruit_until = time.ticks_add(now, 9000)
            fruit_stage += 1
        elif fruit_on and time.ticks_diff(fruit_until, now) <= 0:
            fruit_on = False
        for gi in range(4):
            g = ghosts[gi]
            if not active[gi]:
                if time.ticks_diff(now, release_at[gi]) >= 0:
                    active[gi] = True
                    ai_ghost(gi)  # house nav steers it to the door
                else:
                    continue
            sp = 2 if time.ticks_diff(fright_until[gi], now) > 0 else gspeed
            if advance(g, sp):
                ai_ghost(gi)
        caught = False
        for gi in range(4):
            g = ghosts[gi]
            if (g[0] - pac[0]) ** 2 + (g[1] - pac[1]) ** 2 < 81:
                if time.ticks_diff(fright_until[gi], now) > 0:
                    # pill-mill eats the ghost; it returns to the house
                    score += 200
                    fright_until[gi] = now
                    g[0] = 9 * TS + 8
                    g[1] = 7 * TS + 8
                    g[2] = 0
                    g[3] = -1
                    active[gi] = False
                    release_at[gi] = time.ticks_add(now, 4000)
                else:
                    caught = True
        if caught:
            lives -= 1
            draw()
            if lives <= 0:
                running = False
            else:
                time.sleep_ms(600)
                reset_positions()
            continue
        if not pellets and not power:
            score += 500
            print("level {} cleared".format(level))
            level += 1
            init_level()
            reset_positions()
            time.sleep_ms(400)
        draw()
        time.sleep_ms(15)
    draw()
    print("game {} over, score {}".format(games, score))
    fb.fill_rect(120, 106, 80, 34, BG)
    fb.rect(120, 106, 80, 34, WHITE)
    t1 = "GAME OVER"
    fb.text(t1, 160 - 4 * len(t1), 113, RED)
    t2 = str(score)
    fb.text(t2, 160 - 4 * len(t2), 127, WHITE)
    fb.show()
    time.sleep_ms(2500)
