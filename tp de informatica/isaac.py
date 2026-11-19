# -*- coding: utf-8 -*-
"""
THE BINDING OF ISAAC - mini edición (2 pisos)
=============================================
Requisitos:  pip install pygame
Ejecutar:    python isaac.py
             (en la misma carpeta tienen que estar: player.png, player_blink.png,
              player_hurt.png y logo.png)

Controles
  WASD ........ moverte
  Flechas ..... disparar lágrimas
  P ........... pausa
  R ........... reiniciar (cuando morís o ganás)
  ESC ......... salir

Objetivo: pasá los 2 pisos. En cada uno limpiá las salas, agarrá el ítem de
la sala dorada, vencé al jefe (puerta roja) y bajá por la trampilla.
"""
import math
import os
import random
import sys
from collections import deque

import pygame
from pygame import Vector2 as V2

# ----------------------------------------------------------------------------
# Constantes
# ----------------------------------------------------------------------------
TILE = 64
COLS, ROWS = 13, 7                      # tamaño interior de cada sala (en tiles)
W, H = (COLS + 2) * TILE, (ROWS + 2) * TILE   # 960 x 576
FPS = 60
DOOR_W = 96
HUD_H = 64          # franja del HUD arriba de la sala
FLOOR_NAMES = ["TALLER DE AUTOMOTOR I", "TALLER DE AUTOMOTOR II"]
INNER = pygame.Rect(TILE, TILE, COLS * TILE, ROWS * TILE)

DIRS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}
OPP = {"U": "D", "D": "U", "L": "R", "R": "L"}

SHOOT_KEYS = {
    pygame.K_UP: V2(0, -1),
    pygame.K_DOWN: V2(0, 1),
    pygame.K_LEFT: V2(-1, 0),
    pygame.K_RIGHT: V2(1, 0),
}

PLAYER_IMGS = {}       # "open" | "blink" | "hurt" (se cargan en Game.load_assets())
PLAYER_H = 66          # alto del personaje en pantalla (px)
# posición de los ojos dentro del sprite (0..1), para sacar las lágrimas de ahí
EYE_N = ((0.303, 0.56), (0.699, 0.56))


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def draw_text(surf, font, txt, pos, color=(255, 255, 255), center=True, shadow=(0, 0, 0)):
    img = font.render(txt, True, color)
    sh = font.render(txt, True, shadow)
    rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    surf.blit(sh, rect.move(2, 2))
    surf.blit(img, rect)


def push_out(pos, r, rect):
    """Saca un círculo (pos, r) de adentro de un rectángulo. Devuelve True si chocó."""
    cx = min(max(pos.x, rect.left), rect.right)
    cy = min(max(pos.y, rect.top), rect.bottom)
    dx, dy = pos.x - cx, pos.y - cy
    d2 = dx * dx + dy * dy
    if d2 >= r * r:
        return False
    if d2 > 1e-9:
        d = math.sqrt(d2)
        pos.x += dx / d * (r - d)
        pos.y += dy / d * (r - d)
    else:
        opts = [
            (pos.x - rect.left, -1, 0),
            (rect.right - pos.x, 1, 0),
            (pos.y - rect.top, 0, -1),
            (rect.bottom - pos.y, 0, 1),
        ]
        dist, nx, ny = min(opts)
        pos.x += nx * (dist + r)
        pos.y += ny * (dist + r)
    return True


def heart_surface(size, fill, outline):
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    pts = []
    for i in range(60):
        t = i / 60 * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((size / 2 + x * size / 36, size * 0.45 + y * size / 36))
    pygame.draw.polygon(s, fill, pts)
    pygame.draw.polygon(s, outline, pts, 2)
    return s


def blob(s, cx, cy, rx, ry, fill, outline, ow=3):
    """Elipse con borde (sirve para animar squash & stretch)."""
    pygame.draw.ellipse(s, outline, pygame.Rect(int(cx - rx - ow), int(cy - ry - ow), int(2 * (rx + ow)), int(2 * (ry + ow))))
    pygame.draw.ellipse(s, fill, pygame.Rect(int(cx - rx), int(cy - ry), int(2 * rx), int(2 * ry)))


# ----------------------------------------------------------------------------
# Ítems (sala del tesoro)
# ----------------------------------------------------------------------------
def _teclado(p):
    p.damage += 1.5


def _mouse(p):
    p.delay *= 0.72


def _ram(p):
    p.speed += 45


def _pendrive(p):
    p.max_hp += 2
    p.hp = min(p.max_hp, p.hp + 2)


def _monitor(p):
    p.range_t += 0.3


def _gpu(p):
    p.damage += 2.5
    p.delay *= 1.12


# (nombre, descripción, efecto, sprite)
ITEMS = [
    ("Teclado mecánico", "+ daño", _teclado, "keyboard"),
    ("Mouse gamer", "Lágrimas más rápidas", _mouse, "mouse"),
    ("Memoria RAM", "+ velocidad", _ram, "ram"),
    ("Pendrive con backup", "+1 corazón", _pendrive, "usb"),
    ("Monitor ultrawide", "+ alcance", _monitor, "monitor"),
    ("Placa de video", "Mucho más daño, pero dispara un poco más lento", _gpu, "gpu"),
]


def draw_item_icon(s, key, cx, cy, size=48):
    """Sprite (hecho con formas) de un objeto de informática, centrado en (cx, cy)."""
    u = size / 48.0

    def R(x, y, w, h):
        return pygame.Rect(int(cx + (x - 24) * u), int(cy + (y - 24) * u), max(1, int(w * u)), max(1, int(h * u)))

    def P(x, y):
        return (int(cx + (x - 24) * u), int(cy + (y - 24) * u))

    def br(v):
        return max(0, int(v * u))

    lw = max(1, int(2 * u))
    ol = (18, 14, 18)
    if key == "keyboard":
        pygame.draw.rect(s, ol, R(0, 10, 48, 30), border_radius=br(4))
        pygame.draw.rect(s, (54, 58, 74), R(2, 12, 44, 26), border_radius=br(3))
        accent = [(255, 90, 90), (255, 200, 70), (90, 230, 130), (80, 200, 255), (190, 120, 255)]
        for row in range(2):
            for i in range(9):
                col = accent[(i + row) % 5] if i % 3 == 0 else (208, 212, 224)
                pygame.draw.rect(s, col, R(4.5 + i * 4.4, 14.5 + row * 7.2, 3.6, 5.2), border_radius=br(1))
        for kx, kw in ((5, 7), (13, 20), (35, 8)):
            pygame.draw.rect(s, (208, 212, 224), R(kx, 29, kw, 5), border_radius=br(1))
        pygame.draw.rect(s, (80, 220, 255), R(3, 38.5, 42, 2))
    elif key == "mouse":
        pygame.draw.line(s, (90, 94, 110), P(24, 6), P(24, 0), lw)
        pygame.draw.ellipse(s, ol, R(10, 5, 28, 40))
        pygame.draw.ellipse(s, (62, 66, 84), R(12, 7, 24, 36))
        pygame.draw.line(s, ol, P(24, 8), P(24, 22), lw)
        pygame.draw.line(s, ol, P(14, 22), P(34, 22), lw)
        pygame.draw.rect(s, (80, 220, 255), R(22, 11, 4, 8), border_radius=br(2))
        pygame.draw.rect(s, (255, 90, 200), R(19, 36, 10, 3), border_radius=br(1))
    elif key == "ram":
        pygame.draw.rect(s, ol, R(0, 11, 48, 28), border_radius=br(2))
        pygame.draw.rect(s, (36, 140, 82), R(2, 13, 44, 20))
        for i in range(5):
            pygame.draw.rect(s, (24, 24, 30), R(5 + i * 8, 15.5, 6, 9), border_radius=br(1))
            pygame.draw.rect(s, (70, 72, 84), R(5 + i * 8, 15.5, 6, 3))
        pygame.draw.rect(s, (235, 235, 225), R(6, 27, 22, 4))
        for i in range(15):
            pygame.draw.rect(s, (232, 192, 62), R(3 + i * 2.9, 33, 2, 5))
        pygame.draw.rect(s, (36, 140, 82), R(22.5, 33, 2.5, 5))
    elif key == "usb":
        pygame.draw.rect(s, ol, R(0, 17, 19, 14), border_radius=br(2))
        pygame.draw.rect(s, (196, 202, 214), R(2, 19, 15, 10))
        pygame.draw.rect(s, (40, 40, 52), R(5, 22, 3, 4))
        pygame.draw.rect(s, (40, 40, 52), R(11, 22, 3, 4))
        pygame.draw.rect(s, ol, R(15, 12, 33, 24), border_radius=br(5))
        pygame.draw.rect(s, (60, 120, 220), R(17, 14, 29, 20), border_radius=br(4))
        pygame.draw.rect(s, (120, 255, 150), R(37, 18, 5, 5), border_radius=br(2))
        pygame.draw.rect(s, (200, 225, 255), R(21, 26, 14, 3))
    elif key == "monitor":
        pygame.draw.rect(s, ol, R(2, 4, 44, 30), border_radius=br(3))
        pygame.draw.rect(s, (40, 44, 56), R(4, 6, 40, 26), border_radius=br(2))
        pygame.draw.rect(s, (64, 150, 235), R(7, 9, 34, 20))
        pygame.draw.polygon(s, (120, 195, 255), [P(7, 9), P(24, 9), P(15, 29), P(7, 29)])
        for yy, ww in ((12, 14), (17, 22), (22, 10)):
            pygame.draw.rect(s, (245, 250, 255), R(10, yy, ww, 2))
        pygame.draw.rect(s, (110, 115, 128), R(21, 34, 6, 6))
        pygame.draw.rect(s, ol, R(13, 39, 22, 5), border_radius=br(2))
        pygame.draw.rect(s, (140, 145, 158), R(14, 40, 20, 3), border_radius=br(1))
    else:  # gpu
        pygame.draw.rect(s, ol, R(0, 10, 48, 28), border_radius=br(3))
        pygame.draw.rect(s, (34, 36, 46), R(2, 12, 44, 24), border_radius=br(2))
        pygame.draw.rect(s, (110, 230, 90), R(4, 13, 40, 3))
        for fx in (15, 33):
            pygame.draw.circle(s, ol, P(fx, 25), br(9))
            pygame.draw.circle(s, (86, 90, 108), P(fx, 25), br(7.5))
            for k in range(3):
                a = k * 2.094 + 0.5
                pygame.draw.line(s, (20, 20, 28), P(fx, 25), P(fx + math.cos(a) * 7, 25 + math.sin(a) * 7), lw)
            pygame.draw.circle(s, (20, 20, 28), P(fx, 25), br(2.5))
        pygame.draw.rect(s, (232, 192, 62), R(8, 36, 24, 3))
        pygame.draw.rect(s, (190, 196, 208), R(0, 10, 3, 28))


class Pickup:
    def __init__(self, kind, pos, item=None):
        self.kind = kind          # 'heart' | 'item'
        self.pos = V2(pos)
        self.item = item
        self.taken = False


# ----------------------------------------------------------------------------
# Proyectiles y partículas
# ----------------------------------------------------------------------------
class Tear:
    def __init__(self, pos, vel, dmg, friendly, life=0.8, r=9):
        self.pos = V2(pos)
        self.vel = V2(vel)
        self.dmg = dmg
        self.friendly = friendly
        self.life = life
        self.r = r
        self.dead = False

    def update(self, dt, game):
        self.pos += self.vel * dt
        self.life -= dt
        if self.life <= 0:
            self.dead = True
            return
        if not INNER.inflate(-self.r, -self.r).collidepoint(self.pos.x, self.pos.y):
            self.dead = True
            return
        for rock in game.room.rocks:
            if rock.inflate(self.r, self.r).collidepoint(self.pos.x, self.pos.y):
                self.dead = True
                return

    def draw(self, s):
        r = self.r
        if self.life < 0.12:
            r = max(2, int(r * self.life / 0.12))
        if self.friendly:
            out, inn = (70, 120, 150), (190, 225, 245)
        else:
            out, inn = (90, 20, 25), (215, 70, 80)
        p = (int(self.pos.x), int(self.pos.y))
        pygame.draw.circle(s, out, p, r + 2)
        pygame.draw.circle(s, inn, p, r)
        pygame.draw.circle(s, (255, 255, 255), (p[0] - r // 3, p[1] - r // 3), max(2, r // 3))


class Particle:
    def __init__(self, pos, vel, life, color, r):
        self.pos = V2(pos)
        self.vel = V2(vel)
        self.life = self.max_life = life
        self.color = color
        self.r = r

    def update(self, dt):
        self.pos += self.vel * dt
        self.vel *= 0.92
        self.life -= dt

    def draw(self, s):
        r = max(1, int(self.r * self.life / self.max_life))
        pygame.draw.circle(s, self.color, (int(self.pos.x), int(self.pos.y)), r)


# ----------------------------------------------------------------------------
# Jugador
# ----------------------------------------------------------------------------
class CryDrop:
    """Gotita de lágrima que cae de la cara del personaje."""

    def __init__(self, pos, vel, life, r):
        self.pos = V2(pos)
        self.vel = V2(vel)
        self.life = self.max_life = life
        self.r = r

    def update(self, dt):
        self.vel.y += 650 * dt
        self.pos += self.vel * dt
        self.life -= dt

    def draw(self, s):
        r = self.r
        if self.life < 0.15:
            r = max(1, int(r * self.life / 0.15))
        p = (int(self.pos.x), int(self.pos.y))
        pygame.draw.circle(s, (70, 120, 150), p, r + 1)
        pygame.draw.circle(s, (190, 225, 245), p, r)
        pygame.draw.circle(s, (255, 255, 255), (p[0] - r // 3, p[1] - r // 3), max(1, r // 3))


class Player:
    r = 18

    def __init__(self):
        self.pos = V2(W / 2, H / 2)
        self.vel = V2()
        self.max_hp = 8            # en medios corazones
        self.hp = 8
        self.speed = 290
        self.damage = 3.5
        self.delay = 0.34
        self.tear_speed = 480
        self.range_t = 0.7
        self.cool = 0.0
        self.invuln = 0.0
        self.eye = 1
        self.items = []
        # --- animación ---
        self.anim_t = 0.0
        self.blink_t = 0.0                         # > 0: ojos cerrados (parpadeo)
        self.next_blink = random.uniform(1.2, 3.0)
        self.sob_t = 0.0                           # > 0: sollozo (ojos cerrados, tiembla, llora más)
        self.next_sob = random.uniform(3.0, 6.0)
        self.hurt_t = 0.0                          # > 0: cara de dolor (ojos apretados)
        self.shoot_t = 0.0                         # > 0: cierra los ojos al disparar
        self.lean = 0.0                            # inclinación suavizada (grados)
        self.dead = False
        self.drops = []
        self.cry_acc = 0.0

    # ----- eventos que dispara el juego -----
    def on_shoot(self):
        self.shoot_t = 0.09
        self.burst(2)

    def on_hurt(self):
        self.hurt_t = 0.7
        self.blink_t = 0.0
        self.burst(8)

    # ----- pose (sprite, escala, ángulo, posición de los ojos) -----
    def pose(self):
        t = self.anim_t
        x, y = self.pos.x, self.pos.y
        moving = self.vel.length() > 30
        if moving:
            bob = abs(math.sin(t * 12)) * 3
            sq = 1 + math.sin(t * 24) * 0.035          # squash & stretch al caminar
        else:
            bob = 0.0
            sq = 1 + math.sin(t * 3.0) * 0.025         # respiración
        dy = dx = 0.0
        if self.sob_t > 0:                              # sollozo: saltitos rápidos
            k = min(1.0, self.sob_t / 0.7)
            dy -= abs(math.sin(t * 26)) * 2.5 * k
            sq += math.sin(t * 26) * 0.03 * k
        if self.hurt_t > 0:                             # temblor al recibir daño
            dx += math.sin(t * 90) * 2.5 * min(1.0, self.hurt_t / 0.3)
        sx, sy = 2 - sq, sq
        if self.dead:                                   # derrotado: se desinfla un poco
            sx, sy = 1.08, 0.92

        if self.dead or self.hurt_t > 0:
            key = "hurt"
        elif self.blink_t > 0 or self.sob_t > 0 or self.shoot_t > 0:
            key = "blink"
        else:
            key = "open"

        base = PLAYER_IMGS.get(key)
        if base is None:
            return None
        h0 = PLAYER_H
        w0 = base.get_width() * h0 / base.get_height()
        w, h = w0 * sx, h0 * sy
        bottom = y + 23 - bob + dy
        cx, cy = x + dx, bottom - h / 2
        th = math.radians(self.lean)
        eyes = []
        for nx, ny in EYE_N:
            ox, oy = (nx - 0.5) * w, (ny - 0.5) * h
            eyes.append((cx + ox * math.cos(th) - oy * math.sin(th),
                         cy + ox * math.sin(th) + oy * math.cos(th)))
        return {"key": key, "size": (max(2, int(w)), max(2, int(h))), "center": (cx, cy), "eyes": eyes}

    # ----- lágrimas -----
    def emit_drop(self, strong=False):
        pz = self.pose()
        if pz is None:
            eyes = [(self.pos.x - 13, self.pos.y - 4), (self.pos.x + 13, self.pos.y - 4)]
        else:
            eyes = pz["eyes"]
        ex, ey = random.choice(eyes)
        side = -1 if ex < self.pos.x else 1
        vx = side * (random.uniform(10, 40) if strong else random.uniform(0, 14))
        vy = random.uniform(-30, 10) if strong else random.uniform(10, 40)
        r = random.choice((3, 4, 4, 5)) if strong else random.choice((2, 3, 3, 4))
        self.drops.append(CryDrop((ex + random.uniform(-3, 3), ey), (vx, vy), random.uniform(0.45, 0.75), r))

    def burst(self, n):
        for _ in range(n):
            self.emit_drop(True)

    def animate(self, dt, state="playing"):
        self.dead = state == "dead"
        self.anim_t += dt
        self.hurt_t = max(0.0, self.hurt_t - dt)
        self.shoot_t = max(0.0, self.shoot_t - dt)

        # parpadeo (a veces doble)
        if self.blink_t > 0:
            self.blink_t -= dt
        else:
            self.next_blink -= dt
            if self.next_blink <= 0:
                self.blink_t = 0.14
                self.next_blink = 0.28 if random.random() < 0.2 else random.uniform(1.8, 4.0)

        # sollozo: más seguido si queda poca vida
        if self.sob_t > 0:
            self.sob_t -= dt
        else:
            self.next_sob -= dt
            if self.next_sob <= 0:
                self.sob_t = 0.7
                self.next_sob = random.uniform(3.5, 7.0) * (0.5 if self.hp <= 2 else 1.0)
                self.burst(3)

        # inclinación al moverse
        target = max(-7.0, min(7.0, self.vel.x / 290.0 * 7.0))
        self.lean += (target - self.lean) * min(1.0, dt * 10)

        # llanto continuo
        rate = 5.0 + (5.0 if self.hp <= 2 else 0.0)
        if self.sob_t > 0:
            rate += 22
        if self.hurt_t > 0:
            rate += 40
        if self.dead:
            rate = 28
        self.cry_acc += rate * dt
        while self.cry_acc >= 1:
            self.cry_acc -= 1
            self.emit_drop(self.sob_t > 0 or self.hurt_t > 0 or self.dead)

        for d in self.drops:
            d.update(dt)
        floor_y = self.pos.y + 24
        self.drops = [d for d in self.drops if d.life > 0 and d.pos.y < floor_y]

    def draw(self, s, t):
        x, y = self.pos.x, self.pos.y
        pygame.draw.ellipse(s, (35, 28, 24), pygame.Rect(int(x - 22), int(y + 14), 44, 14))
        flicker = self.invuln > 0 and int(t * 14) % 2 == 0
        if not flicker:
            pz = self.pose()
            if pz is not None:
                img = pygame.transform.smoothscale(PLAYER_IMGS[pz["key"]], pz["size"])
                if abs(self.lean) > 0.4:
                    img = pygame.transform.rotozoom(img, -self.lean, 1.0)
                s.blit(img, img.get_rect(center=(int(pz["center"][0]), int(pz["center"][1]))))
            else:
                pygame.draw.circle(s, (200, 150, 150), (int(x), int(y)), 24)
        for d in self.drops:
            d.draw(s)


# ----------------------------------------------------------------------------
# Enemigos
# ----------------------------------------------------------------------------
class Enemy:
    r = 16
    max_hp = 10
    contact = 1
    flying = False

    def __init__(self, pos):
        self.pos = V2(pos)
        self.vel = V2()
        self.hp = self.max_hp
        self.flash = 0.0
        self.dead = False
        self.spawn_t = self.spawn_total = 0.7
        self.t = random.random() * 6      # reloj de animación
        self.look_at = None               # a dónde mira (el jugador)

    touching = True
    hittable = True

    def hurt(self, dmg):
        self.hp -= dmg
        self.flash = 0.09
        if self.hp <= 0:
            self.dead = True

    def look(self, mx):
        """Vector hacia el jugador (largo mx) para mover pupilas."""
        if self.look_at is None:
            return V2()
        d = self.look_at - self.pos
        l = d.length()
        return d / l * mx if l > 1 else V2()

    def update(self, dt, g):
        pass

    def shadow(self, s, w=None):
        w = w or self.r * 2
        pygame.draw.ellipse(
            s, (35, 28, 24),
            pygame.Rect(int(self.pos.x - w / 2), int(self.pos.y + self.r * 0.55), int(w), int(self.r * 0.6)),
        )

    def col(self, base):
        return (255, 255, 255) if self.flash > 0 else base


class Fly(Enemy):
    r = 13
    max_hp = 5
    flying = True

    def update(self, dt, g):
        to = g.player.pos - self.pos
        d = to.length() or 1
        desired = to / d * 95 + V2(math.cos(self.t * 3.1), math.sin(self.t * 2.3)) * 75
        self.vel += (desired - self.vel) * min(1, dt * 3)
        self.pos += self.vel * dt
        g.confine(self)

    def draw(self, s, t):
        x, y = int(self.pos.x), int(self.pos.y - 8 + math.sin(self.t * 8) * 2)
        self.shadow(s, 22)
        flap = 5 + int(abs(math.sin(self.t * 40)) * 5)
        for sx in (-1, 1):
            pygame.draw.ellipse(s, (200, 220, 235), pygame.Rect(x + sx * 9 - 6, y - flap - 4, 12, flap * 2))
        pygame.draw.circle(s, (20, 16, 16), (x, y), 11)
        pygame.draw.circle(s, self.col((70, 60, 60)), (x, y), 9)
        pygame.draw.circle(s, (230, 60, 60), (x - 3, y - 2), 2)
        pygame.draw.circle(s, (230, 60, 60), (x + 3, y - 2), 2)


class Gaper(Enemy):
    r = 22
    max_hp = 14
    speed = 85

    def update(self, dt, g):
        to = g.player.pos - self.pos
        d = to.length()
        if d > 1:
            self.vel += (to / d * self.speed - self.vel) * min(1, dt * 4)
        self.pos += self.vel * dt
        g.confine(self)

    def draw(self, s, t):
        x, y = int(self.pos.x), int(self.pos.y)
        self.shadow(s)
        walk = math.sin(self.t * 9)
        kx, ky = 1 + 0.07 * walk, 1 - 0.07 * walk          # squash & stretch al caminar
        rx, ry = self.r * kx, self.r * ky
        base = y + self.r                                   # los pies quedan fijos en el piso
        cy = base - ry - 6
        for k in (-1, 1):                                   # patitas que se alternan
            lift = max(0.0, math.sin(self.t * 9 + (0 if k < 0 else math.pi))) * 5
            pygame.draw.ellipse(s, (60, 30, 30), pygame.Rect(int(x + k * 10 - 6), int(base - 8 - lift), 12, 10))
        blob(s, x, cy, rx, ry, self.col((208, 150, 140)), (60, 30, 30))
        lk = self.look(2)
        for k in (-1, 1):                                   # ojos huecos que siguen al jugador
            ex, ey = int(x + k * 9 * kx), int(cy - 6)
            pygame.draw.circle(s, (20, 10, 10), (ex, ey), 6)
            pygame.draw.circle(s, (235, 225, 220), (int(ex + lk.x), int(ey + lk.y)), 2)
        mouth = 6 + 6 * (0.5 + 0.5 * math.sin(self.t * 5))  # boca que abre y cierra
        pygame.draw.ellipse(s, (60, 15, 20), pygame.Rect(int(x - 9), int(cy + 4), 18, int(mouth)))
        pygame.draw.line(s, (170, 40, 40), (int(x + 14 * kx), int(cy - 14)), (int(x + 8 * kx), int(cy + 8)), 2)


class Shooter(Enemy):
    r = 22
    max_hp = 16

    def __init__(self, pos):
        super().__init__(pos)
        self.cd = 1.2 + random.random()
        self.windup = 0.0
        self.recoil = 0.0

    def update(self, dt, g):
        self.cd -= dt
        self.recoil = max(0.0, self.recoil - dt)
        to = g.player.pos - self.pos
        d = to.length() or 1
        self.vel += (to / d * 28 - self.vel) * min(1, dt * 2)
        self.pos += self.vel * dt
        g.confine(self)
        if self.cd <= 0.4:
            self.windup = 1
        if self.cd <= 0:
            base = math.atan2(to.y, to.x)
            for off in (-0.28, 0, 0.28):
                a = base + off
                g.etears.append(Tear(self.pos, V2(math.cos(a), math.sin(a)) * 250, 1, False, 2.6, 8))
            self.cd = 2.1 + random.random() * 0.6
            self.windup = 0
            self.recoil = 0.2

    def draw(self, s, t):
        x, y = int(self.pos.x), int(self.pos.y)
        self.shadow(s)
        breathe = math.sin(self.t * 3) * 1.5                # respira
        shake = random.randint(-2, 2) if self.windup else 0   # tiembla antes de disparar
        k = self.recoil / 0.2                               # se aplasta al disparar
        rx = self.r + breathe + 5 * k
        ry = self.r + breathe - 5 * k
        cx, cy = x + shake, y
        body = (165, 150, 170)
        blob(s, cx, cy, rx, ry, self.col(body), (45, 35, 45))
        if self.windup:
            pygame.draw.ellipse(s, (220, 60, 60), pygame.Rect(int(cx - rx - 2), int(cy - ry - 2), int(2 * rx + 4), int(2 * ry + 4)), 3)
        eye = (255, 205, 205) if self.windup else (250, 250, 250)
        pygame.draw.circle(s, eye, (int(cx), int(cy - 2)), 11)
        lk = self.look(4)                                   # la pupila sigue al jugador
        pygame.draw.circle(s, (15, 10, 15), (int(cx + lk.x), int(cy - 2 + lk.y)), 5)
        if (self.t % 3.2) > 3.06:                           # parpadeo
            pygame.draw.ellipse(s, body, pygame.Rect(int(cx - 12), int(cy - 14), 24, 24))
            pygame.draw.line(s, (45, 35, 45), (int(cx - 11), int(cy - 2)), (int(cx + 11), int(cy - 2)), 3)


class Boss(Enemy):
    """EL LLORÓN: salta hacia vos y escupe lágrimas."""
    r = 66
    max_hp = 170
    contact = 2
    flying = True
    name = "EL LLORÓN"
    JUMP_T = 0.75

    def __init__(self, pos, tier=1):
        self.tier = tier                                    # 1 = piso 1, 2 = piso 2 (más duro)
        self.max_hp = 120 if tier == 1 else 200
        self.name = "EL LLORÓN" if tier == 1 else "EL LLORÓN FURIOSO"
        self.rate = 1.0 if tier == 1 else 0.7               # tiempo entre ataques
        super().__init__(pos)
        self.state = "idle"
        self.timer = 1.3
        self.spawn_t = self.spawn_total = 1.0
        self.squash = 0.0

    @property
    def touching(self):
        return self.state != "jump"

    @property
    def hittable(self):
        return self.state != "jump"

    def update(self, dt, g):
        self.timer -= dt
        self.squash = max(0.0, self.squash - dt)
        P = g.player.pos
        if self.state == "idle":
            if self.timer <= 0:
                if random.random() < 0.5:
                    to = P - self.pos
                    dist = min(to.length(), 380)
                    dirv = to.normalize() if to.length() > 1 else V2(1, 0)
                    self.vel = dirv * dist / self.JUMP_T
                    self.state, self.timer = "jump", self.JUMP_T
                else:
                    self.state, self.timer = "windup", 0.55
        elif self.state == "jump":
            self.pos += self.vel * dt
            g.confine(self)
            if self.timer <= 0:
                self.vel = V2()
                g.shake = 0.35
                n = 10 if self.tier == 1 else 14
                for i in range(n):
                    a = i / n * 2 * math.pi
                    g.etears.append(Tear(self.pos, V2(math.cos(a), math.sin(a)) * 230, 2, False, 2.5, 10))
                self.state, self.timer = "idle", 0.9 * self.rate
                self.squash = 0.25
        elif self.state == "windup":
            if self.timer <= 0:
                to = P - self.pos
                base = math.atan2(to.y, to.x)
                half = 4 if self.tier == 1 else 5
                for i in range(-half, half + 1):
                    a = base + i * 0.17 + random.uniform(-0.05, 0.05)
                    sp = 220 + random.random() * 70
                    g.etears.append(Tear(self.pos, V2(math.cos(a), math.sin(a)) * sp, 1, False, 2.6, 9))
                self.state, self.timer = "idle", 1.0 * self.rate

    def draw(self, s, t):
        lift, stretch = 0.0, 1.0
        if self.state == "jump":
            prog = 1 - self.timer / self.JUMP_T
            lift = math.sin(prog * math.pi) * 70
            stretch = 1 + 0.12 * math.sin(prog * math.pi)   # se estira en el aire
        elif self.squash > 0:
            stretch = 1 - 0.22 * (self.squash / 0.25)       # se aplasta al caer
        R = (self.r + math.sin(self.t * 2.5) * 2) * (1.1 if self.state == "windup" else 1.0)
        rx, ry = R * (1 + (1 - stretch) * 0.8), R * stretch
        cy = self.pos.y - lift + (self.r - ry)              # los "pies" quedan en el piso
        sw = int(rx * 2 * (1 - lift / 320))
        pygame.draw.ellipse(s, (35, 28, 24), pygame.Rect(int(self.pos.x - sw / 2), int(self.pos.y + self.r * 0.6), sw, 36))
        shake = random.randint(-2, 2) if self.state == "windup" else 0
        bx, by = int(self.pos.x + shake), int(cy)
        body = (214, 150, 150) if self.tier == 1 else (226, 118, 122)
        blob(s, bx, by, rx, ry, self.col(body), (60, 25, 30), 4)
        pygame.draw.ellipse(s, self.col((236, 190, 190)), pygame.Rect(int(bx - rx * 0.55), int(by - ry * 0.75), int(rx * 0.28), int(ry * 0.2)))
        lk = self.look(6)
        blinking = (self.t % 4.0) > 3.85
        for k in (-1, 1):
            ex, ey = int(bx + k * rx * 0.4), int(by - ry * 0.15)
            pygame.draw.rect(s, (130, 200, 215), pygame.Rect(ex - 9, ey + 6, 18, int(ry * 0.6)), border_radius=8)
            for j in range(3):                              # lagrimas cayendo
                dy = (self.t * 70 + j * 22 + (0 if k < 0 else 11)) % 66
                pygame.draw.circle(s, (205, 242, 250), (ex + (j - 1) * 4, int(ey + 14 + dy * 0.6)), 3)
            pygame.draw.circle(s, (10, 8, 10), (ex, ey), 17)
            pygame.draw.circle(s, (255, 255, 255), (int(ex - 5 + lk.x * 0.4), int(ey - 6 + lk.y * 0.4)), 6)
            if blinking:
                pygame.draw.ellipse(s, body, pygame.Rect(ex - 19, ey - 19, 38, 38))
                pygame.draw.line(s, (60, 25, 30), (ex - 17, ey), (ex + 17, ey), 4)
            if self.tier == 2:                              # cejas enojadas
                pygame.draw.line(s, (60, 25, 30), (ex + k * 20, ey - 26), (ex - k * 14, ey - 15), 5)
        open_h = 34 if self.state == "windup" else int(16 + 4 * math.sin(self.t * 4))
        pygame.draw.ellipse(s, (70, 15, 25), pygame.Rect(bx - 28, int(by + ry * 0.4), 56, open_h))


# ----------------------------------------------------------------------------
# Salas y piso
# ----------------------------------------------------------------------------
def draw_blood(s, rng, x, y):
    """Mancha de sangre con salpicaduras (rng puede ser random o random.Random)."""
    base = rng.choice([(120, 20, 28, 200), (98, 16, 24, 210), (140, 28, 34, 190)])
    size = rng.randint(10, 26)
    for _ in range(rng.randint(4, 8)):
        ox, oy = rng.uniform(-size * 0.6, size * 0.6), rng.uniform(-size * 0.4, size * 0.4)
        w, h = rng.uniform(size * 0.6, size * 1.2), rng.uniform(size * 0.4, size * 0.9)
        pygame.draw.ellipse(s, base, pygame.Rect(int(x + ox - w / 2), int(y + oy - h / 2), int(w), int(h)))
    for _ in range(rng.randint(5, 12)):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(size * 0.9, size * 2.4)
        pygame.draw.circle(s, base, (int(x + math.cos(a) * d), int(y + math.sin(a) * d * 0.7)), rng.randint(1, 4))


def draw_drips(s, rng, x, y):
    """Reguero de gotas de sangre en fila."""
    col = (118, 20, 28, 215)
    a = rng.uniform(0, 2 * math.pi)
    for i in range(rng.randint(4, 8)):
        pygame.draw.circle(s, col, (int(x + math.cos(a) * i * 11), int(y + math.sin(a) * i * 11)), max(1, 4 - i // 2))


def draw_bone(s, rng, x, y):
    L = rng.randint(18, 32)
    a = rng.uniform(0, math.pi)
    dx, dy = math.cos(a) * L / 2, math.sin(a) * L / 2
    ol, col = (92, 80, 66), (228, 218, 192)
    p1, p2 = (x - dx, y - dy), (x + dx, y + dy)
    nx, ny = -math.sin(a) * 3, math.cos(a) * 3
    knobs = [(ex + nx * sg, ey + ny * sg) for ex, ey in (p1, p2) for sg in (-1, 1)]
    pygame.draw.line(s, ol, p1, p2, 7)
    for kx, ky in knobs:
        pygame.draw.circle(s, ol, (int(kx), int(ky)), 4)
    pygame.draw.line(s, col, p1, p2, 4)
    for kx, ky in knobs:
        pygame.draw.circle(s, col, (int(kx), int(ky)), 3)


def draw_skull(s, rng, x, y):
    ol, col = (92, 80, 66), (230, 220, 196)
    pygame.draw.rect(s, ol, pygame.Rect(x - 9, y + 4, 18, 13), border_radius=4)
    pygame.draw.circle(s, ol, (x, y), 14)
    pygame.draw.circle(s, col, (x, y), 12)
    pygame.draw.rect(s, col, pygame.Rect(x - 7, y + 6, 14, 9), border_radius=3)
    for ex in (-5, 5):
        pygame.draw.circle(s, (32, 22, 24), (x + ex, y - 1), 3)
    pygame.draw.polygon(s, (32, 22, 24), [(x, y + 3), (x - 2, y + 7), (x + 2, y + 7)])
    for tx in (-3, 0, 3):
        pygame.draw.line(s, ol, (x + tx, y + 10), (x + tx, y + 15), 1)


def build_decor(s, room):
    """Pinta sangre y huesos al azar en el piso de la sala (se hace una sola vez)."""
    rng = random.Random(room.seed)
    boss = room.kind == "boss"

    def spot(m=44):
        for _ in range(20):
            x, y = rng.randint(INNER.left + m, INNER.right - m), rng.randint(INNER.top + m, INNER.bottom - m)
            # el centro queda libre para el pedestal del ítem / la trampilla
            if room.kind in ("treasure", "boss") and abs(x - W / 2) < 90 and abs(y - H / 2) < 80:
                continue
            break
        return x, y

    for _ in range(rng.randint(1, 3) + (3 if boss else 0)):
        draw_blood(s, rng, *spot())
    for _ in range(rng.randint(0, 2) + (2 if boss else 0)):
        draw_drips(s, rng, *spot(70))
    for _ in range(rng.randint(0, 4) + (2 if boss else 0)):
        draw_bone(s, rng, *spot())
    if rng.random() < (0.9 if boss else 0.4):
        draw_skull(s, rng, *spot())


def make_rocks(kind):
    if kind in ("start", "boss", "treasure"):
        return []
    rocks = set()
    for _ in range(random.randint(2, 7)):
        c, r = random.randrange(COLS), random.randrange(ROWS)
        if 4 <= c <= 8 and (r <= 1 or r >= ROWS - 2):
            continue                      # no tapar puertas de arriba/abajo
        if (c <= 1 or c >= COLS - 2) and 2 <= r <= 4:
            continue                      # no tapar puertas de los costados
        if (c, r) == (COLS // 2, ROWS // 2):
            continue
        rocks.add((c, r))
    return [pygame.Rect(TILE + c * TILE, TILE + r * TILE, TILE, TILE).inflate(-10, -10) for c, r in rocks]


class Room:
    def __init__(self, pos, kind, pool=None):
        self.pos = pos
        self.kind = kind          # start | normal | treasure | boss
        self.seed = random.random()   # para la decoración
        self.decor = None
        self.doors = set()
        self.cleared = kind in ("start", "treasure")
        self.visited = False
        self.spawned = False
        self.enemies = []
        self.pickups = []
        self.rocks = make_rocks(kind)
        self.trapdoor = False
        # logo del colegio en la sala de inicio y en algunas más
        self.logo = kind == "start" or (kind in ("normal", "boss") and random.random() < 0.5)
        spots = [(W // 2 - 250, H // 2), (W // 2 + 250, H // 2)]
        if kind == "normal":
            spots.append((W // 2, H // 2))
        self.logo_pos = random.choice(spots)
        if kind == "treasure":
            self.pickups.append(Pickup("item", (W / 2, H / 2 - 10), random.choice(pool or ITEMS)))


def generate_floor(n, owned=()):
    while True:
        cells = {(0, 0)}
        order = [(0, 0)]
        while len(cells) < n:
            base = random.choice(order)
            dx, dy = random.choice(list(DIRS.values()))
            p = (base[0] + dx, base[1] + dy)
            if p in cells:
                continue
            nb = sum(((p[0] + ex, p[1] + ey) in cells) for ex, ey in DIRS.values())
            if nb > 1 and random.random() < 0.75:
                continue
            cells.add(p)
            order.append(p)

        def nbrs(c):
            return [(c[0] + dx, c[1] + dy) for dx, dy in DIRS.values() if (c[0] + dx, c[1] + dy) in cells]

        dist = {(0, 0): 0}
        q = deque([(0, 0)])
        while q:
            c = q.popleft()
            for nb in nbrs(c):
                if nb not in dist:
                    dist[nb] = dist[c] + 1
                    q.append(nb)
        dead = [c for c in cells if c != (0, 0) and len(nbrs(c)) == 1]
        if len(dead) >= 2:
            break

    boss = max(dead, key=lambda c: dist[c])
    treasure = random.choice([c for c in dead if c != boss])
    pool = [it for it in ITEMS if it[0] not in owned] or ITEMS
    rooms = {}
    for c in cells:
        kind = "start" if c == (0, 0) else "boss" if c == boss else "treasure" if c == treasure else "normal"
        rooms[c] = Room(c, kind, pool)
    for c, room in rooms.items():
        for d, (dx, dy) in DIRS.items():
            if (c[0] + dx, c[1] + dy) in rooms:
                room.doors.add(d)
    return rooms


ENEMY_TEMPLATES = [
    [Fly, Fly, Fly],
    [Gaper, Gaper],
    [Fly, Fly, Gaper],
    [Shooter, Fly, Fly],
    [Gaper, Gaper, Fly],
    [Shooter, Shooter],
    [Fly, Fly, Fly, Fly, Fly],
    [Gaper, Shooter, Fly],
]


def door_rect(d):
    if d == "U":
        return pygame.Rect(W // 2 - DOOR_W // 2, 0, DOOR_W, TILE)
    if d == "D":
        return pygame.Rect(W // 2 - DOOR_W // 2, H - TILE, DOOR_W, TILE)
    if d == "L":
        return pygame.Rect(0, H // 2 - DOOR_W // 2, TILE, DOOR_W)
    return pygame.Rect(W - TILE, H // 2 - DOOR_W // 2, TILE, DOOR_W)


# ----------------------------------------------------------------------------
# Juego
# ----------------------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H + HUD_H))
        pygame.display.set_caption("The Binding of Isaac - mini edición (2 pisos)")
        self.clock = pygame.time.Clock()
        self.font_s = pygame.font.SysFont("arial", 18, bold=True)
        self.font_xs = pygame.font.SysFont("arial", 12, bold=True)
        self.font_m = pygame.font.SysFont("arial", 30, bold=True)
        self.font_l = pygame.font.SysFont("arial", 64, bold=True)
        self.canvas = pygame.Surface((W, H))
        self.veil = pygame.Surface((W, H + HUD_H))
        self.veil.fill((0, 0, 0))
        self.load_assets()
        self.reset()

    # ---------- assets ----------
    def load_assets(self):
        base = os.path.dirname(os.path.abspath(__file__))
        PLAYER_IMGS.clear()
        for key, fn in (("open", "player.png"), ("blink", "player_blink.png"), ("hurt", "player_hurt.png")):
            try:
                PLAYER_IMGS[key] = pygame.image.load(os.path.join(base, fn)).convert_alpha()
            except Exception as e:
                print("No pude cargar", fn, ":", e)
        if "open" in PLAYER_IMGS:                 # si falta alguna cara, usa la normal
            for key in ("blink", "hurt"):
                PLAYER_IMGS.setdefault(key, PLAYER_IMGS["open"])
        else:
            PLAYER_IMGS.clear()                   # sin sprite, usa un círculo

        # logo del colegio (piso, pared y HUD)
        self.logo_floor = self.logo_wall = self.logo_hud = None
        try:
            logo = pygame.image.load(os.path.join(base, "logo.png")).convert_alpha()
            self.logo_floor = pygame.transform.smoothscale(logo, (150, 150))
            self.logo_floor.set_alpha(120)        # semitransparente: parece pintado en el piso
            self.logo_wall = pygame.transform.smoothscale(logo, (46, 46))
            self.logo_hud = pygame.transform.smoothscale(logo, (36, 36))
        except Exception as e:
            print("No pude cargar logo.png:", e)

        self.h_empty = heart_surface(30, (40, 25, 28), (120, 90, 90))
        full = heart_surface(30, (215, 40, 50), (70, 10, 15))
        self.h_full = full
        self.h_half = self.h_empty.copy()
        self.h_half.blit(full, (0, 0), area=pygame.Rect(0, 0, 15, 30))
        self.h_pick = pygame.transform.smoothscale(full, (24, 24))

        # fondo de sala (se dibuja una sola vez)
        rng = random.Random(7)
        bg = pygame.Surface((W, H))
        bg.fill((58, 40, 34))
        for i in range(0, W, 32):
            pygame.draw.line(bg, (48, 32, 27), (i, 0), (i, H), 1)
        for j in range(0, H, 32):
            pygame.draw.line(bg, (48, 32, 27), (0, j), (W, j), 1)
        pygame.draw.rect(bg, (30, 20, 17), INNER.inflate(14, 14), 7)
        for c in range(COLS):
            for r in range(ROWS):
                shade = 112 if (c + r) % 2 == 0 else 106
                pygame.draw.rect(bg, (shade, shade - 20, shade - 34), pygame.Rect(TILE + c * TILE, TILE + r * TILE, TILE, TILE))
        for _ in range(140):
            x = rng.randint(INNER.left, INNER.right)
            y = rng.randint(INNER.top, INNER.bottom)
            pygame.draw.circle(bg, (92, 74, 62), (x, y), rng.randint(1, 3))
        vig = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(14):
            pygame.draw.rect(vig, (0, 0, 0, int(80 * (1 - i / 14))), INNER.inflate(-i * 4, -i * 4), 4)
        bg.blit(vig, (0, 0))
        self.bg = bg

        self.hint1 = self.font_m.render("WASD · moverte", True, (225, 205, 185))
        self.hint2 = self.font_m.render("Flechas · disparar", True, (225, 205, 185))
        self.hint1.set_alpha(150)
        self.hint2.set_alpha(150)

    # ---------- estado ----------
    def reset(self):
        self.player = Player()
        self.state = "playing"
        self.banner = None
        self.shake = 0.0
        self.time = 0.0
        self.fade = 0.0
        self.shoot_stack = []
        self.start_floor(1)

    def start_floor(self, n):
        self.floor = n
        owned = {it[0] for it in self.player.items}
        self.rooms = generate_floor(random.randint(6, 7) if n == 1 else random.randint(7, 8), owned)
        self.room = self.rooms[(0, 0)]
        self.room.visited = True
        self.tears, self.etears, self.particles = [], [], []
        self.player.pos = V2(W / 2, H / 2)
        self.player.vel = V2()
        self.banner = (FLOOR_NAMES[n - 1], "", 2.5)
        self.player.drops = []
        self.fade = 1.0

    # ---------- eventos ----------
    def quit(self):
        pygame.quit()
        sys.exit()

    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.quit()
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.quit()
                elif e.key == pygame.K_p:
                    if self.state == "playing":
                        self.state = "paused"
                    elif self.state == "paused":
                        self.state = "playing"
                elif e.key == pygame.K_r and self.state in ("dead", "win"):
                    self.reset()
                elif e.key in SHOOT_KEYS:
                    self.shoot_stack.append(e.key)
            elif e.type == pygame.KEYUP:
                self.shoot_stack = [k for k in self.shoot_stack if k != e.key]

    def shoot_dir(self):
        keys = pygame.key.get_pressed()
        self.shoot_stack = [k for k in self.shoot_stack if keys[k]]
        for k in SHOOT_KEYS:                       # por si había una tecla ya apretada
            if keys[k] and k not in self.shoot_stack:
                self.shoot_stack.append(k)
        return SHOOT_KEYS[self.shoot_stack[-1]] if self.shoot_stack else None

    # ---------- lógica auxiliar ----------
    def confine(self, e):
        m = e.r
        e.pos.x = max(INNER.left + m, min(INNER.right - m, e.pos.x))
        e.pos.y = max(INNER.top + m, min(INNER.bottom - m, e.pos.y))
        if not e.flying:
            for rock in self.room.rocks:
                push_out(e.pos, e.r, rock)

    def clamp_player(self):
        p, room = self.player, self.room
        r = p.r
        lane = DOOR_W / 2 - r
        open_ = room.cleared
        min_x, max_x = TILE + r, W - TILE - r
        min_y, max_y = TILE + r, H - TILE - r
        # si está metido en un pasillo de puerta, lo mantenemos dentro del carril
        if open_:
            if ("U" in room.doors and p.pos.y < TILE + r) or ("D" in room.doors and p.pos.y > H - TILE - r):
                p.pos.x = max(W / 2 - lane, min(W / 2 + lane, p.pos.x))
            if ("L" in room.doors and p.pos.x < TILE + r) or ("R" in room.doors and p.pos.x > W - TILE - r):
                p.pos.y = max(H / 2 - lane, min(H / 2 + lane, p.pos.y))
            in_h = abs(p.pos.x - W / 2) <= lane
            in_v = abs(p.pos.y - H / 2) <= lane
            if in_h:
                if "U" in room.doors:
                    min_y = -60
                if "D" in room.doors:
                    max_y = H + 60
            if in_v:
                if "L" in room.doors:
                    min_x = -60
                if "R" in room.doors:
                    max_x = W + 60
        p.pos.x = max(min_x, min(max_x, p.pos.x))
        p.pos.y = max(min_y, min(max_y, p.pos.y))

    def try_transition(self):
        p, room = self.player, self.room
        if not room.cleared:
            return False
        go = None
        if p.pos.y < TILE - 10 and "U" in room.doors:
            go = "U"
        elif p.pos.y > H - TILE + 10 and "D" in room.doors:
            go = "D"
        elif p.pos.x < TILE - 10 and "L" in room.doors:
            go = "L"
        elif p.pos.x > W - TILE + 10 and "R" in room.doors:
            go = "R"
        if not go:
            return False
        dx, dy = DIRS[go]
        self.room = self.rooms[(room.pos[0] + dx, room.pos[1] + dy)]
        self.room.visited = True
        self.tears.clear()
        self.etears.clear()
        r = p.r
        if go == "U":
            p.pos = V2(W / 2, H - TILE - r - 6)
        elif go == "D":
            p.pos = V2(W / 2, TILE + r + 6)
        elif go == "L":
            p.pos = V2(W - TILE - r - 6, H / 2)
        else:
            p.pos = V2(TILE + r + 6, H / 2)
        p.vel = V2()
        if not self.room.cleared and not self.room.spawned:
            self.spawn_room()
        return True

    def free_spot(self, min_dist=220):
        spot = V2(W / 2, H / 2)
        for _ in range(80):
            spot = V2(random.uniform(INNER.left + 50, INNER.right - 50), random.uniform(INNER.top + 50, INNER.bottom - 50))
            if (spot - self.player.pos).length() < min_dist:
                continue
            if any(rock.inflate(60, 60).collidepoint(spot.x, spot.y) for rock in self.room.rocks):
                continue
            return spot
        return spot

    def spawn_room(self):
        room = self.room
        room.spawned = True
        if room.kind == "boss":
            boss = Boss((W / 2, H / 2 - 40), self.floor)
            room.enemies = [boss]
            self.banner = (boss.name, "", 2.5)
        else:
            classes = list(random.choice(ENEMY_TEMPLATES))
            if self.floor == 2:                      # el piso 2 trae un enemigo extra y más vida
                classes.append(random.choice([Fly, Gaper, Shooter]))
            room.enemies = [cls(self.free_spot()) for cls in classes]
            if self.floor == 2:
                for e in room.enemies:
                    e.hp *= 1.25

    def clear_room(self):
        room = self.room
        room.cleared = True
        if room.kind == "boss":
            room.trapdoor = True
            room.pickups.append(Pickup("heart", (W / 2 - 90, H / 2 + 80)))
            room.pickups.append(Pickup("heart", (W / 2 + 90, H / 2 + 80)))
        elif random.random() < 0.35:
            room.pickups.append(Pickup("heart", self.free_spot(0)))

    def hurt_player(self, n, src):
        p = self.player
        if p.invuln > 0 or self.state != "playing":
            return
        p.hp -= n
        p.invuln = 1.1
        p.on_hurt()
        self.shake = max(self.shake, 0.15)
        away = p.pos - src
        if away.length() > 1:
            p.vel += away.normalize() * 380
        for _ in range(10):
            a = random.random() * 6.283
            self.particles.append(Particle(p.pos, V2(math.cos(a), math.sin(a)) * random.uniform(60, 220), 0.5, (200, 40, 50), 5))
        if p.hp <= 0:
            p.hp = 0
            self.state = "dead"

    def get_decor(self, room):
        if room.decor is None:
            room.decor = pygame.Surface((W, H), pygame.SRCALPHA)
            build_decor(room.decor, room)
        return room.decor

    def add_blood(self, e):
        """La sangre de los enemigos muertos queda en el piso."""
        surf = self.get_decor(self.room)
        draw_blood(surf, random, int(e.pos.x), int(e.pos.y + e.r * 0.4))
        if isinstance(e, Boss):
            for _ in range(5):
                draw_blood(surf, random, int(e.pos.x + random.uniform(-80, 80)), int(e.pos.y + random.uniform(-50, 60)))

    def pop(self, pos, color, n=5):
        for _ in range(n):
            a = random.random() * 6.283
            self.particles.append(Particle(pos, V2(math.cos(a), math.sin(a)) * random.uniform(40, 150), 0.3, color, 4))

    def fire(self, d):
        p = self.player
        p.eye *= -1
        p.on_shoot()
        perp = V2(-d.y, d.x) * 9 * p.eye
        vel = d * p.tear_speed + p.vel * 0.35
        self.tears.append(Tear(p.pos + perp + d * 8, vel, p.damage, True, p.range_t, 9))

    # ---------- update ----------
    def update(self, dt):
        self.time += dt
        p, room = self.player, self.room
        keys = pygame.key.get_pressed()

        mv = V2(keys[pygame.K_d] - keys[pygame.K_a], keys[pygame.K_s] - keys[pygame.K_w])
        if mv.length_squared() > 0:
            mv = mv.normalize()
        p.vel += (mv * p.speed - p.vel) * min(1, dt * 12)
        p.pos += p.vel * dt
        for rock in room.rocks:
            push_out(p.pos, p.r, rock)
        self.clamp_player()

        if self.try_transition():
            return

        p.cool -= dt
        p.invuln = max(0.0, p.invuln - dt)
        d = self.shoot_dir()
        if d is not None and p.cool <= 0:
            self.fire(d)
            p.cool = p.delay

        # enemigos
        for e in room.enemies:
            e.t += dt
            e.look_at = p.pos
            e.flash = max(0.0, e.flash - dt)
            if e.spawn_t > 0:
                e.spawn_t -= dt
                continue
            e.update(dt, self)
        walkers = [e for e in room.enemies if not e.flying and e.spawn_t <= 0]
        for i in range(len(walkers)):
            for j in range(i + 1, len(walkers)):
                a, b = walkers[i], walkers[j]
                dv = a.pos - b.pos
                dist = dv.length()
                mind = a.r + b.r
                if 0 < dist < mind:
                    push = dv / dist * (mind - dist) / 2
                    a.pos += push
                    b.pos -= push

        # lágrimas
        for t in self.tears:
            t.update(dt, self)
        for t in self.etears:
            t.update(dt, self)
        for t in self.tears:
            if t.dead:
                self.pop(t.pos, (190, 225, 245))
                continue
            for e in room.enemies:
                if e.dead or not e.hittable or e.spawn_t > 0:
                    continue
                if (t.pos - e.pos).length_squared() < (t.r + e.r) ** 2:
                    e.hurt(t.dmg)
                    t.dead = True
                    self.pop(t.pos, (220, 60, 70) if not isinstance(e, Boss) else (230, 120, 130), 4)
                    break
        for t in self.etears:
            if t.dead:
                self.pop(t.pos, (215, 70, 80), 3)
                continue
            if (t.pos - p.pos).length_squared() < (t.r + p.r * 0.7) ** 2:
                self.hurt_player(t.dmg, t.pos)
                t.dead = True
        self.tears = [t for t in self.tears if not t.dead]
        self.etears = [t for t in self.etears if not t.dead]

        # contacto
        for e in room.enemies:
            if e.spawn_t <= 0 and e.touching and (e.pos - p.pos).length() < e.r + p.r * 0.75:
                self.hurt_player(e.contact, e.pos)

        # muertes
        for e in room.enemies:
            if e.dead:
                n = 40 if isinstance(e, Boss) else 10
                for _ in range(n):
                    a = random.random() * 6.283
                    self.particles.append(Particle(e.pos, V2(math.cos(a), math.sin(a)) * random.uniform(50, 300), 0.6, (190, 40, 55), 7))
                self.add_blood(e)
                if isinstance(e, Boss):
                    self.shake = 0.6
        room.enemies = [e for e in room.enemies if not e.dead]
        if room.spawned and not room.enemies and not room.cleared:
            self.clear_room()

        # pickups
        for pk in room.pickups:
            if pk.taken:
                continue
            if (pk.pos - p.pos).length() < 34:
                if pk.kind == "heart" and p.hp < p.max_hp:
                    p.hp = min(p.max_hp, p.hp + 2)
                    pk.taken = True
                elif pk.kind == "item":
                    name, desc, fn, _col = pk.item
                    fn(p)
                    p.items.append(pk.item)
                    pk.taken = True
                    self.banner = (name, desc, 3.0)
        room.pickups = [pk for pk in room.pickups if not (pk.taken and pk.kind == "heart")]

        # trampilla
        if room.trapdoor and (p.pos - V2(W / 2, H / 2)).length() < 38:
            if self.floor >= len(FLOOR_NAMES):
                self.state = "win"
            else:
                p.hp = min(p.max_hp, p.hp + 2)       # un corazón de regalo al bajar
                self.start_floor(self.floor + 1)
            return

        # varios
        for pt in self.particles:
            pt.update(dt)
        self.particles = [pt for pt in self.particles if pt.life > 0]
        self.shake = max(0.0, self.shake - dt)
        self.fade = max(0.0, self.fade - dt * 1.2)
        if self.banner:
            self.banner = (self.banner[0], self.banner[1], self.banner[2] - dt)
            if self.banner[2] <= 0:
                self.banner = None

    # ---------- dibujo ----------
    def draw_doors(self, c):
        room = self.room
        for d in room.doors:
            rect = door_rect(d)
            dx, dy = DIRS[d]
            target = self.rooms[(room.pos[0] + dx, room.pos[1] + dy)]
            frame = (120, 85, 65)
            if target.kind == "boss":
                frame = (190, 45, 45)
            elif target.kind == "treasure":
                frame = (235, 195, 60)
            if room.cleared:
                pygame.draw.rect(c, (14, 8, 6), rect)
            else:
                pygame.draw.rect(c, (96, 64, 44), rect)
                if d in "UD":
                    for x in range(rect.left + 12, rect.right, 24):
                        pygame.draw.line(c, (60, 38, 26), (x, rect.top), (x, rect.bottom), 4)
                else:
                    for y in range(rect.top + 12, rect.bottom, 24):
                        pygame.draw.line(c, (60, 38, 26), (rect.left, y), (rect.right, y), 4)
            pygame.draw.rect(c, frame, rect, 5)

    def draw_rock(self, c, rect):
        pygame.draw.rect(c, (40, 36, 36), rect.move(0, 5), border_radius=14)
        pygame.draw.rect(c, (120, 115, 115), rect, border_radius=14)
        pygame.draw.rect(c, (150, 145, 145), rect.inflate(-20, -24).move(-4, -6), border_radius=10)
        pygame.draw.rect(c, (30, 28, 28), rect, 3, border_radius=14)

    def draw_spawn(self, c, e):
        k = 1 - e.spawn_t / e.spawn_total
        w = int(e.r * 2.4 * k)
        rect = pygame.Rect(int(e.pos.x - w / 2), int(e.pos.y + e.r * 0.5 - w * 0.2), w, int(w * 0.4))
        pygame.draw.ellipse(c, (50, 18, 22), rect)
        pygame.draw.ellipse(c, (150, 45, 55), rect, 3)

    def draw_world(self):
        c = self.canvas
        room = self.room
        c.blit(self.bg, (0, 0))
        c.blit(self.get_decor(room), (0, 0))
        if room.logo and self.logo_floor:
            c.blit(self.logo_floor, self.logo_floor.get_rect(center=room.logo_pos))
            c.blit(self.logo_wall, self.logo_wall.get_rect(center=(TILE * 3, TILE // 2)))
        self.draw_doors(c)

        if room.kind == "start" and self.floor == 1:
            c.blit(self.hint1, self.hint1.get_rect(center=(W // 2, H // 2 - 60)))
            c.blit(self.hint2, self.hint2.get_rect(center=(W // 2, H // 2 - 22)))

        if room.trapdoor:
            pygame.draw.ellipse(c, (70, 50, 40), pygame.Rect(W // 2 - 42, H // 2 - 26, 84, 52))
            pygame.draw.ellipse(c, (8, 5, 5), pygame.Rect(W // 2 - 34, H // 2 - 20, 68, 40))

        for rock in room.rocks:
            self.draw_rock(c, rock)

        for pk in room.pickups:
            bob = math.sin(self.time * 4 + pk.pos.x) * 3
            if pk.kind == "heart":
                pygame.draw.ellipse(c, (35, 28, 24), pygame.Rect(int(pk.pos.x - 11), int(pk.pos.y + 10), 22, 8))
                c.blit(self.h_pick, self.h_pick.get_rect(center=(int(pk.pos.x), int(pk.pos.y + bob))))
            else:
                px, py = int(pk.pos.x), int(pk.pos.y)
                pygame.draw.rect(c, (60, 55, 60), pygame.Rect(px - 30, py + 16, 60, 26), border_radius=4)
                pygame.draw.rect(c, (130, 125, 135), pygame.Rect(px - 30, py + 16, 60, 8), border_radius=4)
                if not pk.taken:
                    iy = int(py - 8 + bob * 2)
                    pygame.draw.circle(c, (245, 235, 205), (px, iy), 34, 2)     # aura
                    draw_item_icon(c, pk.item[3], px, iy, 56)

        ents = room.enemies + [self.player]
        ents.sort(key=lambda e: e.pos.y)
        for e in ents:
            if isinstance(e, Enemy) and e.spawn_t > 0:
                self.draw_spawn(c, e)
                if e.spawn_t < 0.25 and int(self.time * 30) % 2 == 0:
                    e.draw(c, self.time)             # parpadea justo antes de aparecer
            else:
                e.draw(c, self.time)
        for t in self.tears:
            t.draw(c)
        for t in self.etears:
            t.draw(c)
        for pt in self.particles:
            pt.draw(c)

    def draw_minimap(self, x0, y0):
        cw, ch, gap, R = 14, 8, 2, 2
        pw = (2 * R + 1) * (cw + gap) + 4
        ph = (2 * R + 1) * (ch + gap) + 4
        s = self.screen
        pygame.draw.rect(s, (28, 24, 26), pygame.Rect(x0, y0, pw, ph))
        pygame.draw.rect(s, (70, 58, 56), pygame.Rect(x0, y0, pw, ph), 2)
        cx, cy = self.room.pos
        for (rx, ry), room in self.rooms.items():
            dx, dy = rx - cx, ry - cy
            if abs(dx) > R or abs(dy) > R:
                continue
            near_visited = any(
                self.rooms[(rx + ex, ry + ey)].visited for ex, ey in DIRS.values() if (rx + ex, ry + ey) in self.rooms
            )
            if not (room.visited or near_visited):
                continue
            color = (190, 190, 190) if room.visited else (80, 80, 80)
            if room is self.room:
                color = (255, 255, 255)
            elif room.kind == "boss":
                color = (190, 50, 50)
            elif room.kind == "treasure":
                color = (225, 185, 60)
            rect = pygame.Rect(x0 + 2 + (dx + R) * (cw + gap), y0 + 2 + (dy + R) * (ch + gap), cw, ch)
            pygame.draw.rect(s, color, rect)
            pygame.draw.rect(s, (20, 20, 20), rect, 1)

    def draw_hud(self):
        s, p = self.screen, self.player
        pygame.draw.rect(s, (16, 12, 12), pygame.Rect(0, 0, W, HUD_H))
        pygame.draw.line(s, (80, 56, 44), (0, HUD_H - 2), (W, HUD_H - 2), 3)

        # minimapa (izquierda)
        self.draw_minimap(10, 5)

        # contadores: daño / cadencia / velocidad
        rows = [
            ((200, 45, 50), (245, 140, 130), "x%.1f" % p.damage, "DAÑO"),
            ((105, 165, 215), (225, 245, 255), "x%.1f" % (1 / p.delay), "DISPARO"),
            ((100, 190, 90), (210, 250, 190), "x%.1f" % (p.speed / 290), "VELOC."),
        ]
        for i, (c1, c2, txt, label) in enumerate(rows):
            cy = 13 + i * 19
            pygame.draw.circle(s, (10, 8, 8), (136, cy), 9)
            pygame.draw.circle(s, c1, (136, cy), 7)
            pygame.draw.circle(s, c2, (134, cy - 2), 3)
            draw_text(s, self.font_s, txt, (150, cy - 10), (235, 225, 215), center=False)
            draw_text(s, self.font_xs, label, (196, cy - 6), (150, 135, 125), center=False)

        # casilleros de objetos
        items = p.items[-2:]
        for i in range(2):
            box = pygame.Rect(270 + i * 70, 6, 56, 52)
            inner = box.inflate(-6, -6)
            pygame.draw.rect(s, (8, 6, 8), box, border_radius=6)
            pygame.draw.rect(s, (42, 38, 46), inner, border_radius=4)
            pygame.draw.rect(s, (70, 64, 74), inner, 1, border_radius=4)
            if i < len(items):
                draw_item_icon(s, items[i][3], box.centerx, box.centery, 40)
        pygame.draw.rect(s, (6, 5, 6), pygame.Rect(410, 6, 14, 52))
        for k in range(5):
            pygame.draw.rect(s, (46, 42, 48), pygame.Rect(413, 10 + k * 10, 8, 6))

        # piso actual
        if self.logo_hud:
            s.blit(self.logo_hud, (436, 14))
        draw_text(s, self.font_s, FLOOR_NAMES[self.floor - 1], (600, 24), (230, 210, 190))
        draw_text(s, self.font_xs, "PISO %d/%d" % (self.floor, len(FLOOR_NAMES)), (600, 44), (150, 135, 125))

        # vida (derecha)
        n = p.max_hp // 2
        total = n * 31
        x0 = W - 14 - total
        draw_text(s, self.font_s, "-VIDA-", (x0 + total // 2, 11), (205, 45, 45))
        for i in range(n):
            hp_here = p.hp - i * 2
            img = self.h_full if hp_here >= 2 else self.h_half if hp_here == 1 else self.h_empty
            s.blit(img, (x0 + i * 31, 22))

        boss = next((e for e in self.room.enemies if isinstance(e, Boss)), None)
        if boss:
            bw = 360
            x0, y0 = W // 2 - bw // 2, HUD_H + H - 44
            pygame.draw.rect(s, (20, 10, 10), pygame.Rect(x0 - 3, y0 - 3, bw + 6, 20), border_radius=6)
            pygame.draw.rect(s, (190, 40, 50), pygame.Rect(x0, y0, int(bw * max(0, boss.hp) / boss.max_hp), 14), border_radius=5)
            draw_text(s, self.font_s, boss.name, (W // 2, y0 - 16))

        if self.banner:
            draw_text(s, self.font_m, self.banner[0], (W // 2, HUD_H + 100))
            if self.banner[1]:
                draw_text(s, self.font_s, self.banner[1], (W // 2, HUD_H + 130), (240, 220, 160))

    def draw_overlay(self, title, sub, color):
        veil = pygame.Surface((W, H + HUD_H), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 150))
        self.screen.blit(veil, (0, 0))
        cy = HUD_H + H // 2
        draw_text(self.screen, self.font_l, title, (W // 2, cy - 30), color)
        draw_text(self.screen, self.font_m, sub, (W // 2, cy + 40))

    def draw(self):
        self.draw_world()
        ox = oy = 0
        if self.shake > 0:
            ox, oy = random.randint(-5, 5), random.randint(-5, 5)
        self.screen.fill((0, 0, 0))
        self.screen.blit(self.canvas, (ox, HUD_H + oy))
        self.draw_hud()
        if self.fade > 0:
            self.veil.set_alpha(int(255 * min(1.0, self.fade)))
            self.screen.blit(self.veil, (0, 0))
        if self.state == "paused":
            self.draw_overlay("PAUSA", "P para seguir", (255, 255, 255))
        elif self.state == "dead":
            self.draw_overlay("MORISTE", "R para reintentar · ESC para salir", (210, 50, 60))
        elif self.state == "win":
            self.draw_overlay("¡GANASTE!", "Completaste los 2 pisos · R para jugar de nuevo", (240, 210, 90))
        pygame.display.flip()

    # ---------- loop ----------
    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 30)
            self.handle_events()
            if self.state == "playing":
                self.update(dt)
            if self.state != "paused":
                self.player.animate(dt, self.state)
            self.draw()


if __name__ == "__main__":
    Game().run()
