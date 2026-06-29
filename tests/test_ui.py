"""
Headless-тест графического модуля (UI) против 3D-ядра.

Запускает pygame с «пустым» драйвером (окно не открывается) и проверяет:
- инициализацию приложения и что панель помещается в окно;
- загрузку всех сценариев, шаги симуляции и отрисовку кадра;
- что координаты трёхмерные (x, y, z);
- интерактивное добавление тела мышью (на плоскости z=0);
- выбор тела и редактирование параметров через инспектор (включая Vz);
- что в HUD нет счётчиков FPS/энергии, а метод подписан как Euler.

Запуск из корня проекта:  py tests/test_ui.py
Успех — печатает "ALL OK" и выходит с кодом 0.
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pygame
from Core.simulation import Simulation
from UI.interface import Application


def ev(t, **k):
    return pygame.event.Event(t, **k)


def main() -> None:
    sim = Simulation()
    app = Application(sim)

    # 1) Панель не вылезает за пределы окна
    bottom = max(w.rect.bottom for w in app.panel.widgets)
    assert bottom <= app.HEIGHT, f"панель вылезает: {bottom} > {app.HEIGHT}"

    # 2) Все сценарии: 3D-координаты, шаги и отрисовка без ошибок
    for name in app.scenarios:
        app.load_scenario(name)
        app.sim.start()
        for _ in range(15):
            app._update()
        app._draw()
        pos = sim.get_positions()
        assert all(len(p) == 3 for p in pos), f"координаты не 3D в сценарии {name}"
        assert len(pos) == len(app.colors) == len(app.radii) == len(app.trails)

    # 3) Интерактивное добавление тела (на плоскости z=0)
    app.clear_all()
    app.edit_mode = True
    app.mass_index = 4  # Солнце

    def drag(a, b):
        app._handle_view_events(ev(pygame.MOUSEBUTTONDOWN, button=1, pos=a))
        app._handle_view_events(ev(pygame.MOUSEMOTION, pos=b))
        app._handle_view_events(ev(pygame.MOUSEBUTTONUP, button=1, pos=b))

    drag((430, 420), (430, 420))   # звезда без скорости
    app.mass_index = 1             # Земля
    drag((600, 420), (600, 360))   # планета со скоростью
    assert len(sim.get_bodies()) == 2
    planet = sim.get_bodies()[1]
    assert abs(planet.z) < 1e6, "новое тело должно лежать на плоскости z=0"

    # 4) Выбор тела + редактирование Vz (3D-вектор скорости числом)
    sx, sy = app.renderer.world_to_screen(*sim.get_positions()[1])
    app._handle_view_events(ev(pygame.MOUSEBUTTONDOWN, button=1, pos=(sx, sy)))
    app._handle_view_events(ev(pygame.MOUSEBUTTONUP, button=1, pos=(sx, sy)))
    assert app._selection_active()
    assert set(app.fields) == {"mass", "x", "y", "z", "vx", "vy", "vz"}

    vzf = app.fields["vz"]
    app._handle_inspector_event(ev(pygame.MOUSEBUTTONDOWN, button=1, pos=vzf.box_rect().center))
    for ch in "5000":
        app._handle_inspector_event(ev(pygame.KEYDOWN, key=ord(ch), unicode=ch))
    app._handle_inspector_event(ev(pygame.KEYDOWN, key=pygame.K_RETURN, unicode="\r"))
    assert abs(app.selected_body.vz - 5000) < 1e-3, "Vz не применился"

    # 5) HUD без FPS/энергии; метод подписан Euler
    hud = app._hud_lines()
    assert not any("FPS" in s or "Энерг" in s for s in hud)
    labels = [w.label() for w in app.panel.widgets]
    assert "Euler" in labels and "Эйлер" not in labels

    pygame.quit()
    print("ALL OK")


if __name__ == "__main__":
    main()
