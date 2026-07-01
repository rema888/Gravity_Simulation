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
from UI.interface import Application, NEW_BODY_MASS, STAR_MASS_THRESHOLD


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

    # 3) Интерактивное добавление тела (на плоскости z=0), фиксированная масса Земли
    app.clear_all()
    app.edit_mode = True

    def drag(a, b):
        app._handle_view_events(ev(pygame.MOUSEBUTTONDOWN, button=1, pos=a))
        app._handle_view_events(ev(pygame.MOUSEMOTION, pos=b))
        app._handle_view_events(ev(pygame.MOUSEBUTTONUP, button=1, pos=b))

    drag((430, 420), (430, 420))   # тело без скорости
    drag((600, 420), (600, 360))   # тело со скоростью
    assert len(sim.get_bodies()) == 2
    planet = sim.get_bodies()[1]
    assert abs(planet.z) < 1e6, "новое тело должно лежать на плоскости z=0"
    assert abs(planet.mass - NEW_BODY_MASS) < 1, "новое тело должно иметь массу Земли"
    assert len(app.seeds) == 2, "у каждого тела должен быть seed для текстуры"
    assert all(r >= 8 for r in app.radii), "тела должны быть достаточно крупными, чтобы видеть текстуру"

    # показатель массы слева (инспектор) должен корректно отражать реальную массу тела
    app._select_body(planet)
    app.fields["mass"].sync()
    assert abs(float(app.fields["mass"].text) - NEW_BODY_MASS) / NEW_BODY_MASS < 1e-5, \
        "поле массы в инспекторе не совпадает с массой тела"

    # после редактирования массы (звезда) seed того же тела должен сохраниться (текстура не мигает)
    seed_before = app.seeds[app.sim.get_bodies().index(app.selected_body)]
    app._edit_selected(mass=STAR_MASS_THRESHOLD * 2)
    seed_after = app.seeds[app.sim.get_bodies().index(app.selected_body)]
    assert seed_before == seed_after, "seed текстуры должен переживать редактирование тела"
    assert app.selected_body.mass >= STAR_MASS_THRESHOLD, "масса не применилась"

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

    # 5) HUD без FPS/энергии; метод подписан Euler; подсказка про СКМ и стрелки
    hud = app._hud_lines()
    assert not any("FPS" in s or "Энерг" in s for s in hud)
    assert any("СКМ" in s for s in hud), "должна быть подсказка про СКМ"
    assert any("трелки" in s for s in hud), "должна быть подсказка про стрелки"
    labels = [w.label() for w in app.panel.widgets]
    assert "Euler" in labels and "Эйлер" not in labels

    # 6) рудиментные кнопки смены массы удалены из панели
    assert not any(lbl.strip().startswith("масса") for lbl in labels), \
        "кнопки/подпись 'масса ±' должны быть удалены"

    # 7) космический фон и текстуры тел строятся без ошибок
    app._draw()
    assert len(app.renderer._stars) > 0, "звёздное поле должно быть сгенерировано"
    assert any(s["bright"] for s in app.renderer._stars), "должны быть яркие звёзды со сверканием"
    assert len(app.renderer._nebula) > 0, "туманности на небесной сфере должны быть сгенерированы"
    assert app.renderer._vignette.get_size() == (app.renderer.area.width, app.renderer.area.height)
    star_body_seed = app.seeds[app.sim.get_bodies().index(app.selected_body)]
    key, sprite = app.renderer._sprite_cache[star_body_seed]
    assert key[2] is True, "тело с массой выше порога должно рисоваться как звезда"
    assert sprite.get_width() > 0 and sprite.get_height() > 0

    # 8) пока тело выбрано — камера каждый кадр смотрит точно на него (зум приближает к нему же)
    assert app._selection_active()
    app._sync_camera_to_selection()
    b = app.selected_body
    assert list(app.renderer.target) == [b.x, b.y, b.z], "камера должна смотреть на выбранное тело"

    # тело подвинулось за шаг симуляции — камера должна последовать за ним
    app.sim.start()
    app.sim.step()
    app._sync_camera_to_selection()
    assert list(app.renderer.target) == [b.x, b.y, b.z], "камера должна следовать за телом при движении"

    def fake_keys(pressed):
        original = pygame.key.get_pressed
        pygame.key.get_pressed = lambda: _FakeKeys(pressed)
        return original

    # пока идёт слежение, стрелки и СКМ-панорама намеренно не двигают камеру (иначе слежение
    # тут же перебивало бы ручной сдвиг обратно на следующем кадре)
    target_before = list(app.renderer.target)
    original_get_pressed = fake_keys({pygame.K_RIGHT: True})
    try:
        app._handle_camera_keys()
    finally:
        pygame.key.get_pressed = original_get_pressed
    assert list(app.renderer.target) == target_before, "стрелки не должны двигать камеру при слежении"

    app._handle_view_events(ev(pygame.MOUSEBUTTONDOWN, button=2, pos=(400, 400)))
    assert app._dragging is False, "СКМ-панорама не должна включаться при слежении"

    # 9) снимаем выделение (как при клике по пустому месту) — стрелки и СКМ снова работают как обычно
    app.selected_body = None
    assert not app._selection_active()

    target_before = list(app.renderer.target)
    original_get_pressed = fake_keys({pygame.K_RIGHT: True})
    try:
        app._handle_camera_keys()
    finally:
        pygame.key.get_pressed = original_get_pressed
    assert list(app.renderer.target) != target_before, "стрелка должна сдвигать камеру, когда ничего не выбрано"

    app._handle_view_events(ev(pygame.MOUSEBUTTONDOWN, button=2, pos=(400, 400)))
    assert app._dragging is True, "СКМ-панорама должна работать, когда ничего не выбрано"
    app._handle_view_events(ev(pygame.MOUSEBUTTONUP, button=2, pos=(400, 400)))

    pygame.quit()
    print("ALL OK")


class _FakeKeys:
    """ Подменяет pygame.key.get_pressed() для проверки обработки стрелок без реального окна. """

    def __init__(self, pressed: dict):
        self._pressed = pressed

    def __getitem__(self, key):
        return self._pressed.get(key, False)


if __name__ == "__main__":
    main()
