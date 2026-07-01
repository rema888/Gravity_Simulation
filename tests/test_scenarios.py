"""
Тест новых готовых сценариев: Солнечная система, Три тела (случайные),
Пять тел (случайные).

Проверяет:
- «случайные» сценарии дают разные начальные условия при каждом выборе
  из списка, но «Сброс» возвращает к уже сгенерированному состоянию
  (не генерирует новую случайность);
- Солнечная система собирается из Солнца и 8 планет с возрастающим
  расстоянием от Солнца;
- после нескольких шагов симуляции энергия остаётся конечным числом
  (не NaN/Inf) — то есть метод не разваливается на новых сценариях;
- «Три тела»/«Пять тел» (случайные) не разлетаются сразу же — начальная
  скорость подобрана так, чтобы система оставалась связанной хотя бы на
  небольшом участке орбиты (регресс-тест на неверную оценку скорости,
  из-за которой тела раньше просто улетали в стороны).

Запуск из корня проекта:  py tests/test_scenarios.py
Успех — печатает "ALL OK" и выходит с кодом 0.
"""

import math
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from Core.simulation import Simulation
from UI.interface import Application


def _max_distance_from_com(sim) -> float:
    """ Максимальное расстояние тела от центра масс системы — мера «разброса». """
    bodies = sim.get_bodies()
    total_m = sum(b.mass for b in bodies)
    cx = sum(b.mass * b.x for b in bodies) / total_m
    cy = sum(b.mass * b.y for b in bodies) / total_m
    cz = sum(b.mass * b.z for b in bodies) / total_m
    return max(math.sqrt((b.x - cx) ** 2 + (b.y - cy) ** 2 + (b.z - cz) ** 2) for b in bodies)


def _assert_stays_bound(app, sim, steps: int, label: str) -> None:
    """
    Прогоняет сценарий вперёд и проверяет, что тела не улетают в бесконечность
    сразу же — максимальное расстояние от центра масс не должно вырасти в разы
    за небольшой (по сравнению с периодом обращения) участок времени. Раньше
    здесь была ошибка в подборе начальной скорости, и тела «Пяти тел» просто
    разлетались в стороны с первых же кадров.
    """
    r0 = _max_distance_from_com(sim)
    app.sim.start()
    for _ in range(steps):
        app._update()
    r1 = _max_distance_from_com(sim)
    assert r1 < r0 * 2.0, (
        f"{label}: система разлетелась ({r0:.3e} -> {r1:.3e} м за {steps} шагов) — "
        f"похоже, начальная скорость слишком велика для связанной орбиты"
    )
    app.sim.pause()


def main() -> None:
    sim = Simulation()
    app = Application(sim)

    assert "Солнечная система" in app.scenarios
    assert "Три тела (случайные)" in app.scenarios
    assert "Пять тел (случайные)" in app.scenarios

    # --- Солнечная система: Солнце + 8 планет, расстояния по возрастанию ---
    app.load_scenario("Солнечная система")
    bodies = sim.get_bodies()
    assert len(bodies) == 9, f"ожидалось 9 тел (Солнце + 8 планет), получили {len(bodies)}"
    assert bodies[0].mass > bodies[1].mass, "Солнце должно быть куда массивнее первой планеты"
    distances = [math.hypot(b.x, b.y) for b in bodies[1:]]
    assert distances == sorted(distances), "планеты должны идти по возрастанию расстояния от Солнца"
    assert all(r >= 4 for r in app.radii), "все тела должны быть видимого размера"

    for _ in range(10):
        app._update()
    e = sim.get_total_energy()["total"]
    assert math.isfinite(e), "энергия должна оставаться конечным числом"

    # --- Три тела (случайные): два подряд выбора дают разные начальные условия ---
    app.load_scenario("Три тела (случайные)")
    first_run = [(b.mass, b.x, b.y, b.vx, b.vy) for b in sim.get_bodies()]

    # движение должно быть по-настоящему трёхмерным: и позиция, и скорость
    # имеют заметную Z-компоненту, а не заперты в плоскости XY
    bodies3 = sim.get_bodies()
    assert any(abs(b.z) > 1e9 for b in bodies3), \
        "хотя бы одно тело должно заметно отклоняться от плоскости XY по Z"
    assert any(abs(b.vz) > 100 for b in bodies3), \
        "хотя бы одно тело должно иметь заметную Z-компоненту скорости"

    app.load_scenario("Три тела (случайные)")
    second_run = [(b.mass, b.x, b.y, b.vx, b.vy) for b in sim.get_bodies()]

    assert first_run != second_run, "повторный выбор сценария должен давать новую случайность"
    assert len(sim.get_bodies()) == 3

    for _ in range(10):
        app._update()
    e = sim.get_total_energy()["total"]
    assert math.isfinite(e), "энергия в хаотичной системе тоже должна оставаться конечной"

    _assert_stays_bound(app, sim, steps=800, label="Три тела (случайные)")

    # --- «Сброс» откатывает к уже сгенерированному состоянию, без новой случайности ---
    before_reset = [(b.mass, b.x, b.y, b.vx, b.vy) for b in sim.get_bodies()]
    app.reset_scenario()
    after_reset = [(round(m, 6), round(x, 3), round(y, 3), round(vx, 6), round(vy, 6))
                   for m, x, y, vx, vy in [(b.mass, b.x, b.y, b.vx, b.vy) for b in sim.get_bodies()]]
    expected = [(round(m, 6), round(x, 3), round(y, 3), round(vx, 6), round(vy, 6))
                for m, x, y, vx, vy in second_run]
    assert after_reset == expected, "«Сброс» должен вернуть те же случайные значения, что были при выборе"

    # --- Пять тел (случайные): 5 тел, тоже разные при повторном выборе ---
    app.load_scenario("Пять тел (случайные)")
    assert len(sim.get_bodies()) == 5
    bodies5 = sim.get_bodies()
    five_first = [(b.x, b.y, b.z) for b in bodies5]
    assert any(abs(b.z) > 1e9 for b in bodies5), \
        "тела «Пяти тел» тоже должны заметно отклоняться от плоскости XY"
    assert any(abs(b.vz) > 100 for b in bodies5), \
        "тела «Пяти тел» должны иметь заметную Z-компоненту скорости"

    app.load_scenario("Пять тел (случайные)")
    five_second = [(b.x, b.y, b.z) for b in sim.get_bodies()]
    assert five_first != five_second, "«Пять тел» тоже должны рандомизироваться при каждом выборе"

    for _ in range(10):
        app._update()
    e = sim.get_total_energy()["total"]
    assert math.isfinite(e), "энергия в системе из пяти тел должна оставаться конечной"

    _assert_stays_bound(app, sim, steps=1500, label="Пять тел (случайные)")

    import pygame
    pygame.quit()
    print("ALL OK")


if __name__ == "__main__":
    main()
