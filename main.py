from Core.simulation import Simulation
from Utils.constants import MASS_SUN, MASS_EARTH, AU

print("=== Инициализация гравитационной симуляции ===")

sim = Simulation()
sim.add_body(mass=MASS_SUN, x=0, y=0, vx=0, vy=0)
sim.add_body(mass=MASS_EARTH, x=AU, y=0, vx=0, vy=29783)

# Запоминаем начальную энергию
initial_energy = sim.get_total_energy()['total']
print(f"Начальная полная энергия: {initial_energy:.4e} Дж\n")

print("=== Мониторинг энергии (метод RK4, dt=3600с) ===")
print(f"{'Шаг':<6} {'Время (ч)':<10} {'Полная энергия':<25} {'Изменение (%)':<15}")
print("-" * 60)

for i in range(100):
    sim.step()

    # Выводим статус каждые 10 шагов, чтобы не забивать консоль
    if (i + 1) % 10 == 0:
        current_energy = sim.get_total_energy()['total']
        drift = abs(current_energy - initial_energy) / abs(initial_energy) * 100

        print(f"{i + 1:<6} {sim.time / 3600:<10.1f} {current_energy:<25.4e} {drift:<15.2e}")

final_drift = abs(sim.get_total_energy()['total'] - initial_energy) / abs(initial_energy)
print(f"\n Итоговое изменение энергии за 100 часов: {final_drift:.2e}%")
print("Если значение < 0.0001% — симуляция работает корректно!")