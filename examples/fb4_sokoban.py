# fb4_sokoban.py - AI Sokoban demo for the CYD (ESP32-2432S028R)
#
# A solver (Rust, multi-core, host) precomputed optimal Push-solutions for a
# set of real David W. Skinner Sokoban levels (see ../sokolver/).
# Levels + solutions are kept in the separate sokoban_levels module.
# Controls (USB serial, optional): 'n' next level, 'p' replay, 'q' quit.
#   mpremote connect /dev/ttyUSB0 run fb4_sokoban.py
from fb4 import FB4
from sokoban_levels import LEVELS
try:
    from sokoban_levels import LEVELS_INFO
except ImportError:
    LEVELS_INFO = None
import sys
import time
import math

DM = [(0, -1), (0, 1), (-1, 0), (1, 0)]
MOVNAMES = ["UP", "DOWN", "LEFT", "RIGHT"]

# interpolation frames per tile of movement
FRAMES = 5
FRAME_DELAY = 12  # ms per intraframe (SPI whole-screen push ~18ms dominates)

PAL = {
    'wall': 2,
    'floor': 0,
    'goal': 13,
    'box': 7,
    'boxgoal': 5,
    'player': 1,
}


def fill_circle(fb, cx, cy, r, col):
    """Scanline fill of a circle centred at (cx, cy) radius r (framebuf has no fill_ellipse)."""
    for dy in range(-r, r + 1):
        w = int((r * r - dy * dy) ** 0.5)
        fb.hline(cx - w, cy + dy, 2 * w + 1, col)


class Board:
    def __init__(self, rows, w, h, tile, x0, y0):
        self.grid = []
        for r in rows:
            if len(r) < w:
                r = r + ' ' * (w - len(r))
            self.grid.append(list(r))
        self.w = w
        self.h = h
        self.tile = tile
        self.x0 = x0
        self.y0 = y0
        self.targets = set()
        self.px = self.py = 0
        for y in range(h):
            for x in range(w):
                c = self.grid[y][x]
                if c in '.+*':
                    self.targets.add((x, y))
                if c == '@':
                    self.px, self.py = x, y
                    self.grid[y][x] = ' '
                elif c == '+':
                    self.px, self.py = x, y
                    self.grid[y][x] = '.'
        self.boxes = set()
        for y in range(h):
            for x in range(w):
                c = self.grid[y][x]
                if c in '$*':
                    self.boxes.add((x, y))
                    self.grid[y][x] = '.' if (x, y) in self.targets else ' '

    def box_at(self, x, y):
        return (x, y) in self.boxes

    def find_box(self, x, y):
        return (x, y) in self.boxes

    def draw_scene(self, fb, ppx, ppy, boxes_px, goal_mask, anim=None):
        """Draw the full scene. boxes_px maps tile->(pixelX,pixelY).
        goal_mask is a set of tiles currently occupied by a box that is on a goal.
        anim (optional dict) is passed to draw_player for living animation."""
        t = self.tile
        x0, y0 = self.x0, self.y0
        for y in range(self.h):
            for x in range(self.w):
                px = x0 + x * t
                py = y0 + y * t
                c = self.grid[y][x]
                if c == '#':
                    fb.fill_rect(px, py, t, t, PAL['wall'])
                elif (x, y) in self.targets:
                    fb.fill_rect(px, py, t, t, PAL['goal'])
                    fb.fill_rect(px + t // 3, py + t // 3,
                                 t - 2 * t // 3, t - 2 * t // 3, 9)
                else:
                    fb.fill_rect(px, py, t, t, PAL['floor'])
        for (bx, by), (bpx, bpy) in boxes_px.items():
            on_goal = goal_mask is not None and (bx, by) in goal_mask
            if on_goal:
                fb.fill_rect(bpx, bpy, t, t, PAL['boxgoal'])
            else:
                fb.fill_rect(bpx, bpy, t, t, PAL['box'])
            fb.rect(bpx + 1, bpy + 1, t - 2, t - 2, 15)
            fb.rect(bpx + 1 + t // 5, bpy + 1 + t // 5,
                    t // 3, t // 3, 0)
        # player
        self.draw_player(fb, ppx, ppy, anim)
    def draw_player(self, fb, ppx, ppy, anim=None):
        """Cute animated robot buddy, drawn proportionally to tile size t.

        anim (optional dict) drives living animation:
          k     (float) 0..1 intraframe ease for walk bounce
          push  (bool)   True while pushing a box (lean toward box)
          facex (int)    -1/0/1 horizontal facing (eye/antenna tilt)
          blink (int)    frame counter; eyes drawn as lines when blinking
        Without anim the character renders at rest (initial scene).
        """
        t = self.tile
        if t < 7:
            fb.fill_rect(ppx + 1, ppy + 1, t - 2, t - 2, PAL['player'])
            return

        fx = fy = k = 0.0
        push = False
        facex = 0
        blink = 0
        if anim is not None:
            k = anim['k']
            push = anim.get('push', False)
            facex = anim.get('facex', 0)
            blink = anim.get('blink', 0)

        cx = ppx + t // 2
        base_cy = ppy + t // 2

        # vertical bounce while walking (unless resting at 0)
        moving = k > 0.0 and k < 1.0
        bounce = 0
        if moving:
            amp = 2.0 if push else 1.5
            bounce = -int(amp * math.sin(math.pi * k))
        cy = base_cy + bounce + 1

        # core radius and leg size, all proportional
        r = max(2, t // 2 - 1)
        legw = max(1, t // 6)
        legh = max(1, t // 5)

        # --- legs (alternate strides while walking) ---
        lx0 = cx - (2 * legw)
        rx0 = cx + legw
        if moving:
            lift = int(1 + math.sin(math.pi * k) * 2)
            lx0 += lift // 2
            rx0 -= lift // 2
            fb.fill_rect(lx0, base_cy + r - 1, legw, legh, 0)
            fb.fill_rect(rx0, base_cy + r - 1, legw, legh, 0)
        else:
            fb.fill_rect(lx0, cy + r - 1, legw, legh, 0)
            fb.fill_rect(rx0, cy + r - 1, legw, legh, 0)

        # --- body: filled circle with shading ---
        fill_circle(fb, cx, cy, r, 9)                      # white body
        # slight lean toward travel dir while pushing / walking
        lean = facex
        # outline shade (gray) on the lower-right for depth
        for dy in range(0, r - 1):
            w = int((r * r - dy * dy) ** 0.5)
            fb.hline(cx + w - 1, cy + dy, 1, 15)           # right edge shade
        fb.hline(cx - r, cy + r - 1, 2 * r + 1, 15)        # bottom lip

        # --- belly plate (contrast panel) ---
        br = max(1, r * 2 // 3)
        for dy in range(-br, br + 1):
            wb = int((br * br - dy * dy) ** 0.5)
            fb.hline(cx + lean - wb, cy + dy, 2 * wb + 1, 14)

        # --- eyes (look in facing direction) ---
        eye_y = cy - r // 3
        ex = r // 3
        eye_dx = lean
        if blink % 9 < 3 and moving:
            # closed eyes = short line per blink cycle
            fb.hline(cx - ex + eye_dx - r // 4, eye_y, r // 2, 0)
            fb.hline(cx + ex + eye_dx - r // 4, eye_y, r // 2, 0)
        else:
            er = max(1, r // 4)
            fill_circle(fb, cx - ex + eye_dx, eye_y, er, 0)
            fill_circle(fb, cx + ex + eye_dx, eye_y, er, 0)
            # eye glint
            fb.pixel(cx - ex + eye_dx, eye_y - er // 2, 9)
            fb.pixel(cx + ex + eye_dx, eye_y - er // 2, 9)

        # --- smile ---
        sm = max(1, r // 3)
        fb.hline(cx - sm, cy + r // 3, 2 * sm + 1, 0)

        # --- antenna (AI robot cue) ---
        ax = cx + lean
        fb.line(ax, cy - r, ax, cy - r - r // 2, 9)
        fb.pixel(ax, cy - r - r // 2 - 1, 9)
        # antenna tip glow
        fill_circle(fb, ax, cy - r - r // 2 - 1, max(1, r // 5), 8 if blink % 20 < 10 else 0)

    def move(self, dx, dy):
        nx, ny = self.px + dx, self.py + dy
        if self.grid[ny][nx] == '#':
            return False
        if (nx, ny) in self.boxes:
            nx2, ny2 = nx + dx, ny + dy
            if self.grid[ny2][nx2] == '#' or (nx2, ny2) in self.boxes:
                return False
            self.boxes.remove((nx, ny))
            self.boxes.add((nx2, ny2))
        self.px, self.py = nx, ny
        return True

    def solved(self):
        return all(b in self.targets for b in self.boxes)


def banner(fb, text, y=110):
    fb.rect(10, y - 14, 300, 30, 9)
    fb.fill_rect(11, y - 13, 298, 28, 0)
    fb.text(text, 20, y - 7, 9)
    fb.show()


def play_level(fb, level_idx, total):
    rows = LEVELS[level_idx][:-1]
    moves = LEVELS[level_idx][-1]
    h = len(rows)
    w = max(len(r) for r in rows)
    margin = 8
    avail_w = 320 - 2 * margin
    avail_h = 240 - 2 * margin - 40
    tile = min(avail_w // w, avail_h // h)
    if tile < 8:
        tile = 8
    x0 = (320 - w * tile) // 2
    y0 = margin + 20
    b = Board(rows, w, h, tile, x0, y0)
    t = b.tile

    def tile_px(x, y):
        return (b.x0 + x * t, b.y0 + y * t)

    move_count = len(moves)
    pushes_done = 0
    push_total = None
    if LEVELS_INFO is not None and level_idx < len(LEVELS_INFO):
        push_total = LEVELS_INFO[level_idx]["pushes"]
    title = "AI SOLVING"

    # fresh frame each level so nothing from the previous board lingers
    fb.fill(0)

    # initial scene
    b.draw_scene(fb, b.x0 + b.px * t, b.y0 + b.py * t,
                 {bxby: tile_px(bxby[0], bxby[1]) for bxby in b.boxes},
                 set(b.boxes), None)
    fb.fill_rect(0, 0, 320, 20, 0)   # clear title bar
    fb.text(title, 12, 4, 15)
    fb.show()
    time.sleep_ms(FRAME_DELAY)

    for i, m in enumerate(moves):
        dx, dy = DM[m]
        nx, ny = b.px + dx, b.py + dy
        was_push = b.box_at(nx, ny)
        blink_counter = 0

        start = (b.x0 + b.px * t, b.y0 + b.py * t)
        pstop = (b.x0 + nx * t, b.y0 + ny * t)

        bstart = None
        bstop = None
        if was_push:
            bx, by = nx, ny
            bstart = tile_px(bx, by)
            bstop = tile_px(bx + dx, by + dy)

        if was_push:
            pushes_done += 1
        if push_total is not None:
            if was_push:
                msg = "PUSH %d/%d %s" % (pushes_done, push_total, MOVNAMES[m])
            else:
                msg = "WALK %s  push %d/%d" % (MOVNAMES[m], pushes_done, push_total)
        else:
            msg = ("PUSH " + MOVNAMES[m]) if was_push else MOVNAMES[m]
        frame_title = "MOVE %d/%d  %s" % (i + 1, move_count, msg)

        # smooth glide (f goes 0..=FRAMES so sprites settle exactly on target)
        facex = dx
        for f in range(FRAMES + 1):
            k = f / FRAMES
            ppx = start[0] + (pstop[0] - start[0]) * k
            ppy = start[1] + (pstop[1] - start[1]) * k
            boxes_px = {}
            goal_mask = set()
            for (bx2, by2) in b.boxes:
                if was_push and (bx2, by2) == (bx, by):
                    bk = f / FRAMES
                    cpx = bstart[0] + (bstop[0] - bstart[0]) * bk
                    cpy = bstart[1] + (bstop[1] - bstart[1]) * bk
                    boxes_px[(bx2 + dx, by2 + dy)] = (int(cpx), int(cpy))
                    if (bx2 + dx, by2 + dy) in b.targets:
                        goal_mask.add((bx2 + dx, by2 + dy))
                else:
                    boxes_px[(bx2, by2)] = tile_px(bx2, by2)
                    if (bx2, by2) in b.targets:
                        goal_mask.add((bx2, by2))
            anim = {'k': k, 'push': was_push, 'facex': facex, 'blink': blink_counter}
            b.draw_scene(fb, int(ppx), int(ppy), boxes_px, goal_mask, anim)
            blink_counter += 1
            fb.fill_rect(0, 0, 320, 20, 0)   # clear title bar before writing
            fb.text(frame_title, 12, 4, 15)
            fb.show()
            time.sleep_ms(FRAME_DELAY)

        b.move(dx, dy)

    if b.solved():
        if LEVELS_INFO is not None and level_idx < len(LEVELS_INFO):
            info = LEVELS_INFO[level_idx]
            if info.get("objective") == "push":
                head = "DONE in %d pushes!" % info["pushes"]
            else:
                head = "SOLVED in %d moves!" % move_count
            banner(fb, head)
        else:
            banner(fb, "SOLVED in %d moves!" % move_count)
        print("level %d/%d solved (%d moves, %d pushes)" %
              (level_idx + 1, total, move_count, pushes_done))
        return True
    else:
        banner(fb, "NOT SOLVED?")
        print("level %d/%d NOT solved" % (level_idx + 1, total))
        return False


def run():
    fb = FB4()
    total = len(LEVELS)
    i = 0
    while True:
        play_level(fb, i, total)
        import select
        p = select.poll()
        p.register(sys.stdin, select.POLLIN)
        t0 = time.ticks_ms()
        advanced = False
        while time.ticks_ms() - t0 < 6000 and not advanced:
            res = p.poll(200)
            if res:
                ch = sys.stdin.buffer.read(1)
                if ch:
                    c = chr(ch[0])
                    if c == 'n':
                        i = (i + 1) % total
                        advanced = True
                    elif c == 'p':
                        advanced = True
                    elif c == 'q':
                        fb.fill(0)
                        fb.text("QUIT", 140, 110, 9)
                        fb.show()
                        return
        if not advanced:
            i = (i + 1) % total


if __name__ == '__main__':
    run()
