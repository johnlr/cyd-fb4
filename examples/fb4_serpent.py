# fb4_serpent.py - self-playing serpent demo using the fb4 4-bit framebuffer module
# Touch is not wired up yet, so the snake drives itself with a simple
# greedy pathfinder (move toward food, avoid walls and its own body).
import time
import random
import fb4

CELL = 8
FIELD_Y = 16          # top of playfield, clears the score bar
GW = 320 // CELL      # 40 cells wide
GH = 27               # 27 rows -> frame is 216 px tall, ends at y=231,
                      # leaving a visible margin above the panel bottom

# palette indices
BG = 0
SNAKE = 2      # green
HEAD = 9       # white
FOOD = 1       # red
WALL = 15      # gray

fb = fb4.FB4()


def draw(score):
    fb.fill(BG)
    fb.rect(0, FIELD_Y, 320, 240 - FIELD_Y, WALL)
    for i, (x, y) in enumerate(snake):
        c = HEAD if i == 0 else SNAKE
        fb.fill_rect(x * CELL + 1, FIELD_Y + y * CELL + 1, CELL - 2, CELL - 2, c)
    fx, fy = food
    fb.fill_rect(fx * CELL + 1, FIELD_Y + fy * CELL + 1, CELL - 2, CELL - 2, FOOD)
    fb.text("SCORE {}".format(score), 8, 2, HEAD)
    fb.show()


def occupied(x, y):
    return (x, y) in snake


def new_food():
    while True:
        p = (random.getrandbits(5) % GW, random.getrandbits(5) % GH)
        if not occupied(p[0], p[1]):
            return p


def step(dx, dy):
    """Advance one cell; returns False if dead."""
    hx, hy = snake[0]
    nx, ny = hx + dx, hy + dy
    if nx < 0 or nx >= GW or ny < 0 or ny >= GH:
        return False
    # tail cell frees up unless we just ate
    body = snake[:-1] if (nx, ny) != food else snake
    if (nx, ny) in body:
        return False
    snake.insert(0, (nx, ny))
    if (nx, ny) == food:
        return True  # grew
    snake.pop()
    return True


def choose_dir():
    """Greedy: prefer closing the bigger gap to food, avoid danger."""
    hx, hy = snake[0]
    fx, fy = food
    dxs = []
    if fx > hx:
        dxs.append((1, 0))
    elif fx < hx:
        dxs.append((-1, 0))
    if fy > hy:
        dxs.append((0, 1))
    elif fy < hy:
        dxs.append((0, -1))
    # fallback order: any direction not reversing
    lx, ly = last_dir
    others = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    others.remove((lx, ly))
    for cand in dxs + others:
        cx, cy = hx + cand[0], hy + cand[1]
        if 0 <= cx < GW and 0 <= cy < GH and (cx, cy) not in snake[:-1]:
            return cand
    return (lx, ly)  # trapped, keep going


def reset():
    global snake, food, last_dir
    snake = [(GW // 2, GH // 2)]
    last_dir = (1, 0)
    food = new_food()


reset()
games = 0
while True:
    games += 1
    score = 0
    alive = True
    while alive:
        last_dir = choose_dir()
        ate = step(*last_dir)
        if not ate:
            alive = False
            break
        if (snake[0][0], snake[0][1]) == food:
            score += 1
            food = new_food()
        draw(score)
        time.sleep_ms(60)
    draw(score)
    print("game {} over, score {}".format(games, score))
    fb.fill_rect(120, 106, 80, 34, BG)
    fb.rect(120, 106, 80, 34, WALL)
    t1 = "GAME OVER"
    fb.text(t1, 160 - 4 * len(t1), 113, FOOD)
    t2 = "SCORE {}".format(score)
    fb.text(t2, 160 - 4 * len(t2), 127, HEAD)
    fb.show()
    time.sleep_ms(2500)
    reset()
