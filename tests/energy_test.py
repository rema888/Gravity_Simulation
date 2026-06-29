"""
Консольная проверка корректности ядра (3D): мониторинг сохранения полной энергии.

Запуск из корня проекта:  py tests/energy_test.py
"""

import os
import sys

# Чтобы импорт Core/Utils работал при запуске из папки tests/, добавляем
# корень проекта в путь поиска модулей.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from Core.simulation import Simulation
from Utils.constants import MASS_SUN, MASS_EARTH, AU

print("=== Инициализация гравитационной симуляции (3D) ===")

sim = Simulation()
# Добавляем Солнце в центре
sim.add_body(mass=MASS_SUN, x=0, y=0, z=0, vx=0, vy=0, vz=0)
# Добавляем Землю на орбите (движение остаётся в плоскости XY)
sim.add_body(mass=MASS_EARTH, x=AU, y=0, z=0, vx=0, vy=29783, vz=0)

# Запоминаем начальную энергию
initial_energy = sim.get_total_energy()['total']
print(f"Начальная полная энергия: {initial_energy:.4e} Дж\n")

print("=== Мониторинг энергии (метод RK4, dt=3600с) ===")
print(f"{'Шаг':<6} {'Время (ч)':<10} {'Полная энергия':<25} {'Изменение (%)':<15}")
print("-" * 60)

for i in range(100):
    sim.step()

    # Выводим статус каждые 10 шагов
    if (i + 1) % 10 == 0:
        current_energy = sim.get_total_energy()['total']
        drift = abs(current_energy - initial_energy) / abs(initial_energy) * 100

        print(f"{i + 1:<6} {sim.time / 3600:<10.1f} {current_energy:<25.4e} {drift:<15.2e}")

final_drift = abs(sim.get_total_energy()['total'] - initial_energy) / abs(initial_energy)
print(f"\n Итоговое изменение энергии за 100 часов: {final_drift:.2e}%")
print("Если значение < 0.0001% — симуляция работает корректно!")
