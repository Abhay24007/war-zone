"""
WAR ZONE - 2D battle arena (pygame, browser-ready via pygbag)

Run in a browser (localhost):   pygbag .      -> http://localhost:8000
Run as a desktop window:        python main.py
"""
import asyncio
import math
import random
import sys

import pygame
from pygame import Vector2 as V2

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
W, H = 1280, 720
FPS = 60
WORLD_W, WORLD_H = 2400, 1600
MATCH_TIME = 180          # seconds
KILL_LIMIT = 20
PLAYER_SPEED = 260
RESPAWN_TIME = 3.0

BG = (11, 14, 22)
PANEL = (20, 26, 40)
PANEL_EDGE = (46, 56, 80)
ACCENT = (255, 176, 0)
ACCENT_DIM = (150, 104, 0)
RED = (255, 82, 82)
GREEN = (80, 220, 120)
BLUE = (80, 170, 255)
TEXT = (236, 241, 250)
DIM = (128, 140, 162)

WEAPONS = {
    "RIFLE": dict(dmg=12, delay=0.09, mag=30, reload=1.5, spread=0.05, speed=950,
                  pellets=1, life=0.85, auto=True, ideal=380, bars=(0.35, 0.95, 0.6),
                  blurb="Fast & accurate"),
    "SHOTGUN": dict(dmg=9, delay=0.75, mag=6, reload=2.0, spread=0.20, speed=850,
                    pellets=8, life=0.42, auto=False, ideal=200, bars=(0.95, 0.35, 0.25),
                    blurb="Brutal up close"),
    "SNIPER": dict(dmg=75, delay=1.10, mag=5, reload=2.2, spread=0.0, speed=2100,
                   pellets=1, life=1.20, auto=False, ideal=640, bars=(1.0, 0.15, 1.0),
                   blurb="One-two shots"),
}
WEAPON_KEYS = list(WEAPONS.keys())

OBST = [pygame.Rect(*r) for r in [
    (300, 300, 60, 260), (2040, 300, 60, 260), (300, 1040, 60, 260), (2040, 1040, 60, 260),
    (700, 200, 300, 60), (1400, 200, 300, 60), (700, 1340, 300, 60), (1400, 1340, 300, 60),
    (1000, 600, 400, 60), (1000, 940, 400, 60), (580, 700, 60, 200), (1760, 700, 60, 200),
    (1140, 760, 120, 80),
]]
SPAWNS = [(150, 150), (2250, 150), (150, 1450), (2250, 1450),
          (1200, 120), (1200, 1480), (120, 800), (2280, 800)]
PACKS = [(480, 800), (1920, 800), (1200, 450), (1200, 1150)]

BOT_NAMES = ["VIPER", "GHOST", "RAZOR", "NOVA", "TITAN", "SHADE", "HAVOC"]
BOT_COLORS = [(255, 95, 95), (190, 120, 255), (255, 140, 60), (80, 220, 200),
              (240, 90, 180), (150, 210, 70), (230, 220, 90)]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
_fonts = {}


def font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def text(surf, s, size, color, pos, anchor="topleft", shadow=True):
    img = font(size).render(str(s), True, color)
    r = img.get_rect(**{anchor: pos})
    if shadow:
        surf.blit(font(size).render(str(s), True, (0, 0, 0)), r.move(2, 2))
    surf.blit(img, r)
    return r


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def angle_diff(a, b):
    return (b - a + math.pi) % (2 * math.pi) - math.pi


def seg_dist(a, b, p):
    ab = b - a
    l2 = ab.length_squared()
    if l2 == 0:
        return a.distance_to(p)
    t = clamp((p - a).dot(ab) / l2, 0.0, 1.0)
    return (a + ab * t).distance_to(p)


def line_blocked(a, b):
    p1 = (int(a.x), int(a.y))
    p2 = (int(b.x), int(b.y))
    for o in OBST:
        if o.clipline(p1, p2):
            return True
    return False


def move_collide(pos, delta, r):
    """Move a square-ish body of radius r, sliding along obstacles. Returns True if blocked."""
    blocked = False
    rect = pygame.Rect(0, 0, int(2 * r), int(2 * r))
    pos.x += delta.x
    rect.center = (int(pos.x), int(pos.y))
    for o in OBST:
        if rect.colliderect(o):
            if delta.x > 0:
                pos.x = o.left - r
            elif delta.x < 0:
                pos.x = o.right + r
            rect.centerx = int(pos.x)
            blocked = True
    pos.y += delta.y
    rect.center = (int(pos.x), int(pos.y))
    for o in OBST:
        if rect.colliderect(o):
            if delta.y > 0:
                pos.y = o.top - r
            elif delta.y < 0:
                pos.y = o.bottom + r
            rect.centery = int(pos.y)
            blocked = True
    pos.x = clamp(pos.x, r, WORLD_W - r)
    pos.y = clamp(pos.y, r, WORLD_H - r)
    return blocked


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------
class Bullet:
    __slots__ = ("pos", "vel", "dmg", "owner", "life")

    def __init__(self, pos, vel, dmg, owner, life):
        self.pos, self.vel, self.dmg, self.owner, self.life = pos, vel, dmg, owner, life


class Fighter:
    R = 18

    def __init__(self, name, color, is_player=False):
        self.name = name
        self.color = color
        self.is_player = is_player
        self.kills = 0
        self.deaths = 0
        self.weapon = "RIFLE"
        self.pos = V2()
        self.aim = 0.0
        self.alive = False
        self.respawn_t = 0.0
        self.killer = None
        # bot brain
        self.target = None
        self.think_t = 0.0
        self.strafe = random.choice((-1, 1))
        self.flip_cd = 0.0
        self.nolos_t = 0.0
        self.skill = random.uniform(0.6, 1.0)
        self.aim_err = 0.0
        self.spawn((0, 0))
        self.alive = False

    def spawn(self, pos):
        self.pos = V2(pos)
        self.hp = 100
        self.alive = True
        self.ammo = {k: w["mag"] for k, w in WEAPONS.items()}
        self.cd = 0.0
        self.reload_t = 0.0
        self.inv = 1.5
        self.dash_t = 0.0
        self.dash_cd = 0.0
        self.dash_dir = V2()
        self.flash = 0.0
        self.hurt = 0.0
        self.target = None
        self.nolos_t = 0.0


# --------------------------------------------------------------------------
# Game
# --------------------------------------------------------------------------
class Game:
    def __init__(self, screen):
        self.screen = screen
        self.state = "menu"        # menu | play | end
        self.t = 0.0
        self.name = "PLAYER"
        self.sel_weapon = "RIFLE"
        self.bot_count = 5
        self.mouse_click = False
        self.cursor_hidden = None
        self.red = pygame.Surface((W, H))
        self.red.fill((210, 0, 0))
        self.dark = pygame.Surface((W, H))
        self.dark.fill((0, 0, 0))
        self.fighters = []
        self.bullets = []
        self.particles = []
        self.packs = []
        self.feed = []
        self.player = None
        self.paused = False
        self.cam = V2()
        self.shake = 0.0
        self.hitmarker = 0.0
        self.dmg_flash = 0.0
        self.time_left = MATCH_TIME
        self.play_t = 0.0
        self.winner = None

    # ---- match flow ------------------------------------------------------
    def start_match(self):
        self.fighters = []
        self.player = Fighter(self.name.strip() or "PLAYER", BLUE, True)
        self.player.weapon = self.sel_weapon
        self.fighters.append(self.player)
        for i in range(self.bot_count):
            b = Fighter(BOT_NAMES[i], BOT_COLORS[i])
            b.weapon = random.choice(WEAPON_KEYS)
            self.fighters.append(b)
        spawns = random.sample(SPAWNS, len(self.fighters))
        for f, sp in zip(self.fighters, spawns):
            f.spawn(sp)
        self.bullets, self.particles, self.feed = [], [], []
        self.packs = [{"pos": V2(p), "t": 0.0} for p in PACKS]
        self.time_left = MATCH_TIME
        self.paused = False
        self.shake = self.hitmarker = self.dmg_flash = 0.0
        self.play_t = 0.0
        self.cam = self.player.pos - V2(W / 2, H / 2)
        self.state = "play"

    def end_match(self):
        self.state = "end"
        board = sorted(self.fighters, key=lambda f: (-f.kills, f.deaths))
        self.winner = board[0]

    def pick_spawn(self, f):
        best, best_d = SPAWNS[0], -1
        for sp in random.sample(SPAWNS, len(SPAWNS)):
            d = min([V2(sp).distance_to(o.pos) for o in self.fighters
                     if o is not f and o.alive] or [9999])
            if d > best_d:
                best, best_d = sp, d
        return best

    # ---- input -----------------------------------------------------------
    def menu_rects(self):
        r = {"input": pygame.Rect(350, 272, 580, 44), "play": pygame.Rect(350, 566, 580, 64)}
        for i, k in enumerate(WEAPON_KEYS):
            r["w_" + k] = pygame.Rect(350 + i * 198, 358, 184, 110)
        for i, n in enumerate((3, 5, 7)):
            r["b_%d" % n] = pygame.Rect(350 + i * 92, 506, 80, 38)
        return r

    def end_rects(self):
        return {"again": pygame.Rect(W // 2 - 230, 620, 220, 56),
                "menu": pygame.Rect(W // 2 + 10, 620, 220, 56)}

    def handle_event(self, e):
        if self.state == "menu":
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for k, rc in self.menu_rects().items():
                    if rc.collidepoint(e.pos):
                        if k == "play":
                            self.start_match()
                        elif k.startswith("w_"):
                            self.sel_weapon = k[2:]
                        elif k.startswith("b_"):
                            self.bot_count = int(k[2:])
            elif e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.start_match()
                elif e.key == pygame.K_BACKSPACE:
                    self.name = self.name[:-1]
                elif e.unicode and e.unicode.isprintable() and len(self.name) < 12:
                    self.name += e.unicode.upper()
        elif self.state == "play":
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self.mouse_click = True
            elif e.type == pygame.MOUSEWHEEL and not self.paused:
                i = WEAPON_KEYS.index(self.player.weapon)
                self.switch_weapon(self.player, WEAPON_KEYS[(i - e.y) % len(WEAPON_KEYS)])
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.paused = not self.paused
                elif self.paused and e.key == pygame.K_m:
                    self.state = "menu"
                elif not self.paused:
                    if e.key == pygame.K_r:
                        self.start_reload(self.player)
                    elif e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        self.switch_weapon(self.player, WEAPON_KEYS[e.key - pygame.K_1])
        elif self.state == "end":
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for k, rc in self.end_rects().items():
                    if rc.collidepoint(e.pos):
                        if k == "again":
                            self.start_match()
                        else:
                            self.state = "menu"
            elif e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.start_match()

    # ---- combat ----------------------------------------------------------
    def switch_weapon(self, f, key):
        if f.weapon != key and f.alive:
            f.weapon = key
            f.reload_t = 0.0
            f.cd = 0.25

    def start_reload(self, f):
        w = WEAPONS[f.weapon]
        if f.alive and f.reload_t <= 0 and f.ammo[f.weapon] < w["mag"]:
            f.reload_t = w["reload"]

    def fire(self, f):
        w = WEAPONS[f.weapon]
        if not f.alive or f.cd > 0 or f.reload_t > 0:
            return
        if f.ammo[f.weapon] <= 0:
            self.start_reload(f)
            return
        f.ammo[f.weapon] -= 1
        f.cd = w["delay"]
        f.flash = 0.06
        f.inv = 0.0
        d = V2(math.cos(f.aim), math.sin(f.aim))
        for _ in range(w["pellets"]):
            a = f.aim + random.uniform(-w["spread"], w["spread"])
            vel = V2(math.cos(a), math.sin(a)) * w["speed"]
            self.bullets.append(Bullet(f.pos + d * (f.R + 8), vel, w["dmg"], f, w["life"]))
        if f.is_player:
            self.shake = min(0.6, self.shake + (0.35 if f.weapon != "RIFLE" else 0.08))

    def burst(self, pos, color, n):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(60, 240)
            self.particles.append([V2(pos), V2(math.cos(a), math.sin(a)) * sp,
                                   random.uniform(0.2, 0.45), color])

    def damage(self, f, dmg, owner):
        f.hp -= dmg
        f.hurt = 0.12
        self.burst(f.pos, (255, 70, 70), 6)
        if f.is_player:
            self.dmg_flash = 0.4
            self.shake = min(0.7, self.shake + 0.3)
        if owner is not None and owner.is_player:
            self.hitmarker = 0.18
        if f.hp <= 0 and f.alive:
            f.alive = False
            f.respawn_t = RESPAWN_TIME
            f.deaths += 1
            f.killer = owner
            self.burst(f.pos, f.color, 22)
            if owner is not None and owner is not f:
                owner.kills += 1
                self.feed.append([owner.name, owner.weapon, f.name, 6.0,
                                  owner.is_player, f.is_player])

    # ---- movement / ai ----------------------------------------------------
    def apply_move(self, f, mv, dt, dash_key=False):
        if dash_key and f.dash_cd <= 0 and mv.length_squared() > 0:
            f.dash_t, f.dash_cd, f.dash_dir = 0.14, 2.0, V2(mv)
        if f.dash_t > 0:
            f.dash_t -= dt
            vel = f.dash_dir * PLAYER_SPEED * 3.4
        else:
            vel = mv * PLAYER_SPEED * (1.0 if f.is_player else 0.82)
        return move_collide(f.pos, vel * dt, f.R)

    def update_player(self, f, dt):
        keys = pygame.key.get_pressed()
        mv = V2(int(keys[pygame.K_d]) - int(keys[pygame.K_a]) +
                int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT]),
                int(keys[pygame.K_s]) - int(keys[pygame.K_w]) +
                int(keys[pygame.K_DOWN]) - int(keys[pygame.K_UP]))
        if mv.length_squared() > 0:
            mv = mv.normalize()
        d = V2(pygame.mouse.get_pos()) + self.cam - f.pos
        if d.length_squared() > 4:
            f.aim = math.atan2(d.y, d.x)
        self.apply_move(f, mv, dt, keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
        w = WEAPONS[f.weapon]
        held = pygame.mouse.get_pressed()[0]
        if self.play_t > 0.3 and ((w["auto"] and held) or (not w["auto"] and self.mouse_click)):
            self.fire(f)
        self.mouse_click = False

    def update_bot(self, f, dt):
        f.think_t -= dt
        f.flip_cd -= dt
        if f.think_t <= 0:
            f.think_t = random.uniform(0.3, 0.7)
            best, bd = None, 1e9
            for o in self.fighters:
                if o is f or not o.alive:
                    continue
                dist = f.pos.distance_to(o.pos)
                if dist < bd:
                    best, bd = o, dist
            f.target = best
            f.aim_err = random.uniform(-0.10, 0.10) * (1.2 - f.skill)
            if random.random() < 0.35 and f.flip_cd <= 0:
                f.strafe *= -1
                f.flip_cd = 0.5
        t = f.target
        if t is None or not t.alive:
            f.target = None
            to_c = V2(WORLD_W / 2, WORLD_H / 2) - f.pos
            if to_c.length_squared() > 10000:
                self.apply_move(f, to_c.normalize() * 0.6, dt)
            return
        to = t.pos - f.pos
        dist = to.length() or 1.0
        dirv = to / dist
        perp = V2(-dirv.y, dirv.x) * f.strafe
        w = WEAPONS[f.weapon]
        los = not line_blocked(f.pos, t.pos)
        f.nolos_t = 0.0 if los else f.nolos_t + dt
        mv = V2()
        if f.hp < 40:
            best, bd = None, 1e9
            for p in self.packs:
                if p["t"] <= 0:
                    dd = f.pos.distance_to(p["pos"])
                    if dd < bd:
                        best, bd = p, dd
            if best is not None:
                mv = (best["pos"] - f.pos).normalize() * 1.1 + perp * 0.3
        if mv.length_squared() == 0:
            if not los:
                mv = dirv * 0.6 + perp * 1.0
            elif dist > w["ideal"] + 70:
                mv = dirv + perp * 0.5
            elif dist < w["ideal"] - 70:
                mv = -dirv + perp * 0.8
            else:
                mv = perp * 0.9
        if mv.length_squared() > 1:
            mv = mv.normalize()
        if self.apply_move(f, mv, dt) and f.flip_cd <= 0:
            f.strafe *= -1
            f.flip_cd = 0.5
        true_ang = math.atan2(to.y, to.x)
        diff = angle_diff(f.aim, true_ang + f.aim_err)
        step = (4.0 + 6.0 * f.skill) * dt
        f.aim += clamp(diff, -step, step)
        reach = w["speed"] * w["life"] * 0.9
        tol = clamp(math.atan2(26, dist), 0.03, 0.25)
        if los and dist < reach and abs(angle_diff(f.aim, true_ang)) < tol:
            self.fire(f)
        if f.ammo[f.weapon] <= 0:
            self.start_reload(f)

    # ---- update ----------------------------------------------------------
    def update(self, dt):
        self.t += dt
        want_hidden = self.state == "play" and not self.paused
        if want_hidden != self.cursor_hidden:
            pygame.mouse.set_visible(not want_hidden)
            self.cursor_hidden = want_hidden
        if self.state != "play" or self.paused:
            return
        self.play_t += dt
        self.time_left -= dt
        if self.time_left <= 0 or any(f.kills >= KILL_LIMIT for f in self.fighters):
            self.end_match()
            return

        for f in self.fighters:
            if f.alive:
                f.cd = max(0.0, f.cd - dt)
                f.inv = max(0.0, f.inv - dt)
                f.flash = max(0.0, f.flash - dt)
                f.hurt = max(0.0, f.hurt - dt)
                f.dash_cd = max(0.0, f.dash_cd - dt)
                if f.reload_t > 0:
                    f.reload_t -= dt
                    if f.reload_t <= 0:
                        f.reload_t = 0.0
                        f.ammo[f.weapon] = WEAPONS[f.weapon]["mag"]
                if f.is_player:
                    self.update_player(f, dt)
                else:
                    self.update_bot(f, dt)
            else:
                f.respawn_t -= dt
                if f.respawn_t <= 0:
                    f.spawn(self.pick_spawn(f))
                    if not f.is_player:
                        f.weapon = random.choice(WEAPON_KEYS)

        # separate overlapping fighters
        alive = [f for f in self.fighters if f.alive]
        for i, a in enumerate(alive):
            for b in alive[i + 1:]:
                d = b.pos - a.pos
                dist = d.length()
                if 0 < dist < 2 * Fighter.R:
                    push = d / dist * ((2 * Fighter.R - dist) / 2)
                    move_collide(a.pos, -push, Fighter.R)
                    move_collide(b.pos, push, Fighter.R)

        # bullets
        keep = []
        for b in self.bullets:
            prev = V2(b.pos)
            b.pos += b.vel * dt
            b.life -= dt
            dead = b.life <= 0 or not (0 <= b.pos.x <= WORLD_W and 0 <= b.pos.y <= WORLD_H)
            if not dead:
                if line_blocked(prev, b.pos):
                    self.burst(b.pos, (255, 210, 120), 3)
                    dead = True
            if not dead:
                for f in self.fighters:
                    if f is b.owner or not f.alive or f.inv > 0:
                        continue
                    if seg_dist(prev, b.pos, f.pos) < f.R + 2:
                        self.damage(f, b.dmg, b.owner)
                        dead = True
                        break
            if not dead:
                keep.append(b)
        self.bullets = keep

        # health packs
        for p in self.packs:
            if p["t"] > 0:
                p["t"] -= dt
                continue
            for f in alive:
                if f.alive and f.hp < 100 and f.pos.distance_to(p["pos"]) < 30:
                    f.hp = min(100, f.hp + 40)
                    p["t"] = 15.0
                    break

        # particles / feed / fx timers
        for p in self.particles:
            p[0] += p[1] * dt
            p[1] *= 0.92
            p[2] -= dt
        self.particles = [p for p in self.particles if p[2] > 0]
        for e in self.feed:
            e[3] -= dt
        self.feed = [e for e in self.feed if e[3] > 0][-5:]
        self.hitmarker = max(0.0, self.hitmarker - dt)
        self.dmg_flash = max(0.0, self.dmg_flash - dt)
        self.shake = max(0.0, self.shake - dt * 2.5)

        # camera
        focus = self.player.pos
        target = focus - V2(W / 2, H / 2)
        self.cam += (target - self.cam) * min(1.0, 10 * dt)
        self.cam.x = clamp(self.cam.x, 0, WORLD_W - W)
        self.cam.y = clamp(self.cam.y, 0, WORLD_H - H)

    # ---- drawing: shared -------------------------------------------------
    def draw_bg_grid(self, speed=18):
        s = self.screen
        s.fill(BG)
        off = (self.t * speed) % 60
        for x in range(-60, W + 60, 60):
            pygame.draw.line(s, (17, 22, 34), (x + off, 0), (x + off, H))
        for y in range(-60, H + 60, 60):
            pygame.draw.line(s, (17, 22, 34), (0, y + off), (W, y + off))
        for i in range(7):
            cx = (W * (0.1 + 0.14 * i) + math.sin(self.t * 0.4 + i) * 40)
            cy = (H * (0.2 + 0.1 * ((i * 3) % 7)) + math.cos(self.t * 0.3 + i) * 30)
            pygame.draw.circle(s, (22, 29, 46), (int(cx), int(cy)), 60 + 12 * i, 2)

    def button(self, rc, label, primary=False, size=40):
        hover = rc.collidepoint(pygame.mouse.get_pos())
        if primary:
            col = (255, 200, 60) if hover else ACCENT
            pygame.draw.rect(self.screen, col, rc, border_radius=8)
            text(self.screen, label, size, (20, 14, 0), rc.center, "center", shadow=False)
        else:
            pygame.draw.rect(self.screen, (34, 43, 64) if hover else PANEL, rc, border_radius=8)
            pygame.draw.rect(self.screen, ACCENT if hover else PANEL_EDGE, rc, 2, border_radius=8)
            text(self.screen, label, size, TEXT, rc.center, "center")

    # ---- drawing: menu ---------------------------------------------------
    def draw_menu(self):
        s = self.screen
        self.draw_bg_grid()
        rects = self.menu_rects()
        text(s, "WAR ZONE", 170, ACCENT, (W // 2, 92), "center")
        text(s, "2D  BATTLE  ARENA", 34, DIM, (W // 2, 176), "center")

        panel = pygame.Rect(330, 214, 620, 440)
        pygame.draw.rect(s, PANEL, panel, border_radius=12)
        pygame.draw.rect(s, PANEL_EDGE, panel, 2, border_radius=12)

        text(s, "NICKNAME", 24, DIM, (350, 248))
        ib = rects["input"]
        pygame.draw.rect(s, (12, 16, 26), ib, border_radius=6)
        pygame.draw.rect(s, ACCENT, ib, 2, border_radius=6)
        cursor = "|" if int(self.t * 2) % 2 == 0 else ""
        text(s, self.name + cursor, 36, TEXT, (ib.x + 14, ib.centery), "midleft", shadow=False)

        text(s, "LOADOUT", 24, DIM, (350, 334))
        for k in WEAPON_KEYS:
            rc, w = rects["w_" + k], WEAPONS[k]
            sel = self.sel_weapon == k
            hover = rc.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(s, (30, 38, 58) if (sel or hover) else (14, 19, 31), rc, border_radius=8)
            pygame.draw.rect(s, ACCENT if sel else PANEL_EDGE, rc, 3 if sel else 1, border_radius=8)
            text(s, k, 30, ACCENT if sel else TEXT, (rc.x + 12, rc.y + 10))
            text(s, w["blurb"], 20, DIM, (rc.x + 12, rc.y + 34), shadow=False)
            for i, (lab, v) in enumerate(zip(("DMG", "RATE", "RANGE"), w["bars"])):
                y = rc.y + 58 + i * 15
                text(s, lab, 16, DIM, (rc.x + 12, y), shadow=False)
                pygame.draw.rect(s, (40, 48, 68), (rc.x + 62, y + 2, 108, 8), border_radius=4)
                pygame.draw.rect(s, ACCENT, (rc.x + 62, y + 2, int(108 * v), 8), border_radius=4)

        text(s, "BOTS", 24, DIM, (350, 480))
        for n in (3, 5, 7):
            rc = rects["b_%d" % n]
            sel = self.bot_count == n
            pygame.draw.rect(s, (30, 38, 58) if sel else (14, 19, 31), rc, border_radius=6)
            pygame.draw.rect(s, ACCENT if sel else PANEL_EDGE, rc, 2, border_radius=6)
            text(s, n, 30, ACCENT if sel else TEXT, rc.center, "center")

        self.button(rects["play"], "PLAY", True, 52)
        text(s, "WASD move   MOUSE aim   CLICK shoot   R reload   1-2-3 / WHEEL weapons   "
                "SHIFT dash   TAB scoreboard   ESC pause",
             22, DIM, (W // 2, 690), "center", shadow=False)
        # menu cursor
        mx, my = pygame.mouse.get_pos()
        self.draw_crosshair(mx, my, 0)

    # ---- drawing: play ---------------------------------------------------
    def draw_crosshair(self, x, y, spread):
        s = self.screen
        gap = 7 + spread
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a = (x + dx * gap, y + dy * gap)
            b = (x + dx * (gap + 9), y + dy * (gap + 9))
            pygame.draw.line(s, (0, 0, 0), (a[0] + 1, a[1] + 1), (b[0] + 1, b[1] + 1), 4)
            pygame.draw.line(s, ACCENT, a, b, 2)
        pygame.draw.circle(s, ACCENT, (x, y), 2)

    def draw_world(self, off):
        s = self.screen
        cam = self.cam + off
        pygame.draw.rect(s, (18, 23, 36), (-cam.x, -cam.y, WORLD_W, WORLD_H))
        for x in range(0, WORLD_W + 1, 80):
            sx = x - cam.x
            if -2 <= sx <= W + 2:
                pygame.draw.line(s, (27, 34, 52), (sx, max(0, -cam.y)), (sx, min(H, WORLD_H - cam.y)))
        for y in range(0, WORLD_H + 1, 80):
            sy = y - cam.y
            if -2 <= sy <= H + 2:
                pygame.draw.line(s, (27, 34, 52), (max(0, -cam.x), sy), (min(W, WORLD_W - cam.x), sy))
        pygame.draw.rect(s, ACCENT_DIM, (-cam.x, -cam.y, WORLD_W, WORLD_H), 6)

        for o in OBST:
            r = o.move(-int(cam.x), -int(cam.y))
            if r.colliderect(s.get_rect()):
                pygame.draw.rect(s, (38, 47, 68), r, border_radius=4)
                pygame.draw.rect(s, (96, 112, 150), r, 3, border_radius=4)

        for p in self.packs:
            if p["t"] <= 0:
                c = p["pos"] - cam
                pulse = 2 * math.sin(self.t * 4)
                pygame.draw.circle(s, (20, 70, 40), c, 22 + pulse)
                pygame.draw.circle(s, GREEN, c, 22 + pulse, 2)
                pygame.draw.rect(s, GREEN, (c.x - 3, c.y - 11, 6, 22))
                pygame.draw.rect(s, GREEN, (c.x - 11, c.y - 3, 22, 6))

        for b in self.bullets:
            tail = b.pos - b.vel.normalize() * (24 if b.dmg > 50 else 14)
            col = (255, 230, 140) if b.owner.is_player else (255, 120, 90)
            pygame.draw.line(s, col, tail - cam, b.pos - cam, 3)

        for f in self.fighters:
            if not f.alive:
                continue
            if f.inv > 0 and int(self.t * 14) % 2 == 0 and not f.flash:
                continue
            c = f.pos - cam
            d = V2(math.cos(f.aim), math.sin(f.aim))
            pygame.draw.circle(s, (0, 0, 0), c + V2(3, 4), f.R)
            pygame.draw.line(s, (30, 34, 44), c, c + d * (f.R + 14), 8)
            body = (255, 255, 255) if f.hurt > 0 else f.color
            pygame.draw.circle(s, body, c, f.R)
            pygame.draw.circle(s, (255, 255, 255) if f.is_player else (20, 24, 34), c, f.R, 3)
            if f.flash > 0:
                pygame.draw.circle(s, (255, 230, 120), c + d * (f.R + 18), 9)
            if not f.is_player:
                text(s, f.name, 20, TEXT, (c.x, c.y - 38), "center")
                pygame.draw.rect(s, (40, 20, 24), (c.x - 22, c.y - 28, 44, 5))
                pygame.draw.rect(s, RED, (c.x - 22, c.y - 28, 44 * f.hp / 100, 5))

        for p in self.particles:
            pygame.draw.circle(s, p[3], p[0] - cam, max(1, int(p[2] * 8)))

    def draw_minimap(self):
        s = self.screen
        sc = 0.075
        mm = pygame.Rect(16, 16, int(WORLD_W * sc), int(WORLD_H * sc))
        pygame.draw.rect(s, (10, 13, 22), mm)
        for o in OBST:
            pygame.draw.rect(s, (60, 72, 100), (mm.x + o.x * sc, mm.y + o.y * sc,
                                                max(2, o.w * sc), max(2, o.h * sc)))
        for f in self.fighters:
            if f.alive:
                col = (255, 255, 255) if f.is_player else RED
                pygame.draw.circle(s, col, (mm.x + f.pos.x * sc, mm.y + f.pos.y * sc), 3)
        pygame.draw.rect(s, PANEL_EDGE, mm, 2)

    def draw_hud(self):
        s = self.screen
        p = self.player
        self.draw_minimap()

        # top centre: timer + score
        secs = max(0, int(self.time_left))
        panel = pygame.Rect(W // 2 - 110, 12, 220, 66)
        pygame.draw.rect(s, (10, 13, 22), panel, border_radius=8)
        pygame.draw.rect(s, PANEL_EDGE, panel, 2, border_radius=8)
        text(s, "%d:%02d" % (secs // 60, secs % 60), 44, TEXT, (W // 2, 36), "center")
        lead = max(f.kills for f in self.fighters)
        text(s, "YOU %d   TOP %d / %d" % (p.kills, lead, KILL_LIMIT), 22, ACCENT, (W // 2, 63), "center")

        # kill feed
        y = 16
        for a, wpn, b, t, ap, bp in self.feed:
            alpha_col = TEXT if t > 1 else DIM
            line = "%s  [%s]  %s" % (a, wpn, b)
            r = font(26).render(line, True, alpha_col)
            box = pygame.Rect(W - r.get_width() - 34, y, r.get_width() + 20, 30)
            pygame.draw.rect(s, (10, 13, 22), box, border_radius=5)
            if ap or bp:
                pygame.draw.rect(s, ACCENT if ap else RED, box, 2, border_radius=5)
            s.blit(r, (box.x + 10, box.y + 6))
            y += 36

        # health
        bar = pygame.Rect(24, H - 70, 320, 24)
        pygame.draw.rect(s, (10, 13, 22), bar.inflate(8, 8), border_radius=8)
        pygame.draw.rect(s, (40, 48, 68), bar, border_radius=5)
        hpw = int(bar.w * clamp(p.hp, 0, 100) / 100)
        col = GREEN if p.hp > 60 else ACCENT if p.hp > 30 else RED
        if hpw > 0:
            pygame.draw.rect(s, col, (bar.x, bar.y, hpw, bar.h), border_radius=5)
        text(s, "%d" % max(0, p.hp), 28, TEXT, (bar.right - 8, bar.centery), "midright")
        text(s, "HEALTH", 20, DIM, (bar.x, bar.y - 20), shadow=False)
        # dash
        dash_ready = p.dash_cd <= 0
        text(s, "DASH [SHIFT]  " + ("READY" if dash_ready else "%.1fs" % p.dash_cd), 22,
             GREEN if dash_ready else DIM, (bar.x, bar.bottom + 12))

        # ammo + weapon
        w = WEAPONS[p.weapon]
        text(s, "%d" % p.ammo[p.weapon], 84, TEXT if p.ammo[p.weapon] > 0 else RED,
             (W - 150, H - 70), "midright")
        text(s, "/ %d" % w["mag"], 38, DIM, (W - 140, H - 52), "midleft")
        text(s, p.weapon, 30, ACCENT, (W - 30, H - 124), "midright")
        if p.reload_t > 0:
            frac = 1 - p.reload_t / w["reload"]
            text(s, "RELOADING", 22, ACCENT, (W - 30, H - 24), "midright")
            pygame.draw.rect(s, (40, 48, 68), (W - 230, H - 14, 200, 6))
            pygame.draw.rect(s, ACCENT, (W - 230, H - 14, int(200 * frac), 6))
        for i, k in enumerate(WEAPON_KEYS):
            sel = p.weapon == k
            rc = pygame.Rect(W - 30 - (3 - i) * 62 + 8, H - 160, 54, 26)
            pygame.draw.rect(s, (30, 38, 58) if sel else (10, 13, 22), rc, border_radius=4)
            pygame.draw.rect(s, ACCENT if sel else PANEL_EDGE, rc, 2, border_radius=4)
            text(s, str(i + 1), 22, ACCENT if sel else DIM, rc.center, "center", shadow=False)

    def draw_scoreboard(self, title=None, top=150):
        s = self.screen
        board = sorted(self.fighters, key=lambda f: (-f.kills, f.deaths))
        panel = pygame.Rect(W // 2 - 280, top, 560, 70 + 38 * len(board))
        pygame.draw.rect(s, (10, 13, 22), panel, border_radius=10)
        pygame.draw.rect(s, PANEL_EDGE, panel, 2, border_radius=10)
        text(s, title or "SCOREBOARD", 34, ACCENT, (panel.centerx, panel.y + 26), "center")
        text(s, "KILLS", 22, DIM, (panel.right - 170, panel.y + 56), "midright", shadow=False)
        text(s, "DEATHS", 22, DIM, (panel.right - 30, panel.y + 56), "midright", shadow=False)
        for i, f in enumerate(board):
            y = panel.y + 82 + i * 38
            if f.is_player:
                pygame.draw.rect(s, (30, 38, 58), (panel.x + 8, y - 4, panel.w - 16, 32), border_radius=5)
            pygame.draw.circle(s, f.color, (panel.x + 30, y + 12), 9)
            text(s, "%d.  %s" % (i + 1, f.name), 28, TEXT, (panel.x + 52, y))
            text(s, f.kills, 28, TEXT, (panel.right - 170, y + 12), "midright")
            text(s, f.deaths, 28, DIM, (panel.right - 30, y + 12), "midright")

    def draw_play(self):
        s = self.screen
        off = V2()
        if self.shake > 0:
            m = self.shake * 10
            off = V2(random.uniform(-m, m), random.uniform(-m, m))
        s.fill(BG)
        self.draw_world(off)

        if self.dmg_flash > 0:
            self.red.set_alpha(int(110 * self.dmg_flash / 0.4))
            s.blit(self.red, (0, 0))

        self.draw_hud()

        p = self.player
        keys = pygame.key.get_pressed()
        if keys[pygame.K_TAB] or keys[pygame.K_q]:
            self.draw_scoreboard()

        if not p.alive:
            self.dark.set_alpha(110)
            s.blit(self.dark, (0, 0))
            text(s, "ELIMINATED", 90, RED, (W // 2, H // 2 - 40), "center")
            by = p.killer.name if p.killer is not None else "the arena"
            text(s, "by %s   -   respawn in %d" % (by, int(p.respawn_t) + 1), 36, TEXT,
                 (W // 2, H // 2 + 20), "center")

        if self.paused:
            self.dark.set_alpha(170)
            s.blit(self.dark, (0, 0))
            text(s, "PAUSED", 100, ACCENT, (W // 2, H // 2 - 50), "center")
            text(s, "ESC  resume        M  quit to menu", 34, TEXT, (W // 2, H // 2 + 20), "center")
        else:
            mx, my = pygame.mouse.get_pos()
            spread = 5 + (8 if pygame.mouse.get_pressed()[0] else 0) + int(p.flash * 100)
            self.draw_crosshair(mx, my, spread)
            if self.hitmarker > 0:
                for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                    pygame.draw.line(s, RED, (mx + dx * 6, my + dy * 6), (mx + dx * 14, my + dy * 14), 3)

    def draw_end(self):
        s = self.screen
        self.draw_bg_grid(8)
        won = self.winner is self.player
        text(s, "VICTORY" if won else "MATCH OVER", 120, GREEN if won else ACCENT, (W // 2, 70), "center")
        text(s, "%s wins the match" % self.winner.name, 36, TEXT, (W // 2, 134), "center")
        self.draw_scoreboard("FINAL STANDINGS", 170)
        rects = self.end_rects()
        self.button(rects["again"], "PLAY AGAIN", True, 34)
        self.button(rects["menu"], "MENU", False, 34)
        mx, my = pygame.mouse.get_pos()
        self.draw_crosshair(mx, my, 0)

    def draw(self):
        if self.state == "menu":
            self.draw_menu()
        elif self.state == "play":
            self.draw_play()
        else:
            self.draw_end()


# --------------------------------------------------------------------------
# Entry point (async loop is required by pygbag; it also runs fine on desktop)
# --------------------------------------------------------------------------
async def main():
    pygame.init()
    flags = pygame.SCALED | pygame.RESIZABLE
    screen = pygame.display.set_mode((W, H), flags)
    pygame.display.set_caption("WAR ZONE - 2D Battle Arena")
    clock = pygame.time.Clock()
    game = Game(screen)
    while True:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            game.handle_event(e)
        game.update(dt)
        game.draw()
        pygame.display.flip()
        await asyncio.sleep(0)


asyncio.run(main())
