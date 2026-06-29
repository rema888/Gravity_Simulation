"""
Модуль отрисовки (Renderer) — 3D.

Отвечает ТОЛЬКО за рисование. Получает от Simulation (через interface.py)
готовые трёхмерные координаты (x, y, z) и проецирует их на экран.

Используется ортографическая проекция с орбитальной камерой:
- target — точка, на которую смотрит камера (мировые метры);
- yaw, pitch — углы поворота камеры (вращение мышью);
- scale — пикселей на метр (зум).

Базис камеры (right, up, forward) строится из углов; проекция точки P:
    rel = P - target
    sx = cx + dot(rel, right) * scale
    sy = cy - dot(rel, up)    * scale
    depth = dot(rel, forward)   # для сортировки по глубине (painter's algorithm)
"""

import math
import pygame


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(a):
    m = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    if m < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / m, a[1] / m, a[2] / m)


class Renderer:
    """ Отрисовщик 3D-сцены и орбитальная камера. """

    BG_COLOR = (8, 10, 20)
    GRID_COLOR = (26, 30, 48)
    HUD_COLOR = (210, 215, 230)
    VECTOR_COLOR = (90, 220, 160)
    AXIS_COLORS = {"x": (210, 80, 80), "y": (90, 200, 100), "z": (90, 150, 240)}

    PITCH_LIMIT = math.radians(89)

    def __init__(self, screen: pygame.Surface, area: pygame.Rect):
        self.screen = screen
        self.area = area

        # --- Камера ---
        self.target = [0.0, 0.0, 0.0]   # точка взгляда (мир)
        self.yaw = math.radians(-55)    # поворот вокруг вертикали Z
        self.pitch = math.radians(28)   # наклон камеры
        self.scale = 1.0                # пикселей на метр

        # Кэш базиса камеры (пересчитывается при смене углов)
        self._basis_key = None
        self._r = (1.0, 0.0, 0.0)
        self._u = (0.0, 1.0, 0.0)
        self._f = (0.0, 0.0, -1.0)

        pygame.font.init()
        self.font = pygame.font.SysFont("consolas", 16)
        self.small_font = pygame.font.SysFont("consolas", 13)

    # ------------------------------------------------------------------
    # Базис камеры и проекция
    # ------------------------------------------------------------------
    def _ensure_basis(self) -> None:
        key = (self.yaw, self.pitch)
        if key == self._basis_key:
            return
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        # Единичный вектор от цели к камере (камера приподнята на pitch).
        eye_dir = (cp * cy, cp * sy, sp)
        forward = (-eye_dir[0], -eye_dir[1], -eye_dir[2])  # взгляд внутрь сцены
        world_up = (0.0, 0.0, 1.0)
        right = _norm(_cross(forward, world_up))
        up = _cross(right, forward)  # уже единичный (right ⟂ forward)
        self._r, self._u, self._f = right, up, forward
        self._basis_key = key

    def project(self, p):
        """ Точка 3D -> (sx, sy, depth). depth больше => дальше от камеры. """
        self._ensure_basis()
        rel = _sub(p, self.target)
        sx = self.area.centerx + _dot(rel, self._r) * self.scale
        sy = self.area.centery - _dot(rel, self._u) * self.scale
        depth = _dot(rel, self._f)
        return sx, sy, depth

    def world_to_screen(self, x, y, z):
        """ Удобная обёртка: 3D -> (sx, sy) (без глубины). """
        sx, sy, _ = self.project((x, y, z))
        return int(sx), int(sy)

    def screen_to_plane(self, sx, sy, plane_z=0.0):
        """
        Обратная проекция точки экрана на горизонтальную плоскость z = plane_z.
        Нужна для размещения новых тел и расчёта вектора скорости перетаскиванием.
        """
        self._ensure_basis()
        a = (sx - self.area.centerx) / self.scale
        b = (self.area.centery - sy) / self.scale
        r, u, f = self._r, self._u, self._f
        base_z = self.target[2] + a * r[2] + b * u[2]
        if abs(f[2]) < 1e-9:
            d = 0.0  # камера смотрит почти вдоль плоскости — глубину не определить
        else:
            d = (plane_z - base_z) / f[2]
        return (self.target[0] + a * r[0] + b * u[0] + d * f[0],
                self.target[1] + a * r[1] + b * u[1] + d * f[1],
                self.target[2] + a * r[2] + b * u[2] + d * f[2])

    # ------------------------------------------------------------------
    # Управление камерой
    # ------------------------------------------------------------------
    def rotate(self, d_yaw: float, d_pitch: float) -> None:
        self.yaw += d_yaw
        self.pitch = max(-self.PITCH_LIMIT, min(self.PITCH_LIMIT, self.pitch + d_pitch))

    def zoom(self, factor: float, pivot_px=None) -> None:
        self.scale = max(1e-12, min(self.scale * factor, 1e6))

    def pan(self, dx_px: float, dy_px: float) -> None:
        """ Сдвиг камеры в плоскости экрана (перетаскивание средней кнопкой). """
        self._ensure_basis()
        k = 1.0 / self.scale
        for i in range(3):
            self.target[i] += -dx_px * k * self._r[i] + dy_px * k * self._u[i]

    def reset_camera(self) -> None:
        self.yaw = math.radians(-55)
        self.pitch = math.radians(28)

    def fit(self, positions, margin: float = 0.2) -> None:
        """ Подбирает target и scale так, чтобы все тела попали в кадр. """
        if not positions:
            return
        cx = sum(p[0] for p in positions) / len(positions)
        cy = sum(p[1] for p in positions) / len(positions)
        cz = sum(p[2] for p in positions) / len(positions)
        self.target = [cx, cy, cz]

        self._ensure_basis()
        max_a = max_b = 1e-9
        for p in positions:
            rel = _sub(p, self.target)
            max_a = max(max_a, abs(_dot(rel, self._r)))
            max_b = max(max_b, abs(_dot(rel, self._u)))
        half_w = self.area.width * (1 - margin) / 2
        half_h = self.area.height * (1 - margin) / 2
        self.scale = min(half_w / max_a, half_h / max_b)

    # ------------------------------------------------------------------
    # Рисование
    # ------------------------------------------------------------------
    def draw_background(self, show_grid: bool = True) -> None:
        self.screen.set_clip(self.area)
        self.screen.fill(self.BG_COLOR, self.area)
        if show_grid:
            self._draw_grid()
            self._draw_axes()
        self.screen.set_clip(None)

    @staticmethod
    def _nice_step(raw: float) -> float:
        if raw <= 0:
            return 1.0
        exp = math.floor(math.log10(raw))
        base = raw / (10 ** exp)
        nice = 1 if base < 1.5 else 2 if base < 3.5 else 5 if base < 7.5 else 10
        return nice * (10 ** exp)

    def _draw_grid(self) -> None:
        """ Сетка на плоскости z = 0 (главная плоскость орбит). """
        # Углы области, спроецированные на плоскость z=0 -> границы по миру.
        corners = [
            self.screen_to_plane(self.area.left, self.area.top),
            self.screen_to_plane(self.area.right, self.area.top),
            self.screen_to_plane(self.area.left, self.area.bottom),
            self.screen_to_plane(self.area.right, self.area.bottom),
        ]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        world_step = self._nice_step(max(max_x - min_x, max_y - min_y) / 9)
        if world_step <= 0:
            return
        MAX_LINES = 400

        def line3(p1, p2):
            (x1, y1), (x2, y2) = self.world_to_screen(*p1), self.world_to_screen(*p2)
            pygame.draw.line(self.screen, self.GRID_COLOR, (x1, y1), (x2, y2))

        x = math.floor(min_x / world_step) * world_step
        for _ in range(MAX_LINES):
            if x > max_x:
                break
            line3((x, min_y, 0.0), (x, max_y, 0.0))
            x += world_step
        y = math.floor(min_y / world_step) * world_step
        for _ in range(MAX_LINES):
            if y > max_y:
                break
            line3((min_x, y, 0.0), (max_x, y, 0.0))
            y += world_step

        label = f"1 деление = {self._format_distance(world_step)}"
        text = self.small_font.render(label, True, self.HUD_COLOR)
        self.screen.blit(text, (self.area.left + 10, self.area.bottom - 24))

    def _draw_axes(self) -> None:
        """ Оси координат X (красная), Y (зелёная), Z (синяя) из начала координат. """
        length = (min(self.area.width, self.area.height) / self.scale) * 0.4
        origin = self.world_to_screen(0.0, 0.0, 0.0)
        axes = {"x": (length, 0, 0), "y": (0, length, 0), "z": (0, 0, length)}
        for name, vec in axes.items():
            end = self.world_to_screen(*vec)
            pygame.draw.line(self.screen, self.AXIS_COLORS[name], origin, end, 2)
            lbl = self.small_font.render(name.upper(), True, self.AXIS_COLORS[name])
            self.screen.blit(lbl, (end[0] + 3, end[1] - 6))

    def draw_trails(self, trails, colors) -> None:
        self.screen.set_clip(self.area)
        for i, trail in enumerate(trails):
            if len(trail) < 2:
                continue
            color = colors[i % len(colors)]
            faded = tuple(int(c * 0.55) for c in color)
            points = [self.world_to_screen(*p) for p in trail]
            pygame.draw.aalines(self.screen, faded, False, points)
        self.screen.set_clip(None)

    def draw_velocity_vectors(self, positions, velocities, colors) -> None:
        """ 3D-векторы скорости. Длина нормирована по самой быстрой точке. """
        if not velocities:
            return
        max_speed = max((math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) for v in velocities),
                        default=0.0)
        if max_speed < 1e-9:
            return
        # самая быстрая стрелка ~ 55 px => мировая длина 55/scale
        k = (55.0 / self.scale) / max_speed

        self.screen.set_clip(self.area)
        for pos, vel in zip(positions, velocities):
            speed = math.sqrt(vel[0] ** 2 + vel[1] ** 2 + vel[2] ** 2)
            if speed < 1e-9:
                continue
            end_world = (pos[0] + vel[0] * k, pos[1] + vel[1] * k, pos[2] + vel[2] * k)
            p0 = self.world_to_screen(*pos)
            p1 = self.world_to_screen(*end_world)
            pygame.draw.line(self.screen, self.VECTOR_COLOR, p0, p1, 2)
            self._draw_arrowhead(p0, p1)
        self.screen.set_clip(None)

    def _draw_arrowhead(self, start, end) -> None:
        ang = math.atan2(end[1] - start[1], end[0] - start[0])
        size = 7
        for da in (math.radians(150), math.radians(-150)):
            x = end[0] + size * math.cos(ang + da)
            y = end[1] + size * math.sin(ang + da)
            pygame.draw.line(self.screen, self.VECTOR_COLOR, end, (x, y), 2)

    def draw_bodies(self, positions, colors, radii) -> None:
        """ Тела как кружки фикс. радиуса; рисуем от дальних к ближним (по глубине). """
        self.screen.set_clip(self.area)
        order = sorted(range(len(positions)),
                       key=lambda i: self.project(positions[i])[2], reverse=True)
        for i in order:
            sx, sy = self.world_to_screen(*positions[i])
            color = colors[i % len(colors)]
            r = radii[i % len(radii)]
            glow = tuple(int(c * 0.35) for c in color)
            pygame.draw.circle(self.screen, glow, (sx, sy), r + 4)
            pygame.draw.circle(self.screen, color, (sx, sy), r)
            pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), max(1, r // 3))
        self.screen.set_clip(None)

    def draw_new_body_preview(self, start_px, cur_px, radius, color) -> None:
        self.screen.set_clip(self.area)
        pygame.draw.circle(self.screen, color, start_px, radius)
        pygame.draw.circle(self.screen, (255, 255, 255), start_px, radius, 1)
        if (cur_px[0] - start_px[0]) ** 2 + (cur_px[1] - start_px[1]) ** 2 > 9:
            pygame.draw.line(self.screen, self.VECTOR_COLOR, start_px, cur_px, 2)
            self._draw_arrowhead(start_px, cur_px)
        self.screen.set_clip(None)

    def draw_hud(self, lines) -> None:
        x = self.area.left + 12
        y = self.area.top + 10
        for line in lines:
            surf = self.font.render(line, True, self.HUD_COLOR)
            bg = pygame.Surface((surf.get_width() + 8, surf.get_height() + 2), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 110))
            self.screen.blit(bg, (x - 4, y - 1))
            self.screen.blit(surf, (x, y))
            y += surf.get_height() + 4

    @staticmethod
    def _format_distance(meters: float) -> str:
        AU = 1.496e11
        if meters >= 0.1 * AU:
            return f"{meters / AU:.2f} а.е."
        if meters >= 1e9:
            return f"{meters / 1e9:.2f} млн км"
        if meters >= 1e3:
            return f"{meters / 1e3:.0f} км"
        return f"{meters:.0f} м"
