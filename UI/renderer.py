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
import random

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


def _rand_sphere_dir(rng):
    """ Случайное равномерно распределённое направление на единичной сфере (не кучкуется у полюсов). """
    z = rng.uniform(-1, 1)
    theta = rng.uniform(0, math.tau)
    rxy = math.sqrt(max(0.0, 1 - z * z))
    return (rxy * math.cos(theta), rxy * math.sin(theta), z)


def _perturb_dir(base_dir, spread, rng):
    """ Случайное направление в пределах углового «spread» вокруг base_dir (для скоплений звёзд). """
    d = base_dir
    helper = (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 else (1.0, 0.0, 0.0)
    t1 = _norm(_cross(d, helper))
    t2 = _cross(d, t1)
    ang = rng.uniform(0, math.tau)
    dist = spread * math.sqrt(rng.random())  # гуще к центру, чем к краю
    ox, oy = dist * math.cos(ang), dist * math.sin(ang)
    v = (d[0] + t1[0] * ox + t2[0] * oy,
         d[1] + t1[1] * ox + t2[1] * oy,
         d[2] + t1[2] * ox + t2[2] * oy)
    return _norm(v)


class Renderer:
    """ Отрисовщик 3D-сцены и орбитальная камера. """

    BG_COLOR = (8, 10, 20)
    VIGNETTE_INNER = (18, 22, 42)   # чуть светлее и синее ближе к центру кадра
    VIGNETTE_OUTER = (3, 4, 9)      # почти чёрный к краям — глубина космоса
    GRID_COLOR = (26, 30, 48)
    HUD_COLOR = (210, 215, 230)
    VECTOR_COLOR = (90, 220, 160)
    AXIS_COLORS = {"x": (210, 80, 80), "y": (90, 200, 100), "z": (90, 150, 240)}

    PITCH_LIMIT = math.radians(89)

    # «Радиус небесной сферы» в экранных пикселях — звёзды рисуются по направлению
    # от камеры на эту фиксированную дистанцию, не зависящую от zoom (как и положено
    # бесконечно далёким звёздам). Значение подобрано так, чтобы в кадре был виден
    # разумно широкий кусок неба (слишком большой радиус сужает обзор до нескольких
    # градусов и звёзды почти не видны).
    SKY_RADIUS_PX = 850

    def __init__(self, screen: pygame.Surface, area: pygame.Rect):
        self.screen = screen
        self.area = area

        # --- Камера ---
        self.target = [0.0, 0.0, 0.0]   # точка взгляда (мир)
        self.yaw = math.radians(-55)    # поворот вокруг вертикали Z
        self.pitch = math.radians(28)   # наклон камеры
        self.scale = 1.0                # пикселей на метр
        self.reference_scale = 1.0      # масштаб на момент последнего «кадрирования»
                                        # (fit/смена сценария) — точка отсчёта для
                                        # лёгкого роста/уменьшения тел при зуме

        # Кэш базиса камеры (пересчитывается при смене углов)
        self._basis_key = None
        self._r = (1.0, 0.0, 0.0)
        self._u = (0.0, 1.0, 0.0)
        self._f = (0.0, 0.0, -1.0)

        pygame.font.init()
        self.font = pygame.font.SysFont("consolas", 16)
        self.small_font = pygame.font.SysFont("consolas", 13)

        # --- Космический фон: строится один раз и переиспользуется каждый кадр ---
        # Туманности строятся первыми — звёздному полю нужны их направления,
        # чтобы сгустить звёзды вокруг них (как скопления молодых звёзд в
        # реальных областях звездообразования).
        self._vignette = self._build_vignette()
        self._nebula = self._generate_nebula()
        self._stars = self._generate_starfield(self._nebula)

        # --- Кэш «спрайтов» тел (текстура планеты/звезды), чтобы не пересчитывать каждый кадр ---
        self._sprite_cache: dict[int, tuple] = {}

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

    # При сильном зуме (большой scale) спроецированные координаты далёких точек
    # (например, начала координат для осей) могут выйти за пределы, которые
    # понимает SDL — pygame тогда падает с TypeError. Обрезаем координату
    # заведомо далёким, но безопасным значением: экран всё равно только
    # ~1000 px, так что «далеко за кадром» можно не считать точно.
    _SAFE_COORD = 100_000

    def world_to_screen(self, x, y, z):
        """ Удобная обёртка: 3D -> (sx, sy) (без глубины). """
        sx, sy, _ = self.project((x, y, z))
        if not (math.isfinite(sx) and math.isfinite(sy)):
            return 0, 0
        sx = max(-self._SAFE_COORD, min(self._SAFE_COORD, sx))
        sy = max(-self._SAFE_COORD, min(self._SAFE_COORD, sy))
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

    def effective_radius(self, base_radius: int) -> int:
        """
        Пиксельный радиус тела с поправкой на текущий зум относительно
        «эталонного» масштаба (того, что был при последнем кадрировании сцены).
        Рост/уменьшение всегда мягкое и ограниченное (степень 0.22 от отношения
        масштабов, зажатая в [0.55, 2.2]) — тело чуть увеличивается, когда вы
        приближаетесь к нему вплотную, но не «раздувается» до абсурда.
        """
        ratio = self.scale / max(self.reference_scale, 1e-300)
        factor = ratio ** 0.22
        factor = max(0.55, min(2.2, factor))
        return int(max(3, round(base_radius * factor)))

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
        self.reference_scale = self.scale

    # ------------------------------------------------------------------
    # Космический фон (виньетка, туманности, звёзды)
    # ------------------------------------------------------------------
    def _build_vignette(self):
        """ Мягкий радиальный градиент фона вместо плоской заливки — придаёт глубину. """
        surf = pygame.Surface((self.area.width, self.area.height))
        cx, cy = self.area.width / 2, self.area.height / 2
        max_r = math.hypot(cx, cy)
        steps = 32
        outer, inner = self.VIGNETTE_OUTER, self.VIGNETTE_INNER
        for i in range(steps, 0, -1):
            f = i / steps
            color = tuple(int(outer[k] * f + inner[k] * (1 - f)) for k in range(3))
            pygame.draw.circle(surf, color, (int(cx), int(cy)), int(max_r * f))
        return surf

    # Спектральные классы звёзд (грубая имитация): доля, множители R/G/B поверх
    # случайной яркости — даёт настоящее цветовое разнообразие, а не просто
    # «теплее/холоднее» один и тот же белый.
    _STAR_CLASSES = [
        (0.12, (0.78, 0.86, 1.15)),   # голубовато-белые (горячие)
        (0.45, (1.00, 1.00, 1.00)),   # белые
        (0.22, (1.05, 1.00, 0.78)),   # жёлтые
        (0.15, (1.15, 0.88, 0.58)),   # оранжевые
        (0.06, (1.20, 0.62, 0.52)),   # красноватые (холодные)
    ]

    @classmethod
    def _pick_star_color(cls, rng, lo=90, hi=255):
        roll = rng.random()
        acc = 0.0
        tint = cls._STAR_CLASSES[-1][1]
        for weight, t in cls._STAR_CLASSES:
            acc += weight
            if roll <= acc:
                tint = t
                break
        brightness = rng.uniform(lo, hi)
        return tuple(max(0, min(255, int(brightness * k))) for k in tint)

    def _generate_starfield(self, nebula_blobs=None):
        """
        Звёзды заданы не экранными координатами, а направлениями на воображаемой
        небесной сфере вокруг камеры (как настоящий скайбокс) — при вращении
        камеры они «едут» по экрану вместе с поворотом, а не стоят на месте.
        Сид фиксирован, так что узор неба не меняется между кадрами и запусками.
        """
        rng = random.Random(20260701)
        stars = []

        def add_star(direction, r, color, bright=False):
            stars.append({
                "dir": direction, "r": r, "color": color, "bright": bright,
                "phase": rng.uniform(0, math.tau), "speed": rng.uniform(0.3, 1.2),
            })

        # обычные звёзды — равномерно по всей небесной сфере, с цветовым разнообразием.
        # Яркость берём не из равномерного распределения, а с перекосом в пользу тусклых
        # (степень >1) — на настоящем небе ярких звёзд немного, тусклых много, и именно
        # этот перекос создаёт неоднородность, а не ровный «шум».
        for _ in range(300):
            r = 2 if rng.random() < 0.06 else 1
            lo, hi = 70, 255
            brightness = lo + (hi - lo) * rng.random() ** 1.8
            add_star(_rand_sphere_dir(rng), r, self._tinted(rng, brightness))

        # тусклая полоса вроде «Млечного Пути» вдоль наклонного большого круга —
        # для разнообразия неба вместо равномерной россыпи точек
        tilt = math.radians(35)
        band_u = (1.0, 0.0, 0.0)
        band_v = (0.0, math.cos(tilt), math.sin(tilt))
        for _ in range(170):
            t = rng.uniform(0, math.tau)
            spread = rng.gauss(0, 0.10)  # небольшая толщина полосы
            d = (
                math.cos(t) * band_u[0] + math.sin(t) * band_v[0],
                math.cos(t) * band_u[1] + math.sin(t) * band_v[1] + spread,
                math.cos(t) * band_u[2] + math.sin(t) * band_v[2] + spread,
            )
            m = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2) or 1.0
            add_star((d[0] / m, d[1] / m, d[2] / m), 1, self._pick_star_color(rng, 50, 150))

        # яркие «приметные» звёзды со сверкающим крестом-бликом (голубовато-белые,
        # как настоящие сверхгиганты вроде Веги или Сириуса)
        for _ in range(12):
            tint = rng.choice([(0.85, 0.9, 1.15), (1.0, 1.0, 1.0), (1.05, 1.0, 0.85)])
            brightness = rng.uniform(232, 255)
            color = tuple(max(0, min(255, int(brightness * k))) for k in tint)
            add_star(_rand_sphere_dir(rng), 2, color, bright=True)

        # сгущаем звёзды вокруг туманностей и галактик — как настоящие скопления
        # молодых горячих звёзд в областях звездообразования. Заметно плотнее фона
        # и заметно ярче в среднем — именно это и делает эти участки неба «живыми»,
        # а не одинаковой по яркости россыпью точек.
        for blob in nebula_blobs or []:
            radius_px = blob.get("radius_px", 150)
            spread = min(0.9, (radius_px * 2.0) / self.SKY_RADIUS_PX)
            count = max(70, int(radius_px * 0.9))
            for _ in range(count):
                d = _perturb_dir(blob["dir"], spread, rng)
                if rng.random() < 0.18:
                    tint = rng.choice([(0.82, 0.88, 1.15), (1.0, 1.0, 1.0), (1.1, 1.0, 0.8)])
                    brightness = rng.uniform(215, 255)
                    color = tuple(max(0, min(255, int(brightness * k))) for k in tint)
                    add_star(d, 2, color, bright=True)
                else:
                    r = 2 if rng.random() < 0.25 else 1
                    add_star(d, r, self._pick_star_color(rng, 120, 255))

        return stars

    @classmethod
    def _tinted(cls, rng, brightness):
        """ Применяет случайный спектральный класс к уже выбранной яркости. """
        roll = rng.random()
        acc = 0.0
        tint = cls._STAR_CLASSES[-1][1]
        for weight, t in cls._STAR_CLASSES:
            acc += weight
            if roll <= acc:
                tint = t
                break
        return tuple(max(0, min(255, int(brightness * k))) for k in tint)

    # Палитры газовых туманностей — навеяны реальными снимками (Ориона, Орла,
    # Киля, планетарных туманностей): у каждой контрастная «горячая» и «холодная»
    # составляющая плюс светлый акцент для яркого ядра.
    _NEBULA_PALETTES = [
        [(210, 60, 70), (235, 120, 60), (255, 200, 140)],    # эмиссионная, красно-золотая (Орион/Орёл)
        [(70, 90, 190), (110, 160, 230), (200, 225, 255)],   # отражательная, синяя
        [(60, 175, 150), (150, 90, 195), (220, 170, 230)],   # планетарная, бирюзово-пурпурная
        [(190, 90, 150), (230, 150, 90), (255, 210, 150)],   # тёплая розово-золотая (Киль)
        [(120, 70, 170), (170, 110, 210), (210, 170, 235)],  # туманность-облако, фиолетовая
    ]

    def _build_nebula_sprite(self, radius_px: float, seed: int):
        """
        Клочковатое облако газа: россыпь мазков вокруг нескольких смещённых
        «лепестков» (гуще к центру каждого, реже к краю) — так силуэт получается
        неправильной, рваной формы, а не одним ровным кругом. Строится ДВУМЯ
        независимыми проходами, наложенными друг на друга — как будто слились
        две туманности — так текстура выходит плотнее и разнообразнее, чем
        от одного прохода. Рисуется в полном разрешении, а затем размывается
        настоящим гауссовым блюром — именно это убирает жёсткие края кружков
        и даёт волокнистый, туманный вид вместо «мыльных пузырей». Плюс яркий
        узелок звёздообразования, тёмные пылевые прожилки и щепотка ярких
        точек — звёздное скопление, запутавшееся в газе.
        """
        rng = random.Random(seed)
        palette = rng.choice(self._NEBULA_PALETTES)
        pad = int(radius_px * 0.6) + 20
        size = int(radius_px * 3.0) + 2 * pad
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size / 2

        def scatter(cx0, cy0, count, spread, radius_range, alpha_range, colors):
            for _ in range(count):
                color = rng.choice(colors)
                ang = rng.uniform(0, math.tau)
                dist = spread * math.sqrt(rng.random())
                x = cx0 + dist * math.cos(ang)
                y = cy0 + dist * math.sin(ang)
                r = max(1, int(rng.uniform(*radius_range)))
                alpha = int(rng.uniform(*alpha_range))
                pygame.draw.circle(surf, (*color, alpha), (int(x), int(y)), r)

        bright = tuple(min(255, int(ch * 1.3) + 25) for ch in palette[-1])

        def cloud_pass(lobe_range, knot_range):
            """
            Один независимый проход: свой набор смещённых «лепестков» (силуэт
            облака) и ярких узлов-сгустков. Альфа мазков разбросана широко
            (не узкий диапазон) — это уже само по себе даёт неровную яркость,
            а не «ровный шум» одной интенсивности.
            """
            centers = []
            for _ in range(rng.randint(*lobe_range)):
                lang = rng.uniform(0, math.tau)
                ldist = rng.uniform(0, radius_px * 0.55)
                lx, ly = c + ldist * math.cos(lang), c + ldist * math.sin(lang)
                centers.append((lx, ly))
                scatter(lx, ly, rng.randint(70, 110), radius_px * 0.5,
                       (radius_px * 0.05, radius_px * 0.14), (12, 40), palette)

            # яркие сгустки-«узлы» звёздообразования — рисуем ДО размытия, теми же
            # мазками, что и остальное облако, просто плотнее и ярче. После общего
            # гауссова блюра они сливаются с газом мягкими краями, а не остаются
            # отдельными резкими шариками поверх текстуры.
            for _ in range(rng.randint(*knot_range)):
                # узлы чаще возле центров лепестков — там, где и так гуще газ
                klx, kly = rng.choice(centers)
                kang = rng.uniform(0, math.tau)
                kdist = rng.uniform(0, radius_px * 0.35)
                kx, ky = klx + kdist * math.cos(kang), kly + kdist * math.sin(kang)
                scatter(kx, ky, rng.randint(30, 55), radius_px * 0.16,
                       (radius_px * 0.03, radius_px * 0.08), (45, 100), [bright])
            return centers

        # два независимых прохода наложены друг на друга — плотнее и разнообразнее,
        # чем один проход; настоящие протяжённые облака газа редко имеют одну
        # простую форму, а выглядят как слияние нескольких клочковатых масс.
        lobe_centers = cloud_pass((3, 5), (2, 3))
        lobe_centers += cloud_pass((2, 4), (1, 3))

        # главный узелок — самая яркая точка облака, тоже ДО размытия
        core_ang = rng.uniform(0, math.tau)
        core_dist = rng.uniform(0, radius_px * 0.15)
        ccx = c + core_dist * math.cos(core_ang)
        ccy = c + core_dist * math.sin(core_ang)
        for i in range(10, 0, -1):
            f = i / 10
            rr = max(1, int(radius_px * 0.18 * f))
            alpha = int(30 + 95 * (1 - f))
            pygame.draw.circle(surf, (*bright, alpha), (int(ccx), int(ccy)), rr)
        scatter(ccx, ccy, 40, radius_px * 0.22,
               (radius_px * 0.02, radius_px * 0.05), (35, 65), [bright])

        # тёмные пылевые прожилки — фирменный контраст настоящих туманностей
        dust = (max(0, palette[0][0] // 6), max(0, palette[0][1] // 6), max(0, palette[0][2] // 5))
        for _ in range(rng.randint(3, 5)):
            dang = rng.uniform(0, math.tau)
            ddist = rng.uniform(0, radius_px * 0.4)
            dx_, dy_ = c + ddist * math.cos(dang), c + ddist * math.sin(dang)
            scatter(dx_, dy_, rng.randint(25, 40), radius_px * 0.22,
                   (radius_px * 0.03, radius_px * 0.07), (45, 80), [dust])

        # настоящее гауссово размытие — вот тут все мазки (и яркие узлы, и пыль,
        # и основной газ) сливаются в один непрерывный дым с неровной яркостью
        surf = pygame.transform.gaussian_blur(surf, max(2, int(radius_px * 0.05)))

        # щепотка ярких точек рисуем ПОСЛЕ размытия, поверх, чтобы звёзды скопления
        # остались чёткими, а не размылись вместе с газом
        for _ in range(rng.randint(5, 9)):
            sx_ = ccx + rng.uniform(-radius_px * 0.25, radius_px * 0.25)
            sy_ = ccy + rng.uniform(-radius_px * 0.25, radius_px * 0.25)
            pygame.draw.circle(surf, (255, 255, 255, rng.randint(140, 220)),
                               (int(sx_), int(sy_)), 1)

        return surf

    def _build_galaxy_sprite(self, radius_px: float, seed: int):
        """ Далёкая галактика: сплюснутое светящееся гало со спиральным ядром, видна почти с ребра. """
        rng = random.Random(seed)
        elongate = rng.uniform(2.4, 3.6)
        pad = int(radius_px * 0.5) + 16
        w = int(radius_px * 2.6 * elongate) + 2 * pad
        h = int(radius_px * 2.6) + 2 * pad
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = w // 2, h // 2
        core_color = rng.choice([(235, 220, 195), (225, 205, 230), (255, 235, 205)])
        halo_color = tuple(int(ch * 0.55) for ch in core_color)

        # сплюснутое гало
        layers = 18
        for i in range(layers, 0, -1):
            f = i / layers
            rw = max(1, int(radius_px * elongate * f))
            rh = max(1, int(radius_px * f * 0.34))
            alpha = int(8 + 50 * (1 - f) ** 1.3)
            pygame.draw.ellipse(surf, (*halo_color, alpha), (cx - rw, cy - rh, rw * 2, rh * 2))

        # мелкая рябь пыли вдоль диска — намёк на спиральные рукава, широкий разброс
        # альфы (не узкий диапазон) уже даёт неровную яркость по длине диска
        for _ in range(rng.randint(14, 22)):
            t = rng.uniform(-1, 1)
            dx = t * radius_px * elongate * 0.8
            dy = math.sin(t * math.pi) * radius_px * 0.12 * rng.choice([-1, 1])
            r = rng.uniform(radius_px * 0.08, radius_px * 0.18)
            alpha = rng.randint(8, 30)
            pygame.draw.circle(surf, (*halo_color, alpha), (int(cx + dx), int(cy + dy)), max(1, int(r)))

        # яркие узлы звёздообразования вдоль рукавов — рисуем ДО размытия, теми же
        # мягкими мазками, что и остальной диск, просто плотнее и ярче. После
        # общего блюра они сливаются с гало, а не остаются резкими шариками сверху.
        for _ in range(rng.randint(2, 4)):
            t = rng.uniform(-0.85, 0.85)
            kx = cx + t * radius_px * elongate * 0.8
            ky = cy + math.sin(t * math.pi) * radius_px * 0.12 * rng.choice([-1, 1])
            for _ in range(rng.randint(10, 18)):
                ang = rng.uniform(0, math.tau)
                dist = radius_px * 0.09 * math.sqrt(rng.random())
                rr = max(1, int(radius_px * rng.uniform(0.02, 0.05)))
                alpha = int(rng.uniform(30, 70))
                pygame.draw.circle(surf, (*core_color, alpha),
                                   (int(kx + dist * math.cos(ang)), int(ky + dist * math.sin(ang))), rr)

        # настоящее гауссово размытие — гало, рукава и яркие узлы сливаются в один
        # мягкий диск с неровной яркостью, без «зубцов» и без отдельных шариков
        surf = pygame.transform.gaussian_blur(surf, max(2, int(radius_px * 0.05)))

        # яркое ядро рисуем поверх уже размытой картинки — оно единственное,
        # что должно остаться по-настоящему резким (звёздное ядро галактики)
        for i in range(10, 0, -1):
            f = i / 10
            r = max(1, int(radius_px * 0.24 * f))
            alpha = int(20 + 90 * (1 - f))
            pygame.draw.circle(surf, (*core_color, alpha), (cx, cy), r)

        return pygame.transform.rotate(surf, rng.uniform(0, 360))

    def _generate_nebula(self):
        """
        Несколько глубоких «объектов неба» — газовых туманностей и далёких
        галактик — направления на той же небесной сфере, что и звёзды, так
        что вращаются вместе с ней при повороте камеры. Текстура каждого
        объекта строится один раз при старте, дальше только перемещается.

        Сид НЕ фиксирован (в отличие от звёзд): расположение, размер и
        внешний вид туманностей/галактик каждый раз новые при запуске
        приложения — иначе они бы всегда оказывались в одних и тех же
        местах неба. Стабильность в течение одной сессии обеспечивается
        тем, что _generate_nebula() вызывается только один раз, при
        создании Renderer.
        """
        rng = random.Random()
        blobs = []
        for _ in range(3):
            radius_px = rng.uniform(170, 300)
            blobs.append({
                "dir": _rand_sphere_dir(rng),
                "sprite": self._build_nebula_sprite(radius_px, seed=rng.randrange(1_000_000)),
                "radius_px": radius_px,
            })
        for _ in range(3):
            radius_px = rng.uniform(90, 160)
            blobs.append({
                "dir": _rand_sphere_dir(rng),
                "sprite": self._build_galaxy_sprite(radius_px, seed=rng.randrange(1_000_000)),
                "radius_px": radius_px,
            })
        return blobs

    def _draw_nebula(self) -> None:
        """ Проецирует центр каждого блоба туманности через базис камеры (та же логика, что у звёзд). """
        self._ensure_basis()
        cx, cy = self.area.center
        r, u, f = self._r, self._u, self._f
        for blob in self._nebula:
            dx, dy, dz = blob["dir"]
            depth = dx * f[0] + dy * f[1] + dz * f[2]
            if depth <= -0.1:
                continue  # туманность позади камеры — не рисуем
            sx = cx + (dx * r[0] + dy * r[1] + dz * r[2]) * self.SKY_RADIUS_PX
            sy = cy - (dx * u[0] + dy * u[1] + dz * u[2]) * self.SKY_RADIUS_PX
            sprite = blob["sprite"]
            rect = sprite.get_rect(center=(int(sx), int(sy)))
            if not self.area.colliderect(rect):
                continue
            self.screen.blit(sprite, rect)

    def _draw_stars(self, frame: int) -> None:
        """
        Проецирует каждую звезду по её направлению через ТЕКУЩИЙ базис камеры
        (right/up/forward), но без учёта target и scale — звёзды «бесконечно
        далеко», поэтому не сдвигаются при панораме и зуме, только при повороте
        камеры (ровно как небесная сфера в настоящем скайбоксе).
        """
        self._ensure_basis()
        t = frame * 0.05
        cx, cy = self.area.center
        r, u, f = self._r, self._u, self._f
        for s in self._stars:
            dx, dy, dz = s["dir"]
            depth = dx * f[0] + dy * f[1] + dz * f[2]
            if depth <= 0.05:
                continue  # звезда «за спиной» камеры — не рисуем, как за горизонтом
            sx = cx + (dx * r[0] + dy * r[1] + dz * r[2]) * self.SKY_RADIUS_PX
            sy = cy - (dx * u[0] + dy * u[1] + dz * u[2]) * self.SKY_RADIUS_PX
            if not self.area.collidepoint(sx, sy):
                continue
            twinkle = 0.75 + 0.25 * math.sin(t * s["speed"] + s["phase"])
            color = tuple(max(0, min(255, int(ch * twinkle))) for ch in s["color"])
            isx, isy = int(sx), int(sy)
            pygame.draw.circle(self.screen, color, (isx, isy), s["r"])
            if s["bright"]:
                # мерцающий крест-блик — как диафрагменные лучи у ярких звёзд на фото
                spike = 3 + int(2 * twinkle)
                pygame.draw.line(self.screen, color, (isx - spike, isy), (isx + spike, isy))
                pygame.draw.line(self.screen, color, (isx, isy - spike), (isx, isy + spike))

    # ------------------------------------------------------------------
    # Рисование
    # ------------------------------------------------------------------
    def draw_background(self, show_grid: bool = True, frame: int = 0) -> None:
        self.screen.set_clip(self.area)
        self.screen.blit(self._vignette, self.area.topleft)
        self._draw_nebula()
        self._draw_stars(frame)
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

    def clear_sprite_cache(self) -> None:
        """ Сбрасывает кэш текстур тел (вызывается при загрузке сценария/очистке сцены). """
        self._sprite_cache.clear()

    def _get_body_sprite(self, seed: int, radius: int, color, is_star: bool):
        """ Берёт готовую текстуру тела из кэша или строит новую, если параметры изменились. """
        key = (radius, color, is_star)
        cached = self._sprite_cache.get(seed)
        if cached is not None and cached[0] == key:
            return cached[1]
        sprite = self._build_star_sprite(radius, color, seed) if is_star \
            else self._build_planet_sprite(radius, color, seed)
        self._sprite_cache[seed] = (key, sprite)
        return sprite

    def _build_planet_sprite(self, radius: int, color, seed: int):
        """ Затенённый шар со случайными пятнами и, иногда, кольцом — своё для каждого тела. """
        size = int(radius * 2.8) + 8
        c = size // 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        rng = random.Random(seed * 2654435761 % (2 ** 32))

        # кольцо рисуем первым — сфера потом перекроет середину, оставив «ушки» по бокам
        if radius >= 7 and rng.random() < 0.45:
            ring_color = tuple(min(255, int(ch * 0.9) + 20) for ch in color)
            rw, rh = int(radius * 2.6), int(radius * 0.85)
            pygame.draw.ellipse(surf, (*ring_color, 120),
                                (c - rw // 2, c - rh // 2, rw, rh), width=max(1, radius // 5))

        # лимб-дарк: край темнее, середина светлее — дешёвая имитация объёма.
        # Шагов побольше, чтобы переход был плавным, а не «луковичными кольцами».
        steps = max(radius, 14)
        for i in range(steps, 0, -1):
            f = i / steps
            r = max(1, int(radius * f))
            tone = 0.55 + 0.65 * (1 - f)
            shaded = tuple(max(0, min(255, int(ch * tone))) for ch in color)
            pygame.draw.circle(surf, shaded, (c, c), r)

        # случайные пятна — материки/кратеры, гарантированно не вылезают за диск
        dark = tuple(max(0, int(ch * 0.55)) for ch in color)
        light = tuple(min(255, int(ch * 1.35) + 12) for ch in color)
        for _ in range(rng.randint(3, 6)):
            ang = rng.uniform(0, math.tau)
            dist = rng.uniform(0, radius * 0.45)
            ox, oy = c + dist * math.cos(ang), c + dist * math.sin(ang)
            spot_r = max(1, int(rng.uniform(radius * 0.15, radius * 0.32)))
            tone = dark if rng.random() < 0.55 else light
            pygame.draw.circle(surf, tone, (int(ox), int(oy)), spot_r)

        # маленький блик со стороны «света»
        hd = radius * 0.42
        hx, hy = c - hd * 0.7, c - hd * 0.7
        pygame.draw.circle(surf, (255, 255, 255, 90), (int(hx), int(hy)), max(1, int(radius * 0.22)))

        return surf

    def _build_star_sprite(self, radius: int, color, seed: int):
        """ Светящееся ядро с компактным ореолом и парой бликов-лучей — для массивных тел. """
        # ореол доходит до radius*2.4 (i=4 в цикле ниже) — поверхность должна быть
        # немного больше, иначе он обрежется квадратными краями surface
        size = int(radius * 6) + 8
        c = size // 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        rng = random.Random(seed * 2654435761 % (2 ** 32))
        glow_color = tuple(min(255, int(ch * 1.1) + 25) for ch in color)

        # мягкое свечение вокруг ядра — компактное, чтобы не забивать всю сцену
        for i in range(4, 0, -1):
            r = int(radius * (1 + i * 0.35))
            alpha = 10 + i * 9
            pygame.draw.circle(surf, (*glow_color, alpha), (c, c), r)

        # яркое ядро, светлеющее к центру
        for i in range(4, 0, -1):
            f = i / 4
            r = max(1, int(radius * f))
            tone = tuple(min(255, int(ch + (255 - ch) * (1 - f) * 0.85)) for ch in color)
            pygame.draw.circle(surf, (*tone, 255), (c, c), r)

        # тонкие лучи — как блик объектива
        for _ in range(rng.randint(4, 6)):
            ang = rng.uniform(0, math.tau)
            length = radius * rng.uniform(1.3, 2.0)
            ex, ey = c + length * math.cos(ang), c + length * math.sin(ang)
            pygame.draw.line(surf, (*glow_color, 60), (c, c), (int(ex), int(ey)), 1)

        return surf

    def draw_bodies(self, positions, colors, radii, seeds, is_star) -> None:
        """ Тела как текстурированные шары/звёзды; рисуем от дальних к ближним (по глубине). """
        self.screen.set_clip(self.area)
        order = sorted(range(len(positions)),
                       key=lambda i: self.project(positions[i])[2], reverse=True)
        for i in order:
            sx, sy = self.world_to_screen(*positions[i])
            color = colors[i % len(colors)]
            radius = self.effective_radius(radii[i % len(radii)])
            seed = seeds[i] if i < len(seeds) else i
            star = is_star[i] if i < len(is_star) else False
            sprite = self._get_body_sprite(seed, radius, color, star)
            self.screen.blit(sprite, sprite.get_rect(center=(sx, sy)))
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
