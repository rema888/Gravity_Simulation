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

import pygame

from Core.simulation import Simulation
from Utils.constants import G, MASS_SUN, MASS_EARTH, MASS_MOON, AU
from UI.renderer import Renderer
from UI.controls import ControlPanel, TextField


# Радиус лунной орбиты (нет в constants.py, задаём локально для сценария)
MOON_ORBIT = 3.844e8

# Набор масс для редактора тел: пользователь листает его кнопками «масса −/+».
MASS_OPTIONS = [
    (MASS_MOON, "Луна"),
    (MASS_EARTH, "Земля"),
    (1.898e27, "Юпитер"),
    (1.0e29, "Кор. карлик"),
    (MASS_SUN, "Солнце"),
    (10 * MASS_SUN, "10x Солнце"),
]

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


def _body(mass, x, y, z, vx, vy, vz, color, radius):
    """ Удобный конструктор описания тела сценария (3D). """
    return dict(mass=mass, x=x, y=y, z=z, vx=vx, vy=vy, vz=vz, color=color, radius=radius)


def build_scenarios() -> dict:
    """
    Готовые сцены. Каждое тело — словарь с физикой (mass, x,y,z, vx,vy,vz)
    и параметрами отрисовки (color, radius). Координаты трёхмерные.
    """
    scenarios = {}

    # 1. Солнце — Земля (в плоскости XY)
    scenarios["Солнце - Земля"] = {
        "dt": 3600,
        "bodies": [
            _body(MASS_SUN, 0, 0, 0, 0, 0, 0, PALETTE[0], 12),
            _body(MASS_EARTH, AU, 0, 0, 0, 29783, 0, PALETTE[1], 5),
        ],
    }

    # 2. Солнце — Земля — Луна
    v_earth = 29783
    v_moon = _circular_velocity(MASS_EARTH, MOON_ORBIT)
    scenarios["Солнце-Земля-Луна"] = {
        "dt": 1800,
        "bodies": [
            _body(MASS_SUN, 0, 0, 0, 0, 0, 0, PALETTE[0], 12),
            _body(MASS_EARTH, AU, 0, 0, 0, v_earth, 0, PALETTE[1], 5),
            _body(MASS_MOON, AU + MOON_ORBIT, 0, 0, 0, v_earth + v_moon, 0, PALETTE[2], 3),
        ],
    }

    # 3. Двойная звезда (две равные массы вокруг общего центра масс)
    m = 1.0e30
    d = 4.0e11
    v = (G * m / (2 * d)) ** 0.5  # из условия круговой орбиты для равных масс
    scenarios["Двойная звезда"] = {
        "dt": 3600,
        "bodies": [
            _body(m, -d / 2, 0, 0, 0, v, 0, PALETTE[0], 10),
            _body(m, d / 2, 0, 0, 0, -v, 0, PALETTE[3], 10),
        ],
    }

    # 4. Три тела (хаотический «танец» трёх равных звёзд)
    m3 = 1.0e30
    r3 = 2.0e11
    v3 = 0.5 * _circular_velocity(m3, r3)
    scenarios["Три тела"] = {
        "dt": 2000,
        "bodies": [
            _body(m3, -r3, 0, 0, 0, v3, 0, PALETTE[0], 8),
            _body(m3, r3, 0, 0, 0, -v3, 0, PALETTE[3], 8),
            _body(m3, 0, r3 * 1.4, 0, v3, 0, 0, PALETTE[4], 8),
        ],
    }

    # 5. 3D: наклонные орбиты (две планеты в разных плоскостях — видно объём)
    v1 = _circular_velocity(MASS_SUN, AU)
    r2 = 1.6 * AU
    v2 = _circular_velocity(MASS_SUN, r2)
    inc = math.radians(40)  # наклонение второй орбиты к плоскости XY
    scenarios["3D: наклонные орбиты"] = {
        "dt": 7200,
        "bodies": [
            _body(MASS_SUN, 0, 0, 0, 0, 0, 0, PALETTE[0], 12),
            _body(MASS_EARTH, AU, 0, 0, 0, v1, 0, PALETTE[1], 5),
            _body(MASS_EARTH, r2, 0, 0, 0, v2 * math.cos(inc), v2 * math.sin(inc),
                  PALETTE[4], 5),
        ],
    }

    return scenarios


class Application:
    """ Главное приложение: окно, цикл, события и связь Core <-> UI. """

    WIDTH = 1100
    HEIGHT = 850
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
        self.mass_index = 1                  # текущая масса (индекс в MASS_OPTIONS) = Земля
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
        p.add_button("масса −", lambda: self.change_mass(-1), width_frac=0.5)
        p.add_button("масса +", lambda: self.change_mass(+1),
                     width_frac=0.5, same_row=True)
        p.add_value(lambda: f"  масса: {MASS_OPTIONS[self.mass_index][1]}")
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
        scenario = self.scenarios[name]
        self.current_scenario = name

        self._clear_bodies()
        self.colors.clear()
        self.radii.clear()

        self.sim.set_dt(scenario["dt"])
        for b in scenario["bodies"]:
            self.sim.add_body(mass=b["mass"], x=b["x"], y=b["y"], z=b["z"],
                              vx=b["vx"], vy=b["vy"], vz=b["vz"])
            self.colors.append(b["color"])
            self.radii.append(b["radius"])

        self.sim.reset()
        self.sim.pause()
        self._reset_trails()
        self._frame_scenario()

    def _adopt_existing_bodies(self) -> None:
        """ Берёт тела, уже добавленные в ядро снаружи (например, в main.py). """
        bodies = self.sim.get_bodies()
        for i, _ in enumerate(bodies):
            self.colors.append(PALETTE[i % len(PALETTE)])
            self.radii.append(8)
        self._reset_trails()
        self.fit_view()

    def reset_scenario(self) -> None:
        """ Кнопка «Сброс»: возвращает текущий сценарий в начальное состояние. """
        if self.current_scenario:
            self.load_scenario(self.current_scenario)
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

    # ------------------------------------------------------------------
    # Редактор тел (интерактивное добавление / удаление)
    # ------------------------------------------------------------------
    def toggle_edit_mode(self) -> None:
        self.edit_mode = not self.edit_mode
        self._placing = False

    def change_mass(self, direction: int) -> None:
        self.mass_index = max(0, min(len(MASS_OPTIONS) - 1, self.mass_index + direction))

    def clear_all(self) -> None:
        self._clear_bodies()
        self.colors.clear()
        self.radii.clear()
        self.trails.clear()
        self.selected_body = None
        self.current_scenario = None
        self.sim.reset()

    @staticmethod
    def _radius_for_mass(mass: float) -> int:
        """ Пиксельный радиус тела по его массе (логарифмическая шкала). """
        r = 3 + 2.0 * math.log10(max(mass, 1.0) / MASS_MOON + 1.0)
        return int(max(3, min(16, r)))

    def _add_body_interactive(self, world_pos, velocity) -> None:
        """ Создаёт тело в ядре + заводит для него цвет/радиус/след.
        world_pos и velocity — трёхмерные (тело ставится на плоскость z=0). """
        mass = MASS_OPTIONS[self.mass_index][0]
        try:
            self.sim.add_body(mass=mass, x=world_pos[0], y=world_pos[1], z=world_pos[2],
                              vx=velocity[0], vy=velocity[1], vz=velocity[2])
        except (ValueError, MemoryError, TypeError) as e:
            # ядро может отказать (слишком близко к другому телу, лимит и т.п.)
            self._set_status(str(e))
            return
        self.colors.append(PALETTE[len(self.colors) % len(PALETTE)])
        self.radii.append(self._radius_for_mass(mass))
        self.trails.append([])
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
        if best_d <= self.radii[best_i] + 10:
            if self.sim.get_bodies()[best_i] is self.selected_body:
                self.selected_body = None
            self.sim.remove_body(best_i)
            del self.colors[best_i]
            del self.radii[best_i]
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
        if best_i is not None and best_d <= self.radii[best_i] + 8:
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

        color, trail = self.colors[i], self.trails[i]
        self.sim.remove_body(i)
        del self.colors[i]
        del self.radii[i]
        del self.trails[i]

        try:
            self.sim.add_body(mass=nm, x=nx, y=ny, z=nz, vx=nvx, vy=nvy, vz=nvz)
            self.radii.append(self._radius_for_mass(nm))
        except (ValueError, MemoryError, TypeError) as e:
            # откатываемся к исходным значениям
            self.sim.add_body(mass=b.mass, x=b.x, y=b.y, z=b.z, vx=b.vx, vy=b.vy, vz=b.vz)
            self.radii.append(self._radius_for_mass(b.mass))
            self._set_status(str(e))
        self.colors.append(color)
        self.trails.append(trail)
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
            elif event.button == 2:  # средняя — панорама
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
        elif k == pygame.K_LEFTBRACKET:
            self.change_mass(-1)
        elif k == pygame.K_RIGHTBRACKET:
            self.change_mass(+1)
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
        if self.sim.is_running:
            self.sim.step()
            if self.show_trails:
                self._record_trails()

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
        self.renderer.draw_background(self.show_grid)

        if self.show_trails:
            self.renderer.draw_trails(self.trails, self.colors)

        positions = self.sim.get_positions()

        if self.show_vectors:
            velocities = [b.get_velocity() for b in self.sim.get_bodies()]
            self.renderer.draw_velocity_vectors(positions, velocities, self.colors)

        self.renderer.draw_bodies(positions, self.colors, self.radii)

        # Подсветка выбранного тела (оно «выбивается» пульсирующим кольцом)
        self._draw_selection_highlight()

        # Предпросмотр размещаемого тела (кружок + стрелка скорости)
        if self._placing:
            mass = MASS_OPTIONS[self.mass_index][0]
            self.renderer.draw_new_body_preview(
                self._place_start_px, self._place_cur_px,
                self._radius_for_mass(mass),
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
        ring = self.radii[i] + 6 + pulse
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

        lines.append("")
        lines.append("Камера: ЛКМ — вращать · колесо — зум · ср.кнопка — сдвиг")

        if self.edit_mode:
            lines.append("РЕДАКТОР: ЛКМ+тяни — тело (на плоскости z=0) и скорость")
            lines.append("ПКМ — удалить,  масса: " + MASS_OPTIONS[self.mass_index][1])
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
