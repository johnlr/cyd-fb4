# fb4_space_intruders.py - self-playing space intruders demo using the fb4 module
# Touch is not wired up yet, so the ship drives itself: it tracks the lowest
# invader, dodges falling bombs and fires automatically.
import time
import random
import framebuf
import fb4

# palette indices
BG = 0
RED = 1
GREEN = 2
BLUE = 3
YELLOW = 4
MAGENTA = 6
WHITE = 9

ROW_COLORS = (MAGENTA, RED, RED, YELLOW, YELLOW)
N_COLS = 8
N_ROWS = 5
INV_W = 12
INV_H = 7
INV_GAP_X = 32
INV_GAP_Y = 18
TOP_Y = 24

PLAYER_W = 14
PLAYER_H = 5
PLAYER_Y = 224

# destructible shields (pixel-erodible bunkers)
SHIELD_W = 22
SHIELD_H = 14
SHIELD_Y = 192
SHIELD_XS = (29, 109, 189, 269)
SHIELD_SHAPE = (
    "......................",
    "...XXXXXXXXXXXXXXXX...",
    "..XXXXXXXXXXXXXXXXXX..",
    ".XXXXXXXXXXXXXXXXXXXX.",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXX........XXXXXXX",
    "XXXXXX..........XXXXXX",
    "XXXXX............XXXXX",
    "XXXXX............XXXXX",
    "XXXXX............XXXXX",
)

fb = fb4.FB4()
shields = []  # one GS4 FrameBuffer per bunker


def build_shields():
    global shields
    shields = []
    for sx in SHIELD_XS:
        buf = bytearray(SHIELD_W * SHIELD_H // 2)
        sfb = framebuf.FrameBuffer(buf, SHIELD_W, SHIELD_H, framebuf.GS4_HMSB)
        for r in range(SHIELD_H):
            row = SHIELD_SHAPE[r]
            for c in range(SHIELD_W):
                if row[c] == "X":
                    sfb.fill_rect(c, r, 1, 1, GREEN)
        shields.append(sfb)


def shield_hit(px, py):
    """Return (sfb, lx, ly) if a solid shield pixel is at absolute (px, py)."""
    for i in range(len(SHIELD_XS)):
        lx, ly = px - SHIELD_XS[i], py - SHIELD_Y
        if 0 <= lx < SHIELD_W and 0 <= ly < SHIELD_H and shields[i].pixel(lx, ly):
            return (shields[i], lx, ly)
    return None


def blast(sfb, lx, ly, r):
    """Erode a blast circle from a shield."""
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                x, y = lx + dx, ly + dy
                if 0 <= x < SHIELD_W and 0 <= y < SHIELD_H:
                    sfb.fill_rect(x, y, 1, 1, BG)


def reset():
    global inv, ox, oy, odir, px, shots, bombs, score, cooldown, step_ms
    inv = [(c, r) for r in range(N_ROWS) for c in range(N_COLS)]
    ox = 20
    oy = 0
    odir = 1
    px = 152
    shots = []   # [x, y]
    bombs = []   # [x, y]
    score = 0
    cooldown = 0
    step_ms = 300
    build_shields()


def inv_rect(c, r):
    return (ox + c * INV_GAP_X, TOP_Y + oy + r * INV_GAP_Y)


def draw():
    fb.fill(BG)
    for c, r in inv:
        x, y = inv_rect(c, r)
        col = ROW_COLORS[r]
        fb.fill_rect(x, y, INV_W, INV_H - 2, col)
        fb.fill_rect(x + 2, y + INV_H - 3, INV_W - 4, 1, col)
        fb.fill_rect(x + 1, y + INV_H - 1, 2, 1, col)
        fb.fill_rect(x + INV_W - 3, y + INV_H - 1, 2, 1, col)
    # player ship
    fb.fill_rect(px, PLAYER_Y, PLAYER_W, PLAYER_H, GREEN)
    fb.fill_rect(px + PLAYER_W // 2 - 1, PLAYER_Y - 4, 2, 4, GREEN)
    for i in range(len(SHIELD_XS)):
        fb.blit(shields[i], SHIELD_XS[i], SHIELD_Y)
    for sx, sy in shots:
        fb.fill_rect(sx, sy, 2, 6, WHITE)
    for bx, by in bombs:
        fb.fill_rect(bx, by, 2, 5, BLUE)
    fb.text("SCORE {}".format(score), 8, 2, WHITE)
    fb.show()


def lowest_in_col(c):
    best = None
    for cc, r in inv:
        if cc == c and (best is None or r > best):
            best = r
    return best


def autopilot():
    global cooldown
    # target: column of the lowest invader overall
    tx = None
    best_r = -1
    for c, r in inv:
        if r > best_r:
            best_r = r
            tx = inv_rect(c, r)[0] + INV_W // 2
    if tx is None:
        return
    cx = px + PLAYER_W // 2
    # dodge nearby bombs first
    for bx, by in bombs:
        if abs(bx - cx) < 20 and by > PLAYER_Y - 60:
            cx_t = bx + 24 if bx < cx else bx - 24
            tx = max(8, min(304, cx_t))
            break
    if cx < tx:
        px_step(3)
    elif cx > tx:
        px_step(-3)
    # fire when aligned and cooled down
    if cooldown <= 0:
        col = None
        for c in range(N_COLS):
            x, _ = inv_rect(c, 0)
            if x <= cx < x + INV_GAP_X - (INV_GAP_X - INV_W):
                col = c
                break
        if col is not None and lowest_in_col(col) is not None:
            shots.append([cx - 1, PLAYER_Y - 6])
            cooldown = 4


def px_step(dx):
    global px
    px = max(2, min(320 - PLAYER_W - 2, px + dx))


def march():
    """Move formation; returns False if invaders reached the player."""
    global ox, oy, odir, step_ms
    min_x = min(inv_rect(c, 0)[0] for c, r in inv)
    max_x = max(inv_rect(c, 0)[0] for c, r in inv)
    nx = ox + odir * 6
    lo = min_x + odir * 6
    hi = lo + (max_x - min_x)
    if hi > 306 or lo < 4:
        odir = -odir
        oy += 6
        step_ms = max(180, step_ms - 8)
    else:
        ox = nx
    bottom = max(inv_rect(0, r)[1] for c, r in inv) + INV_H
    if bottom >= PLAYER_Y:
        return False
    return True


def update_shots():
    global score
    keep = []
    for s in shots:
        s[1] -= 12
        # shield check first (sample tip and mid of the shot)
        sh = shield_hit(s[0], s[1]) or shield_hit(s[0], s[1] + 6)
        if sh:
            blast(sh[0], sh[1], sh[2], 3)
            continue
        hit = False
        for c, r in inv:
            x, y = inv_rect(c, r)
            if x - 1 <= s[0] <= x + INV_W and y - 6 <= s[1] <= y + INV_H:
                inv.remove((c, r))
                score += (N_ROWS - r) * 10
                hit = True
                break
        if not hit and s[1] > 10:
            keep.append(s)
    shots[:] = keep


def update_bombs():
    global bombs
    keep = []
    for b in bombs:
        b[1] += 9
        if b[1] >= PLAYER_Y and px - 2 <= b[0] <= px + PLAYER_W:
            return False  # player hit
        # shield check (sample tip and mid of the bomb)
        sh = shield_hit(b[0], b[1] + 5) or shield_hit(b[0], b[1] + 2)
        if sh:
            blast(sh[0], sh[1], sh[2], 3)
            continue  # bomb consumed by the shield
        if b[1] < 236:
            keep.append(b)
    bombs[:] = keep
    return True


def drop_bomb():
    cols = {}
    for c, r in inv:
        if c not in cols or r > cols[c]:
            cols[c] = r
    if cols:
        c = random.choice(list(cols.keys()))
        x, y = inv_rect(c, cols[c])
        bombs.append([x + INV_W // 2, y + INV_H])


games = 0
while True:
    games += 1
    reset()
    alive = True
    while alive and inv:
        autopilot()
        if not march():
            alive = False
        update_shots()
        if not update_bombs():
            alive = False
        if cooldown:
            cooldown -= 1
        if inv and random.getrandbits(8) < 40:
            drop_bomb()
        draw()
        time.sleep_ms(step_ms // 4)
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
