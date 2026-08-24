# fb4_rock_runner.py - self-playing boulder-dash style demo using fb4
# Touch is not wired up yet, so the runner drives itself: BFS pathfinding to
# the nearest diamond (avoiding cells under loose rocks), then to the exit.
# Rocks and diamonds fall when unsupported; boulders roll off edges; a rock
# landing on the runner costs a life.
import time
import random
import fb4

TS = 16
COLS = 20
ROWS = 14
FIELD_Y = 16

# palette indices
BG = 0
RED = 1
GREEN = 2
YELLOW = 4
CYAN = 5
PURPLE = 8
WHITE = 9
MAROON = 10
GRAY = 15

# tile types
EMPTY = 0
WALL_T = 1
DIRT = 2
ROCK = 3
GEM = 4
EXIT_T = 5

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))

fb = fb4.FB4()

grid = []
px = 1
py = 1
exit_pos = (COLS - 2, ROWS - 2)
gems_left = 0
gems_total = 0
need = 0
exit_open = False
score = 0
lives = 3
level = 1
dead = False
won = False
roll_pref = 1
hang = set()

GEM_ROWS = ((7, 2), (5, 6), (5, 6), (3, 10), (3, 10), (5, 6), (5, 6), (7, 2))


def fill_circle(cx, cy, r, col):
    r2 = r * r
    for dy in range(-r, r + 1):
        w = int((r2 - dy * dy) ** 0.5)
        fb.fill_rect(cx - w, cy + dy, 2 * w + 1, 1, col)


def gen_cave():
    """Carve-first cave generation: solvable by construction.

    1. Fill everything with dirt.
    2. Carve a guaranteed corridor from the start to the exit, plus extra
       wandering tunnels (the walkable network).
    3. Put gems on corridor cells and in dirt right next to corridors, so
       every gem is reachable without touching any rock hazard.
    4. Only place rocks in solid dirt pockets that cannot fall or roll into
       a corridor (dirt below and on both sides/diagonals).
    """
    global grid, px, py, gems_left, gems_total, need, exit_open, dead, won, hang
    ex, ey = exit_pos
    for _ in range(80):
        g = [[DIRT] * COLS for _ in range(ROWS)]
        for x in range(COLS):
            g[0][x] = WALL_T
            g[ROWS - 1][x] = WALL_T
        for y in range(ROWS):
            g[y][0] = WALL_T
            g[y][COLS - 1] = WALL_T
        # main tunnel: biased random walk from start to exit
        cx, cy = 1, 1
        g[cy][cx] = EMPTY
        while (cx, cy) != (ex, ey):
            r = random.getrandbits(8)
            if r < 90 and cx < ex:
                cx += 1
            elif r < 140 and cx > ex:
                cx -= 1
            elif r < 200 and cy < ey:
                cy += 1
            elif r < 230 and cy > ey:
                cy -= 1
            else:
                dd = DIRS[random.getrandbits(8) % 4]
                nx, ny = cx + dd[0], cy + dd[1]
                if 1 <= nx < COLS - 1 and 1 <= ny < ROWS - 1:
                    cx, cy = nx, ny
            g[cy][cx] = EMPTY
        # extra wandering tunnels so the cave isn't one long snake
        wx, wy = 1, 1
        for _ in range(COLS * ROWS // 3):
            dd = DIRS[random.getrandbits(8) % 4]
            nx, ny = wx + dd[0], wy + dd[1]
            if 1 <= nx < COLS - 1 and 1 <= ny < ROWS - 1:
                wx, wy = nx, ny
                g[wy][wx] = EMPTY
        # stamp the exit where the main tunnel ended
        g[ey][ex] = EXIT_T
        # rocks only where they cannot fall or roll into open space
        for y in range(1, ROWS - 1):
            for x in range(1, COLS - 1):
                if g[y][x] != DIRT:
                    continue
                if g[y + 1][x] != DIRT:
                    continue
                if g[y][x - 1] == EMPTY or g[y][x + 1] == EMPTY:
                    continue
                if g[y + 1][x - 1] == EMPTY or g[y + 1][x + 1] == EMPTY:
                    continue
                if random.getrandbits(8) < 45:
                    g[y][x] = ROCK
        # gems: on corridor floor cells (solid below, so nothing rains down
        # at the start), then in dirt beside corridors
        gems = []
        open_cells = [
            (x, y)
            for y in range(1, ROWS - 1)
            for x in range(1, COLS - 1)
            if g[y][x] == EMPTY
            and g[y + 1][x] != EMPTY
            and (x, y) != (1, 1)
            and (x, y) != (ex, ey)
        ]
        for i in range(len(open_cells)):
            t = open_cells[(random.getrandbits(8) * 251 + i * 7) % len(open_cells)]
            if g[t[1]][t[0]] == EMPTY:
                g[t[1]][t[0]] = GEM
                gems.append(t)
            if len(gems) >= 14:
                break
        for y in range(1, ROWS - 1):
            for x in range(1, COLS - 1):
                if len(gems) >= 20:
                    break
                if g[y][x] != DIRT or g[y - 1][x] == ROCK:
                    continue
                if any(g[y + d[1]][x + d[0]] == EMPTY for d in DIRS):
                    if random.getrandbits(8) < 60:
                        g[y][x] = GEM
                        gems.append((x, y))
        if len(gems) < 10:
            continue
        grid = g
        px = 1
        py = 1
        gems_left = len(gems)
        gems_total = len(gems)
        need = max(4, len(gems) // 2)
        exit_open = False
        dead = False
        won = False
        hang = set()
        return


def compute_danger():
    """Cells threatened by falling or rolling rocks/gems: the whole
    unobstructed column below any loose object, plus roll-off paths where a
    supported rock has an open side."""
    d = set()
    for x in range(1, COLS - 1):
        falling = False
        for y in range(1, ROWS):
            t = grid[y][x]
            if t in (ROCK, GEM):
                falling = True
            elif t == EMPTY:
                if falling:
                    d.add((x, y))
            else:
                falling = False
    # rolling: a rock with support that can tip sideways into open space
    for y in range(1, ROWS - 1):
        for x in range(1, COLS - 1):
            if grid[y][x] != ROCK or grid[y + 1][x] == EMPTY:
                continue
            for dx in (-1, 1):
                if grid[y][x + dx] == EMPTY and grid[y + 1][x + dx] == EMPTY:
                    yy = y
                    while yy < ROWS - 1 and grid[yy + 1][x + dx] == EMPTY:
                        yy += 1
                        d.add((x + dx, yy))
    return d


def bfs_step(targets, allow_danger, danger):
    """First step of the shortest path to any target; None if unreachable."""
    sx, sy = px, py
    prev = {(sx, sy): None}
    q = [(sx, sy)]
    qi = 0
    while qi < len(q):
        cx, cy = q[qi]
        qi += 1
        if (cx, cy) in targets:
            cur = (cx, cy)
            while prev[cur] != (sx, sy):
                cur = prev[cur]
            return (cur[0] - sx, cur[1] - sy)
        for dd in DIRS:
            nx, ny = cx + dd[0], cy + dd[1]
            if not (1 <= nx < COLS - 1 and 1 <= ny < ROWS - 1):
                continue
            t = grid[ny][nx]
            if t in (WALL_T, ROCK):
                continue
            if t == EXIT_T and not exit_open:
                continue
            if not allow_danger and (nx, ny) in danger and (nx, ny) not in targets:
                continue
            if (nx, ny) not in prev:
                prev[(nx, ny)] = (cx, cy)
                q.append((nx, ny))
    return None


def ai_dir(danger):
    targets = set()
    if gems_left > 0:
        for y in range(ROWS):
            for x in range(COLS):
                if grid[y][x] == GEM:
                    targets.add((x, y))
    else:
        targets.add(exit_pos)
    dd = bfs_step(targets, False, danger)
    if dd is None:
        dd = bfs_step(targets, True, danger)
    return dd


def try_move(dd):
    global px, py, score, gems_left, exit_open, won
    nx, ny = px + dd[0], py + dd[1]
    t = grid[ny][nx]
    if t in (WALL_T, ROCK):
        return
    if t == EXIT_T and not exit_open:
        return
    if t == DIRT:
        grid[ny][nx] = EMPTY
    elif t == GEM:
        grid[ny][nx] = EMPTY
        score += 100
        gems_left -= 1
        if gems_total - gems_left >= need:
            exit_open = True
    elif t == EXIT_T and exit_open:
        won = True
        return
    px, py = nx, ny


def physics():
    """One gravity step for rocks and gems; returns True if the runner died.

    An object whose support was just dug away hangs for one tick (like real
    Boulder Dash) so the runner has a frame to escape; if he is still
    underneath on the next tick, he is crushed.
    """
    global roll_pref, hang
    roll_pref ^= 1
    new_hang = set()
    died = False
    for y in range(ROWS - 2, 0, -1):
        for x in range(1, COLS - 1):
            t = grid[y][x]
            if t != ROCK and t != GEM:
                continue
            below = grid[y + 1][x]
            if below == EMPTY:
                if x == px and y + 1 == py:
                    if (x, y) in hang:
                        died = True  # lingered under a loose object
                    else:
                        new_hang.add((x, y))  # one-tick grace
                    continue
                grid[y + 1][x] = t
                grid[y][x] = EMPTY
            elif t == ROCK and below != EMPTY:
                # boulders roll off edges (diamonds just pile up)
                first, second = (-1, 1) if roll_pref else (1, -1)
                for dx in (first, second):
                    if grid[y][x + dx] == EMPTY and grid[y + 1][x + dx] == EMPTY:
                        if x + dx == px and y == py:
                            if (x, y) in hang:
                                died = True
                            else:
                                new_hang.add((x, y))
                            break
                        grid[y][x + dx] = t
                        grid[y][x] = EMPTY
                        break
    hang = new_hang
    return died


def draw():
    fb.fill(BG)
    now = time.ticks_ms()
    blink = (now // 300) % 2
    for y in range(ROWS):
        for x in range(COLS):
            t = grid[y][x]
            X = x * TS
            Y = FIELD_Y + y * TS
            if t == WALL_T:
                fb.fill_rect(X + 1, Y + 1, TS - 2, TS - 2, GRAY)
            elif t == DIRT:
                fb.fill_rect(X + 2, Y + 2, TS - 4, TS - 4, MAROON)
                fb.fill_rect(X + 4, Y + 4, 2, 2, PURPLE)
                fb.fill_rect(X + 10, Y + 9, 2, 2, PURPLE)
            elif t == ROCK:
                fill_circle(X + 8, Y + 8, 6, GRAY)
                fb.fill_rect(X + 5, Y + 4, 2, 2, WHITE)
            elif t == GEM:
                for i in range(len(GEM_ROWS)):
                    xo, w = GEM_ROWS[i]
                    fb.fill_rect(X + xo, Y + 4 + i, w, 1, CYAN)
            elif t == EXIT_T:
                col = GREEN if (exit_open and blink) else RED
                fb.rect(X + 2, Y + 2, TS - 4, TS - 4, col)
                if exit_open and blink:
                    fb.fill_rect(X + 5, Y + 5, TS - 10, TS - 10, GREEN)
    # runner
    fill_circle(px * TS + 8, FIELD_Y + py * TS + 8, 6, YELLOW)
    fb.fill_rect(px * TS + 5, FIELD_Y + py * TS + 5, 2, 2, BG)
    fb.fill_rect(px * TS + 9, FIELD_Y + py * TS + 5, 2, 2, BG)
    # hud
    fb.text("SCORE {}".format(score), 4, 2, WHITE)
    fb.text("{}/{}".format(need - gems_left, need), 130, 2, CYAN)
    for i in range(lives):
        fill_circle(306 - i * 14, 10, 5, YELLOW)
    fb.show()


games = 0
while True:
    games += 1
    score = 0
    lives = 3
    level = 1
    running = True
    while running:
        gen_cave()
        alive = True
        while alive:
            danger = compute_danger()
            dd = ai_dir(danger)
            if dd is not None:
                try_move(dd)
            if physics():
                lives -= 1
                draw()
                time.sleep_ms(600)
                if lives <= 0:
                    alive = False
                else:
                    gen_cave()  # restart the cave
                continue
            if won:
                score += 500
                print("level {} cleared".format(level))
                level += 1
                gen_cave()
            draw()
            time.sleep_ms(110)
    draw()
    print("game {} over, score {}".format(games, score))
    fb.fill_rect(90, 104, 140, 40, BG)
    fb.rect(90, 104, 140, 40, WHITE)
    fb.text("GAME OVER", 122, 114, RED)
    fb.text("SCORE {}".format(score), 122, 130, WHITE)
    fb.show()
    time.sleep_ms(2500)
