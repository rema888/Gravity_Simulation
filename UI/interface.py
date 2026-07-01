"""
Модуль интерфейса (Interface).

Это «приложение»: связывает вычислительное ядро (Simulation) с отрисовкой
(Renderer) и панелью управления (ControlPanel). Здесь живёт главный цикл,
обработка клавиатуры/мыши и набор готовых сценариев.

С ядром взаимодействуем ТОЛЬКО через публичный API класса Simulation:
add_body / remove_body / step / set_dt / set_method / start / pause /
reset / get_positions / get_bodies / is_running.
"""

import math
import random

import pygame

from Core.simulation import Simulation
from Utils.constants import G, MASS_SUN, MASS_EARTH, MASS_MOON, AU
from UI.renderer import Renderer
from UI.controls import ControlPanel, TextField


# Радиус лунной орбиты (нет в constants.py, задаём локально для сценария)
MOON_ORBIT = 3.844e8

# Масса, которую получает новое тело при размещении мышью; точную массу
# потом можно ввести числом в панели параметров слева снизу.
NEW_BODY_MASS = MASS_EARTH

# Тела тяжелее этого порога рисуем светящейся звездой, легче — планетой/спутником.
STAR_MASS_THRESHOLD = 1e29


# Диапазоны базового пиксельного радиуса. У звёзд шкала своя и более
# компактная — иначе яркое свечение проглатывало бы всю сцену.
PLANET_MIN_RADIUS = 4
PLANET_MAX_RADIUS = 22
STAR_MIN_RADIUS = 9
STAR_MAX_RADIUS = 18


def _radius_for_mass(mass: float) -> int:
    """
    Базовый (при «эталонном» масштабе камеры) пиксельный радиус тела по массе,
    логарифмическая шкала. Фактический радиус на экране дополнительно немного
    меняется при зуме (см. Renderer.effective_radius) — тело чуть увеличивается,
    когда вы приближаетесь к нему вплотную (например, чтобы разглядеть, как
    Луна обходит Землю), но не «раздувается» до абсурда.
    """
    if mass >= STAR_MASS_THRESHOLD:
        r = STAR_MIN_RADIUS + 1.6 * math.log10(mass / STAR_MASS_THRESHOLD + 1.0)
        return int(max(STAR_MIN_RADIUS, min(STAR_MAX_RADIUS, r)))
    r = PLANET_MIN_RADIUS + 2.4 * math.log10(mass / MASS_MOON + 1.0)
    return int(max(PLANET_MIN_RADIUS, min(PLANET_MAX_RADIUS, r)))

# Перевод длины перетаскивания мышью в скорость нового тела.
# Скорость = (мировое смещение перетаскивания) / VEL_DRAG_TIME.
# Чем длиннее «потянуть» — тем быстрее тело. Значение подобрано так, чтобы
# на масштабе «Солнце–Земля» перетаскивание ~40 px давало ~30 км/с.
VEL_DRAG_TIME = 5.0e5

# Палитра цветов для тел (по порядку добавления)
PALETTE = [
    (255, 210, 70),    # жёлтый  — звезда/Солнце
    (90, 160, 255),    # синий   — Земля
    (200, 200, 210),   # серый   — Луна
    (255, 120, 90),    # красный
    (120, 230, 160),   # зелёный
    (210, 130, 255),   # фиолетовый
]


def _circular_velocity(central_mass: float, radius: float) -> float:
    """ Скорость круговой орбиты v = sqrt(G*M/R) — для построения сценариев. """
    return (G * central_mass / radius) ** 0.5


def _polygon_orbital_speed(mass: float, radius: float, n: int) -> float:
    """
    Точная скорость кругового обращения для N РАВНЫХ масс, расставленных
    в вершинах правильного N-угольника (классическая задача Лагранжа о
    центральной конфигурации многоугольника — обобщение двойной звезды на
    произвольное число тел). В отличие от грубой оценки «заменим соседей одной
    массой в центре и посчитаем по Кеплеру» (она давала скорость примерно на
    треть больше нужной и тела просто разлетались), эта формула честно
    суммирует притяжение от всех остальных тел на кольце:

        ω² = (G m / R³) · (1/4) · Σ_{k=1}^{N-1} 1/sin(kπ/N)

    При N=2 совпадает со скоростью в сценарии «Двойная звезда».
    """
    s = sum(1.0 / math.sin(k * math.pi / n) for k in range(1, n))
    return (G * mass * s / (4 * radius)) ** 0.5


def _body(mass, x, y, z, vx, vy, vz, color):
    """ Удобный конструктор описания тела сценария (3D); радиус считается по массе. """
    return dict(mass=mass, x=x, y=y, z=z, vx=vx, vy=vy, vz=vz, color=color,
                radius=_radius_for_mass(mass))


def build_scenarios() -> dict:
    """
    Готовые сцены. Каждое значение словаря — функция без аргументов, которая
    возвращает свежий словарь {"dt": ..., "bodies": [...]}. Для большинства
    сцен она просто отдаёт один и тот же фиксированный набор тел; для сцен
    с пометкой «случайные» — каждый раз подмешивает небольшой случайный
    разброс масс/позиций/скоростей, чтобы наглядно показать, что метод
    остаётся физически корректным (энергия ведёт себя разумно, движение
    выглядит правдоподобно) не только для одного точно подобранного случая.
    """
    scenarios = {}

    # 1. Солнце — Земля (в плоскости XY)
    scenarios["Солнце - Земля"] = lambda: {
        "dt": 3600,
        "bodies": [
            _body(MASS_SUN, 0, 0, 0, 0, 0, 0, PALETTE[0]),
            _body(MASS_EARTH, AU, 0, 0, 0, 29783, 0, PALETTE[1]),
        ],
    }

    # 2. Солнце — Земля — Луна
    def solar_earth_moon():
        v_earth = 29783
        v_moon = _circular_velocity(MASS_EARTH, MOON_ORBIT)
        return {
            "dt": 1800,
            "bodies": [
                _body(MASS_SUN, 0, 0, 0, 0, 0, 0, PALETTE[0]),
                _body(MASS_EARTH, AU, 0, 0, 0, v_earth, 0, PALETTE[1]),
                _body(MASS_MOON, AU + MOON_ORBIT, 0, 0, 0, v_earth + v_moon, 0, PALETTE[2]),
            ],
        }
    scenarios["Солнце-Земля-Луна"] = solar_earth_moon

    # 3. Двойная звезда (две равные массы вокруг общего центра масс)
    def binary_star():
        m = 1.0e30
        d = 4.0e11
        v = (G * m / (2 * d)) ** 0.5  # из условия круговой орбиты для равных масс
        return {
            "dt": 3600,
            "bodies": [
                _body(m, -d / 2, 0, 0, 0, v, 0, PALETTE[0]),
                _body(m, d / 2, 0, 0, 0, -v, 0, PALETTE[3]),
            ],
        }
    scenarios["Двойная звезда"] = binary_star

    # 4. Три тела (фиксированная демонстрация — хаотический «танец» равных звёзд)
    def three_bodies_fixed():
        m3 = 1.0e30
        r3 = 2.0e11
        v3 = 0.5 * _circular_velocity(m3, r3)
        return {
            "dt": 2000,
            "bodies": [
                _body(m3, -r3, 0, 0, 0, v3, 0, PALETTE[0]),
                _body(m3, r3, 0, 0, 0, -v3, 0, PALETTE[3]),
                _body(m3, 0, r3 * 1.4, 0, v3, 0, 0, PALETTE[4]),
            ],
        }
    scenarios["Три тела"] = three_bodies_fixed

    # 5. 3D: наклонные орбиты (две планеты в разных плоскостях — видно объём)
    def tilted_orbits():
        v1 = _circular_velocity(MASS_SUN, AU)
        r2 = 1.6 * AU
        v2 = _circular_velocity(MASS_SUN, r2)
        inc = math.radians(40)  # наклонение второй орбиты к плоскости XY
        return {
            "dt": 7200,
            "bodies": [
                _body(MASS_SUN, 0, 0, 0, 0, 0, 0, PALETTE[0]),
                _body(MASS_EARTH, AU, 0, 0, 0, v1, 0, PALETTE[1]),
                _body(MASS_EARTH, r2, 0, 0, 0, v2 * math.cos(inc), v2 * math.sin(inc), PALETTE[4]),
            ],
        }
    scenarios["3D: наклонные орбиты"] = tilted_orbits

    # 6. Полная Солнечная система: Солнце + 8 планет на круговых орбитах
    def full_solar_system():
        # (масса кг, расстояние в а.е., цвет)
        planets = [
            (3.3011e23, 0.387, (170, 170, 175)),   # Меркурий
            (4.8675e24, 0.723, (230, 200, 150)),   # Венера
            (MASS_EARTH, 1.000, PALETTE[1]),       # Земля
            (6.4171e23, 1.524, (210, 110, 80)),    # Марс
            (1.8982e27, 5.204, (210, 180, 140)),   # Юпитер
            (5.6834e26, 9.582, (225, 200, 150)),   # Сатурн
            (8.6810e25, 19.201, (170, 220, 230)),  # Уран
            (1.02413e26, 30.047, (80, 100, 220)),  # Нептун
        ]
        bodies = [_body(MASS_SUN, 0, 0, 0, 0, 0, 0, PALETTE[0])]
        for mass, dist_au, color in planets:
            dist = dist_au * AU
            v = _circular_velocity(MASS_SUN, dist)
            bodies.append(_body(mass, dist, 0, 0, 0, v, 0, color))
        return {"dt": 3600, "bodies": bodies}
    scenarios["Солнечная система"] = full_solar_system

    # 7. Три тела со случайными условиями: та же треугольная конфигурация
    # равных масс, что и в сценарии «Три тела», но с небольшим случайным
    # разбросом при каждом запуске — хорошая демонстрация чувствительности
    # хаотической системы к начальным условиям и устойчивости метода.
    def three_bodies_random():
        m3 = 1.0e30
        r3 = 2.0e11
        v3 = 0.5 * _circular_velocity(m3, r3)

        def j(value, spread=0.05):
            return value * (1 + random.uniform(-spread, spread))

        # настоящий разброс по всем трём осям — тела не заперты в плоскости XY,
        # и Z-компонента скорости тоже случайна, так что движение не плоское
        z_spread = r3 * 0.3
        vz_spread = v3 * 0.3

        def jz(scale):
            return random.uniform(-scale, scale)

        return {
            "dt": 2000,
            "bodies": [
                _body(j(m3), j(-r3, 0.03), 0, jz(z_spread),
                     0, j(v3), jz(vz_spread), PALETTE[0]),
                _body(j(m3), j(r3, 0.03), 0, jz(z_spread),
                     0, j(-v3), jz(vz_spread), PALETTE[3]),
                _body(j(m3), 0, j(r3 * 1.4, 0.03), jz(z_spread),
                     j(v3), 0, jz(vz_spread), PALETTE[4]),
            ],
        }
    scenarios["Три тела (случайные)"] = three_bodies_random

    # 8. Пять тел на случайно возмущённых орбитах вокруг общего центра масс —
    # показывает поведение метода при N > 3, конфигурация каждый раз новая.
    def five_bodies_random():
        n = 5
        base_mass = 8.0e29
        base_r = 2.5e11
        colors = [PALETTE[0], PALETTE[1], PALETTE[3], PALETTE[4], PALETTE[5]]
        bodies = []
        for i in range(n):
            angle = 2 * math.pi * i / n + random.uniform(-0.15, 0.15)
            r = base_r * (1 + random.uniform(-0.15, 0.15))
            mass = base_mass * (1 + random.uniform(-0.25, 0.25))
            x, y = r * math.cos(angle), r * math.sin(angle)
            # заметный разброс по Z (не символические ±6%, а по-настоящему
            # трёхмерное движение) — треть радиуса орбиты
            z = r * random.uniform(-0.35, 0.35)
            # точная скорость кругового обращения для N равных масс на кольце
            # (см. _polygon_orbital_speed) — раньше здесь была грубая оценка
            # «вся остальная масса в центре», она давала скорость почти на треть
            # больше нужной, и тела вместо танца просто разлетались.
            # В формулу идёт именно base_mass (масса «соседей», которые тянут
            # это тело) — собственная масса тела в ускорение не входит, она
            # сокращается (как и в обычной формуле круговой орбиты).
            v = _polygon_orbital_speed(base_mass, r, n) * (1 + random.uniform(-0.06, 0.06))
            vx, vy = -v * math.sin(angle), v * math.cos(angle)
            vz = v * random.uniform(-0.35, 0.35)
            bodies.append(_body(mass, x, y, z, vx, vy, vz, colors[i % len(colors)]))
        return {"dt": 1500, "bodies": bodies}
    scenarios["Пять тел (случайные)"] = five_bodies_random

    return scenarios


class Application:
    """ Главное приложение: окно, цикл, события и связь Core <-> UI. """

    WIDTH = 1100
    HEIGHT = 920
    SIDEBAR_W = 250
    FPS = 60
    MAX_TRAIL = 600  # макс. длина следа на тело

    DT_STEPS = [300, 600, 900, 1800, 3600, 7200, 14400, 28800, 43200, 86400]

    def __init__(self, simulation: Simulation):
        pygame.init()
        pygame.display.set_caption("Задача N тел — гравитационная симуляция")
        self.screen = pygame.display.set_mode((self.WIDTH, self.HEIGHT))
        self.clock = pygame.time.Clock()

        self.sim = simulation

        sim_area = pygame.Rect(0, 0, self.WIDTH - self.SIDEBAR_W, self.HEIGHT)
        sidebar = pygame.Rect(self.WIDTH - self.SIDEBAR_W, 0, self.SIDEBAR_W, self.HEIGHT)
        self.renderer = Renderer(self.screen, sim_area)
        self.panel = ControlPanel(sidebar)

        # Параметры отображения (по индексам тел)
        self.colors: list[tuple[int, int, int]] = []
        self.radii: list[int] = []
        self.trails: list[list[tuple[float, float]]] = []
        self.seeds: list[int] = []      # стабильный «id» тела для текстуры (переживает редактирование)
        self._next_seed = 0

        # Флаги визуализации
        self.show_trails = True
        self.show_vectors = False
        self.show_grid = True

        # Управление камерой мышью
        self._dragging = False     # панорама (средняя кнопка)
        self._rotating = False     # вращение камеры (ЛКМ по пустому месту)
        self._last_mouse = (0, 0)

        # --- Редактор тел ---
        self.edit_mode = False               # режим добавления тел
        self._placing = False                # идёт ли перетаскивание нового тела
        self._place_start_px = (0, 0)        # точка клика (экран)
        self._place_start_world = (0.0, 0.0, 0.0)  # точка клика (мир, z=0)
        self._place_cur_px = (0, 0)          # текущее положение курсора при перетаскивании

        # Всплывающее сообщение (например, ошибка добавления тела)
        self._status_text = ""
        self._status_until = 0
        self._frame = 0

        # --- Выбор тела и панель его параметров (слева снизу) ---
        self.selected_body = None            # выбранный объект Body (по ссылке)
        self.field_font = pygame.font.SysFont("consolas", 15)
        self.label_font = pygame.font.SysFont("consolas", 13)
        self.title_font = pygame.font.SysFont("consolas", 14, bold=True)
        self.fields: dict[str, TextField] = {}
        self._build_inspector()

        self.scenarios = build_scenarios()
        self.current_scenario = None
        self._current_scenario_data = None   # уже сгенерированные тела текущего сценария
        self.running = True

        self._build_panel()

        # Если ядро уже содержит тела (их добавили в main.py) — берём их,
        # иначе грузим сценарий по умолчанию.
        if self.sim.get_bodies():
            self._adopt_existing_bodies()
        else:
            self.load_scenario("Солнце - Земля")

    # ------------------------------------------------------------------
    # Построение панели управления
    # ------------------------------------------------------------------
    def _build_panel(self) -> None:
        p = self.panel

        p.add_header("СИМУЛЯЦИЯ")
        p.add_button("", self.toggle_running,
                     get_label=lambda: "|| Пауза" if self.sim.is_running else "> Старт")
        p.add_button("Сброс", self.reset_scenario)

        p.add_header("МЕТОД И ШАГ")
        p.add_button("Euler", lambda: self.set_method("euler"),
                     width_frac=0.5,
                     get_active=lambda: self.sim.method == "euler")
        p.add_button("RK4", lambda: self.set_method("rk4"),
                     width_frac=0.5, same_row=True,
                     get_active=lambda: self.sim.method == "rk4")
        p.add_button("dt −", self.decrease_dt, width_frac=0.5)
        p.add_button("dt +", self.increase_dt, width_frac=0.5, same_row=True)
        p.add_value(lambda: f"  dt = {self._format_dt(self.sim.dt)}")

        p.add_header("ОТОБРАЖЕНИЕ")
        p.add_button("Траектории", self.toggle_trails,
                     get_active=lambda: self.show_trails)
        p.add_button("Векторы скорости", self.toggle_vectors,
                     get_active=lambda: self.show_vectors)
        p.add_button("Сетка", self.toggle_grid,
                     get_active=lambda: self.show_grid)
        p.add_button("Зум −", lambda: self.renderer.zoom(1 / 1.25), width_frac=0.5)
        p.add_button("Зум +", lambda: self.renderer.zoom(1.25),
                     width_frac=0.5, same_row=True)
        p.add_button("Вписать", self.fit_view, width_frac=0.5)
        p.add_button("Камера", self.reset_camera, width_frac=0.5, same_row=True)

        p.add_header("РЕДАКТОР ТЕЛ")
        p.add_button("Добавить тело", self.toggle_edit_mode,
                     get_active=lambda: self.edit_mode)
        p.add_button("Очистить всё", self.clear_all)

        p.add_header("СЦЕНАРИИ")
        for name in self.scenarios:
            p.add_button(name, lambda n=name: self.load_scenario(n))

    # ------------------------------------------------------------------
    # Работа со сценариями / телами
    # ------------------------------------------------------------------
    def _clear_bodies(self) -> None:
        """ Удаляет все тела через публичный API ядра. """
        while self.sim.get_bodies():
            self.sim.remove_body(0)

    def load_scenario(self, name: str) -> None:
        """
        Генерирует сцену (для «случайных» сценариев — заново, со свежей
        случайностью) и применяет её. Повторный выбор сценария из списка —
        единственный момент, когда случайность перегенерируется; кнопка
        «Сброс» просто откатывает к уже сгенерированному состоянию.
        """
        data = self.scenarios[name]()
        self.current_scenario = name
        self._current_scenario_data = data
        self._apply_scenario_data(data)

    def _apply_scenario_data(self, data: dict) -> None:
        """ Создаёт тела ядра по уже готовому словарю {"dt":..., "bodies":[...]}. """
        self._clear_bodies()
        self.colors.clear()
        self.radii.clear()
        self.seeds.clear()
        self.renderer.clear_sprite_cache()

        self.sim.set_dt(data["dt"])
        for b in data["bodies"]:
            self.sim.add_body(mass=b["mass"], x=b["x"], y=b["y"], z=b["z"],
                              vx=b["vx"], vy=b["vy"], vz=b["vz"])
            self.colors.append(b["color"])
            self.radii.append(b["radius"])
            self.seeds.append(self._new_seed())

        self.sim.reset()
        self.sim.pause()
        self._reset_trails()
        self._frame_scenario()

    def _adopt_existing_bodies(self) -> None:
        """ Берёт тела, уже добавленные в ядро снаружи (например, в main.py). """
        bodies = self.sim.get_bodies()
        for i, body in enumerate(bodies):
            self.colors.append(PALETTE[i % len(PALETTE)])
            self.radii.append(_radius_for_mass(body.mass))
            self.seeds.append(self._new_seed())
        self._reset_trails()
        self.fit_view()

    def reset_scenario(self) -> None:
        """
        Кнопка «Сброс»: возвращает текущий сценарий к уже сгенерированному
        начальному состоянию (те же случайные параметры, если они были —
        новая случайность появляется только при повторном выборе сценария
        из списка «СЦЕНАРИИ»).
        """
        if self.current_scenario and self._current_scenario_data is not None:
            self._apply_scenario_data(self._current_scenario_data)
        else:
            self.sim.reset()
            self._reset_trails()

    def _reset_trails(self) -> None:
        self.trails = [[] for _ in self.sim.get_positions()]

    # ------------------------------------------------------------------
    # Callback-и кнопок
    # ------------------------------------------------------------------
    def toggle_running(self) -> None:
        self.sim.pause() if self.sim.is_running else self.sim.start()

    def set_method(self, method: str) -> None:
        self.sim.set_method(method)

    def increase_dt(self) -> None:
        self.sim.set_dt(self._next_dt(+1))

    def decrease_dt(self) -> None:
        self.sim.set_dt(self._next_dt(-1))

    def _next_dt(self, direction: int) -> float:
        """ Подбирает соседнее «круглое» значение dt из списка DT_STEPS. """
        cur = self.sim.dt
        steps = self.DT_STEPS
        # ближайший индекс к текущему dt
        idx = min(range(len(steps)), key=lambda i: abs(steps[i] - cur))
        idx = max(0, min(len(steps) - 1, idx + direction))
        return steps[idx]

    def toggle_trails(self) -> None:
        self.show_trails = not self.show_trails
        if not self.show_trails:
            self._reset_trails()

    def toggle_vectors(self) -> None:
        self.show_vectors = not self.show_vectors

    def toggle_grid(self) -> None:
        self.show_grid = not self.show_grid

    def fit_view(self) -> None:
        self.renderer.fit(self.sim.get_positions())

    def reset_camera(self) -> None:
        self.renderer.reset_camera()
        self.fit_view()

    def _frame_scenario(self) -> None:
        """
        Кадрирует вид по центру масс (3D) с запасом под орбиты.
        Центр камеры — центр масс, масштаб — из радиуса орбиты, чтобы тело
        не улетало за край сразу после старта.
        """
        bodies = self.sim.get_bodies()
        if not bodies:
            return
        total_m = sum(b.mass for b in bodies)
        com_x = sum(b.mass * b.x for b in bodies) / total_m
        com_y = sum(b.mass * b.y for b in bodies) / total_m
        com_z = sum(b.mass * b.z for b in bodies) / total_m

        # Максимальное удаление тела от центра масс ~ радиус орбиты
        max_r = max((((b.x - com_x) ** 2 + (b.y - com_y) ** 2 + (b.z - com_z) ** 2) ** 0.5
                     for b in bodies), default=0.0)
        if max_r < 1e-6:
            max_r = 1.0

        self.renderer.target = [com_x, com_y, com_z]
        usable = min(self.renderer.area.width, self.renderer.area.height)
        # вид охватывает ~2.4 * радиус орбиты (диаметр + поля)
        self.renderer.scale = usable / (max_r * 2.4)
        # эта точка кадрирования — новый «эталон» для лёгкого роста/уменьшения тел при зуме
        self.renderer.reference_scale = self.renderer.scale

    # ------------------------------------------------------------------
    # Редактор тел (интерактивное добавление / удаление)
    # ------------------------------------------------------------------
    def toggle_edit_mode(self) -> None:
        self.edit_mode = not self.edit_mode
        self._placing = False

    def clear_all(self) -> None:
        self._clear_bodies()
        self.colors.clear()
        self.radii.clear()
        self.trails.clear()
        self.seeds.clear()
        self.renderer.clear_sprite_cache()
        self.selected_body = None
        self.current_scenario = None
        self._current_scenario_data = None
        self.sim.reset()

    def _new_seed(self) -> int:
        """ Уникальный номер для текстуры тела — не меняется, пока тело существует. """
        self._next_seed += 1
        return self._next_seed

    def _add_body_interactive(self, world_pos, velocity) -> None:
        """ Создаёт тело в ядре + заводит для него цвет/радиус/след.
        world_pos и velocity — трёхмерные (тело ставится на плоскость z=0). """
        mass = NEW_BODY_MASS
        try:
            self.sim.add_body(mass=mass, x=world_pos[0], y=world_pos[1], z=world_pos[2],
                              vx=velocity[0], vy=velocity[1], vz=velocity[2])
        except (ValueError, MemoryError, TypeError) as e:
            # ядро может отказать (слишком близко к другому телу, лимит и т.п.)
            self._set_status(str(e))
            return
        self.colors.append(PALETTE[len(self.colors) % len(PALETTE)])
        self.radii.append(_radius_for_mass(mass))
        self.trails.append([])
        self.seeds.append(self._new_seed())
        self.current_scenario = None  # сцена стала пользовательской

    def _delete_at(self, px) -> None:
        """ Удаляет тело, ближайшее к точке экрана (если клик попал по нему). """
        positions = self.sim.get_positions()
        best_i, best_d = None, 1e18
        for i, p in enumerate(positions):
            sx, sy = self.renderer.world_to_screen(*p)
            d = math.hypot(sx - px[0], sy - px[1])
            if d < best_d:
                best_d, best_i = d, i
        if best_i is None:
            return
        if best_d <= self.renderer.effective_radius(self.radii[best_i]) + 10:
            if self.sim.get_bodies()[best_i] is self.selected_body:
                self.selected_body = None
            self.sim.remove_body(best_i)
            del self.colors[best_i]
            del self.radii[best_i]
            if best_i < len(self.seeds):
                del self.seeds[best_i]
            if best_i < len(self.trails):
                del self.trails[best_i]
            self.current_scenario = None

    def _drag_velocity(self):
        """
        Скорость нового тела по перетаскиванию (3D, м/с). Обе точки берём на
        плоскости z=0, поэтому стартовая скорость лежит в плоскости (vz=0);
        компоненту vz можно потом задать числом в инспекторе.
        """
        start = self._place_start_world
        cur = self.renderer.screen_to_plane(self._place_cur_px[0], self._place_cur_px[1])
        return ((cur[0] - start[0]) / VEL_DRAG_TIME,
                (cur[1] - start[1]) / VEL_DRAG_TIME,
                (cur[2] - start[2]) / VEL_DRAG_TIME)

    def _set_status(self, text: str, seconds: float = 2.5) -> None:
        self._status_text = text
        self._status_until = self._frame + int(seconds * self.FPS)

    # ------------------------------------------------------------------
    # Инспектор выбранного тела (панель параметров слева снизу)
    # ------------------------------------------------------------------
    def _build_inspector(self) -> None:
        """ Размещает панель и поля ввода в левом нижнем углу области симуляции. """
        area = self.renderer.area
        w, h = 252, 348
        self._inspector_rect = pygame.Rect(area.left + 12, area.bottom - 12 - h, w, h)
        r = self._inspector_rect

        rows_top = r.top + 32
        row_h, gap = 27, 4
        row_w = w - 20

        def row(i):
            return pygame.Rect(r.left + 10, rows_top + i * (row_h + gap), row_w, row_h)

        # Поля редактируют выбранное тело через _edit_selected (только публичный API ядра).
        # Порядок: масса, затем координаты X/Y/Z и скорости Vx/Vy/Vz (всё в СИ).
        self.fields = {
            "mass": TextField(row(0), "масса", lambda: self.selected_body.mass,
                              lambda v: self._edit_selected(mass=v), self._fmt_edit),
            "x": TextField(row(1), "X", lambda: self.selected_body.x,
                           lambda v: self._edit_selected(x=v), self._fmt_edit),
            "y": TextField(row(2), "Y", lambda: self.selected_body.y,
                           lambda v: self._edit_selected(y=v), self._fmt_edit),
            "z": TextField(row(3), "Z", lambda: self.selected_body.z,
                           lambda v: self._edit_selected(z=v), self._fmt_edit),
            "vx": TextField(row(4), "Vx", lambda: self.selected_body.vx,
                            lambda v: self._edit_selected(vx=v), self._fmt_edit),
            "vy": TextField(row(5), "Vy", lambda: self.selected_body.vy,
                            lambda v: self._edit_selected(vy=v), self._fmt_edit),
            "vz": TextField(row(6), "Vz", lambda: self.selected_body.vz,
                            lambda v: self._edit_selected(vz=v), self._fmt_edit),
        }
        self._delete_btn_rect = pygame.Rect(r.left + 10, r.bottom - 36, row_w, 28)

    @staticmethod
    def _fmt_edit(v: float) -> str:
        """ Компактное редактируемое представление числа. """
        a = abs(v)
        if a != 0 and (a >= 1e6 or a < 1e-2):
            return f"{v:.6g}"
        return f"{v:g}"

    def _selection_active(self) -> bool:
        return self.selected_body is not None and self.selected_body in self.sim.get_bodies()

    def _body_at(self, px):
        """ Возвращает тело под точкой экрана (или None). """
        positions = self.sim.get_positions()
        bodies = self.sim.get_bodies()
        best_i, best_d = None, 1e18
        for i, p in enumerate(positions):
            sx, sy = self.renderer.world_to_screen(*p)
            d = math.hypot(sx - px[0], sy - px[1])
            if d < best_d:
                best_d, best_i = d, i
        if best_i is not None and best_d <= self.renderer.effective_radius(self.radii[best_i]) + 8:
            return bodies[best_i]
        return None

    def _select_body(self, body) -> None:
        self.selected_body = body
        for f in self.fields.values():
            f.blur(commit=False)

    def _edit_selected(self, mass=None, x=None, y=None, z=None,
                       vx=None, vy=None, vz=None) -> None:
        """
        Меняет параметры выбранного тела (3D). Так как ядро не даёт менять Body
        напрямую, делаем это «чисто» через API: удаляем тело и добавляем заново
        с новыми параметрами (сохраняя цвет и след). Тело становится последним
        в списке — обновляем ссылку на него.
        """
        bodies = self.sim.get_bodies()
        if self.selected_body not in bodies:
            return
        i = bodies.index(self.selected_body)
        b = self.selected_body
        nm = b.mass if mass is None else mass
        nx = b.x if x is None else x
        ny = b.y if y is None else y
        nz = b.z if z is None else z
        nvx = b.vx if vx is None else vx
        nvy = b.vy if vy is None else vy
        nvz = b.vz if vz is None else vz

        color, trail, seed = self.colors[i], self.trails[i], self.seeds[i]
        self.sim.remove_body(i)
        del self.colors[i]
        del self.radii[i]
        del self.trails[i]
        del self.seeds[i]

        try:
            self.sim.add_body(mass=nm, x=nx, y=ny, z=nz, vx=nvx, vy=nvy, vz=nvz)
            self.radii.append(_radius_for_mass(nm))
        except (ValueError, MemoryError, TypeError) as e:
            # откатываемся к исходным значениям
            self.sim.add_body(mass=b.mass, x=b.x, y=b.y, z=b.z, vx=b.vx, vy=b.vy, vz=b.vz)
            self.radii.append(_radius_for_mass(b.mass))
            self._set_status(str(e))
        self.colors.append(color)
        self.trails.append(trail)
        self.seeds.append(seed)  # тело то же самое — текстура остаётся прежней
        self.selected_body = self.sim.get_bodies()[-1]
        self.current_scenario = None

    def _delete_selected(self) -> None:
        bodies = self.sim.get_bodies()
        if self.selected_body in bodies:
            i = bodies.index(self.selected_body)
            self.sim.remove_body(i)
            del self.colors[i]
            del self.radii[i]
            del self.trails[i]
            del self.seeds[i]
            self.current_scenario = None
        self.selected_body = None
        for f in self.fields.values():
            f.blur(commit=False)

    # ------------------------------------------------------------------
    # Главный цикл
    # ------------------------------------------------------------------
    def run(self) -> None:
        while self.running:
            self.clock.tick(self.FPS)
            self._handle_events()
            self._update()
            self._draw()
        pygame.quit()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return

            # Сначала панель (если клик попал в кнопку — дальше не передаём)
            if self.panel.handle_event(event):
                continue

            # Затем инспектор выбранного тела (поля ввода / кнопка удаления)
            if self._handle_inspector_event(event):
                continue

            self._handle_view_events(event)

            # Если редактируем поле ввода — клавиатура идёт только туда,
            # а не на горячие клавиши (иначе цифры/буквы сработают как команды).
            if not self._any_field_focused():
                self._handle_keyboard(event)

    def _any_field_focused(self) -> bool:
        return any(f.focused for f in self.fields.values())

    def _handle_inspector_event(self, event) -> bool:
        """ Обрабатывает клики/ввод в панели параметров. True — событие поглощено. """
        if not self._selection_active():
            return False

        if event.type == pygame.KEYDOWN:
            for f in self.fields.values():
                if f.focused:
                    f.handle_key(event)
                    return True
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._delete_btn_rect.collidepoint(event.pos):
                self._delete_selected()
                return True
            if self._inspector_rect.collidepoint(event.pos):
                for f in self.fields.values():
                    if f.box_rect().collidepoint(event.pos):
                        for g in self.fields.values():
                            g.blur(commit=(g is not f))
                        f.focus()
                        return True
                # клик по пустому месту панели — снимаем фокус с полей
                for g in self.fields.values():
                    g.blur()
                return True
            # клик вне панели — применяем ввод и пропускаем дальше (выбор/панорама)
            for g in self.fields.values():
                g.blur()
        return False

    def _handle_view_events(self, event) -> None:
        """
        Мышь в области симуляции (3D):
        - колесо: зум;
        - ПКМ: удалить тело;
        - средняя кнопка: панорама;
        - ЛКМ по телу: выбрать его;
        - ЛКМ по пустому месту: в режиме редактора — поставить тело и задать
          скорость перетаскиванием; иначе — вращать камеру.
        """
        in_area = self.renderer.area.collidepoint(getattr(event, "pos", (0, 0)))

        if event.type == pygame.MOUSEWHEEL:
            mouse = pygame.mouse.get_pos()
            if self.renderer.area.collidepoint(mouse):
                factor = 1.15 if event.y > 0 else 1 / 1.15
                self.renderer.zoom(factor, mouse)
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            if not in_area:
                return
            if event.button == 3:  # ПКМ — удалить тело
                self._delete_at(event.pos)
            elif event.button == 2:  # средняя — панорама (недоступна, пока камера следит за телом)
                if not self._selection_active():
                    self._dragging = True
                    self._last_mouse = event.pos
            elif event.button == 1:
                hit = self._body_at(event.pos)
                if hit is not None:        # клик по телу — выбираем его
                    self._select_body(hit)
                elif self.edit_mode:       # пустое место в режиме редактора — новое тело
                    self._placing = True
                    self._place_start_px = event.pos
                    self._place_cur_px = event.pos
                    self._place_start_world = self.renderer.screen_to_plane(*event.pos)
                else:                      # пустое место — снять выбор и вращать камеру
                    self.selected_body = None
                    self._rotating = True
                    self._last_mouse = event.pos

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                if self._placing:
                    self._placing = False
                    self._add_body_interactive(self._place_start_world, self._drag_velocity())
                self._rotating = False
            elif event.button == 2:
                self._dragging = False

        elif event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            if self._placing:
                self._place_cur_px = event.pos
            elif self._rotating:
                self.renderer.rotate((mx - self._last_mouse[0]) * 0.01,
                                     (my - self._last_mouse[1]) * 0.01)
                self._last_mouse = event.pos
            elif self._dragging:
                self.renderer.pan(mx - self._last_mouse[0], my - self._last_mouse[1])
                self._last_mouse = event.pos

    def _handle_keyboard(self, event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        k = event.key
        if k == pygame.K_SPACE:
            self.toggle_running()
        elif k == pygame.K_r:
            self.reset_scenario()
        elif k == pygame.K_t:
            self.toggle_trails()
        elif k == pygame.K_v:
            self.toggle_vectors()
        elif k == pygame.K_g:
            self.toggle_grid()
        elif k == pygame.K_m:
            self.set_method("euler" if self.sim.method == "rk4" else "rk4")
        elif k == pygame.K_f:
            self.fit_view()
        elif k == pygame.K_a:
            self.toggle_edit_mode()
        elif k == pygame.K_c:
            self.clear_all()
        elif k in (pygame.K_DELETE, pygame.K_BACKSPACE):
            if self._selection_active():
                self._delete_selected()
        elif k in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.increase_dt()
        elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.decrease_dt()
        elif k == pygame.K_ESCAPE:
            self.running = False
        elif pygame.K_1 <= k <= pygame.K_9:
            idx = k - pygame.K_1
            names = list(self.scenarios.keys())
            if idx < len(names):
                self.load_scenario(names[idx])

    def _update(self) -> None:
        self._frame += 1
        self._sync_camera_to_selection()
        self._handle_camera_keys()
        if self.sim.is_running:
            self.sim.step()
            if self.show_trails:
                self._record_trails()

    def _sync_camera_to_selection(self) -> None:
        """
        Пока тело выбрано, камера каждый кадр смотрит точно на него. Отсюда
        сразу два эффекта: зум (который всегда идёт вокруг renderer.target)
        приближает именно к выбранному телу, а во время симуляции камера сама
        следует за ним по орбите. Чтобы снять слежение — кликнуть по пустому месту.
        """
        if self._selection_active():
            b = self.selected_body
            self.renderer.target = [b.x, b.y, b.z]

    def _handle_camera_keys(self) -> None:
        """ Стрелки двигают камеру так же, как перетаскивание средней кнопкой мыши. """
        if self._any_field_focused() or self._selection_active():
            return
        keys = pygame.key.get_pressed()
        dx = dy = 0
        step = 9
        if keys[pygame.K_LEFT]:
            dx += step
        if keys[pygame.K_RIGHT]:
            dx -= step
        if keys[pygame.K_UP]:
            dy -= step
        if keys[pygame.K_DOWN]:
            dy += step
        if dx or dy:
            self.renderer.pan(dx, dy)

    def _record_trails(self) -> None:
        positions = self.sim.get_positions()
        # на случай рассинхронизации длины (тела добавили/убрали)
        while len(self.trails) < len(positions):
            self.trails.append([])
        for i, pos in enumerate(positions):
            self.trails[i].append(pos)
            if len(self.trails[i]) > self.MAX_TRAIL:
                self.trails[i].pop(0)

    # ------------------------------------------------------------------
    # Отрисовка кадра
    # ------------------------------------------------------------------
    def _draw(self) -> None:
        self.renderer.draw_background(self.show_grid, self._frame)

        if self.show_trails:
            self.renderer.draw_trails(self.trails, self.colors)

        positions = self.sim.get_positions()
        bodies = self.sim.get_bodies()

        if self.show_vectors:
            velocities = [b.get_velocity() for b in bodies]
            self.renderer.draw_velocity_vectors(positions, velocities, self.colors)

        is_star = [b.mass >= STAR_MASS_THRESHOLD for b in bodies]
        self.renderer.draw_bodies(positions, self.colors, self.radii, self.seeds, is_star)

        # Подсветка выбранного тела (оно «выбивается» пульсирующим кольцом)
        self._draw_selection_highlight()

        # Предпросмотр размещаемого тела (кружок + стрелка скорости)
        if self._placing:
            self.renderer.draw_new_body_preview(
                self._place_start_px, self._place_cur_px,
                _radius_for_mass(NEW_BODY_MASS),
                PALETTE[len(self.colors) % len(PALETTE)])

        self.renderer.draw_hud(self._hud_lines())
        self._draw_inspector()
        self.panel.draw(self.screen)

        pygame.display.flip()

    def _draw_selection_highlight(self) -> None:
        if not self._selection_active():
            return
        i = self.sim.get_bodies().index(self.selected_body)
        sx, sy = self.renderer.world_to_screen(*self.sim.get_positions()[i])
        pulse = 3 + int(2 * abs(math.sin(self._frame * 0.12)))
        ring = self.renderer.effective_radius(self.radii[i]) + 6 + pulse
        pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), ring, 2)

    def _draw_inspector(self) -> None:
        """ Панель параметров выбранного тела (слева снизу). """
        if not self._selection_active():
            return
        for f in self.fields.values():
            f.sync()

        r = self._inspector_rect
        panel = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
        panel.fill((20, 24, 38, 235))
        self.screen.blit(panel, (r.left, r.top))
        pygame.draw.rect(self.screen, (90, 130, 200), r, width=1, border_radius=6)

        i = self.sim.get_bodies().index(self.selected_body)
        title = self.title_font.render(f"ПАРАМЕТРЫ ТЕЛА  #{i + 1}",
                                       True, (130, 170, 230))
        self.screen.blit(title, (r.left + 10, r.top + 9))

        for f in self.fields.values():
            f.draw(self.screen, self.field_font, self.label_font)

        # модуль скорости (3D) — как справочная величина
        b = self.selected_body
        speed = math.sqrt(b.vx ** 2 + b.vy ** 2 + b.vz ** 2)
        info = self.label_font.render(f"|V| = {speed:.0f} м/с   (всё в СИ: м, м/с, кг)",
                                      True, (150, 158, 182))
        self.screen.blit(info, (r.left + 10, self._delete_btn_rect.top - 18))

        # кнопка удаления
        pygame.draw.rect(self.screen, (120, 50, 60), self._delete_btn_rect, border_radius=5)
        pygame.draw.rect(self.screen, (180, 80, 90), self._delete_btn_rect, width=1, border_radius=5)
        dl = self.field_font.render("Удалить тело (Del)", True, (235, 220, 222))
        self.screen.blit(dl, (self._delete_btn_rect.centerx - dl.get_width() // 2,
                              self._delete_btn_rect.centery - dl.get_height() // 2))

    def _hud_lines(self) -> list[str]:
        state = "идёт" if self.sim.is_running else "пауза"
        lines = [
            f"Сценарий: {self.current_scenario or 'свой'}",
            f"Состояние: {state}",
            f"Метод: {self.sim.method.upper()}    dt: {self._format_dt(self.sim.dt)}",
            f"Время: {self._format_time(self.sim.time)}",
            f"Тел: {len(self.sim.get_bodies())}",
        ]

        if self._selection_active():
            i = self.sim.get_bodies().index(self.selected_body)
            lines.append(f"Камера следит за телом #{i + 1} (клик по пустому — отпустить)")

        lines.append("")
        lines.append("ЛКМ — вращать")
        lines.append("Колесо — зум")
        lines.append("СКМ — сдвиг")
        lines.append("Стрелки — тоже сдвиг")

        if self.edit_mode:
            lines.append("РЕДАКТОР: ЛКМ+тяни — тело (масса Земли) и скорость")
            lines.append("Точную массу правьте внизу слева после установки")
            lines.append("ПКМ — удалить")
            if self._placing:
                vx, vy, vz = self._drag_velocity()
                lines.append(f"скорость: {math.sqrt(vx*vx + vy*vy + vz*vz):.0f} м/с")

        if self._status_text and self._frame < self._status_until:
            lines.append("")
            lines.append("[!] " + self._status_text)

        return lines

    # ------------------------------------------------------------------
    # Форматирование
    # ------------------------------------------------------------------
    @staticmethod
    def _format_dt(seconds: float) -> str:
        if seconds >= 86400:
            return f"{seconds / 86400:.1f} сут"
        if seconds >= 3600:
            return f"{seconds / 3600:.1f} ч"
        if seconds >= 60:
            return f"{seconds / 60:.0f} мин"
        return f"{seconds:.0f} с"

    @staticmethod
    def _format_time(seconds: float) -> str:
        days = seconds / 86400
        if days >= 365:
            return f"{days / 365.25:.2f} лет"
        if days >= 1:
            return f"{days:.1f} сут"
        return f"{seconds / 3600:.1f} ч"
