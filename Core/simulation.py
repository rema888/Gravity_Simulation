from Core.body import Body
from Core.physics import calculate_accelerations
from Core.integrators import euler_step, rk4_step
from Utils.constants import G, DEFAULT_DT, DEFAULT_METHOD

class Simulation:
    """
    Главный класс симуляции гравитационного взаимодействия N тел.
    Управляет состоянием системы, шагом времени и методом интегрирования.
    Предоставляет интерфейс для модуля визуализации.
    """
    def __init__(self):
        self.bodies: list[Body] = []  # Список небесных тел
        self.dt: float = DEFAULT_DT   # Шаг времени (с)
        self.method: str = DEFAULT_METHOD  # Метод интегрирования
        self.time: float = 0.0        # Текущее время симуляции (с)
        self._is_running: bool = False  # Флаг состояния (запущена/пауза)

    def add_body(self, mass: float, x: float, y: float, z: float,
                 vx: float, vy: float, vz: float) -> None:
        """ Добавляет новое тело в симуляцию с полной проверкой входных данных """
        import math

        # Проверка массы
        if mass <= 0:
            raise ValueError(f"Масса тела должна быть положительной. Получено: {mass}")

        # Проверка типов координат и скоростей
        coords_speeds = [x, y, z, vx, vy, vz]
        if not all(isinstance(v, (int, float)) for v in coords_speeds):
            raise TypeError("Координаты и скорости должны быть числовыми значениями.")

        # Проверка на NaN/Inf (критично для численных методов)
        for val in [mass] + coords_speeds:
            if math.isnan(val) or math.isinf(val):
                raise ValueError(f"Недопустимое значение: {val}. Используйте конечные числа.")

        # Защита от сингулярности: не даём создать тело слишком близко к существующему
        MIN_DISTANCE = 1e6  # Минимальное расстояние между телами (1000 км)
        for body in self.bodies:
            dx = body.x - x
            dy = body.y - y
            dz = body.z - z
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            if dist < MIN_DISTANCE:
                raise ValueError(
                    f"Новое тело слишком близко к существующему (расстояние {dist:.0f} м). "
                    f"Минимально допустимое: {MIN_DISTANCE} м."
                )

        # Лимит количества тел для защиты от зависания O(N²)
        MAX_BODIES = 500
        if len(self.bodies) >= MAX_BODIES:
            raise MemoryError(
                f"Достигнут лимит тел ({MAX_BODIES}). Для большего количества "
                f"требуется оптимизация алгоритма (Barnes-Hut)."
            )

        body = Body(mass=mass, x=x, y=y, z=z, vx=vx, vy=vy, vz=vz)
        self.bodies.append(body)

    def remove_body(self, index: int) -> None:
        """ Удаляет тело по индексу из списка """
        if 0 <= index < len(self.bodies):
            del self.bodies[index]

    def set_dt(self, dt: float) -> None:
        """ Устанавливает шаг времени """
        if dt > 0:
            self.dt = dt
        else:
            raise ValueError("Шаг времени dt должен быть положительным числом.")

    def set_method(self, method: str) -> None:
        """ Устанавливает метод интегрирования """
        if method in ["euler", "rk4"]:
            self.method = method
        else:
            raise ValueError("Можно использовать либо метод Эйлера, либо метод Рунге-Кутты 4 порядка точности")

    def step(self) -> None:
        """
        Выполняет один шаг симуляции:
        1. Рассчитывает ускорения от всех тел
        2. Обновляет скорости и координаты выбранным методом
        3. Увеличивает глобальное время
        """
        if not self.bodies:
            return

        accelerations = calculate_accelerations(self.bodies)

        if self.method == "euler":
            euler_step(self.bodies, accelerations, self.dt)
        elif self.method == "rk4":
            rk4_step(self.bodies, calculate_accelerations, self.dt)

        self.time += self.dt

    def reset(self) -> None:
        """ Сбрасывает время симуляции на 0. Тела остаются на своих местах """
        self.time = 0.0

    def get_positions(self) -> list[tuple[float, float, float]]:
        """
        Возвращает список текущих координат всех тел в формате [(x1,y1,z1), (x2,y2,z2), ...].
        """
        return [body.get_position() for body in self.bodies]

    def get_bodies(self) -> list[Body]:
        """ Возвращает полный список объектов Body (для отладки или расширенной визуализации) """
        return self.bodies.copy()  # Возвращаем копию, чтобы защитить ядро от внешних изменений

    def get_total_energy(self) -> dict[str, float]:
        """
        Рассчитывает полную механическую энергию системы.
        Используется для проверки корректности работы симуляции.
        """
        import math

        kinetic = 0.0      # Кинетическая энергия (движение)
        potential = 0.0    # Потенциальная энергия (гравитация)

        # Считаем кинетическую энергию: E_k = 0.5 * m * v^2
        for body in self.bodies:
            v_squared = body.vx**2 + body.vy**2 + body.vz**2
            kinetic += 0.5 * body.mass * v_squared

        # Считаем потенциальную энергию: E_p = -G * m1 * m2 / r
        n = len(self.bodies)
        for i in range(n):
            for j in range(i + 1, n):
                dx = self.bodies[j].x - self.bodies[i].x
                dy = self.bodies[j].y - self.bodies[i].y
                dz = self.bodies[j].z - self.bodies[i].z
                r = math.sqrt(dx*dx + dy*dy + dz*dz)

                # Защита от деления на ноль, если тела совпали
                if r > 1e-10:
                    potential -= G * self.bodies[i].mass * self.bodies[j].mass / r

        return {
            'kinetic': kinetic,
            'potential': potential,
            'total': kinetic + potential
        }

    @property
    def is_running(self) -> bool:
        """ Возвращает статус симуляции (запущена или нет) """
        return self._is_running

    def start(self) -> None:
        """ Запускает симуляцию """
        self._is_running = True

    def pause(self) -> None:
        """ Ставит симуляцию на паузу """
        self._is_running = False