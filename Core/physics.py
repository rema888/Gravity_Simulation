from Utils.constants import G

def calculate_accelerations(bodies: list) -> list[tuple[float, float]]:
    """ Рассчитывает ускорения для всех тел в системе под действием гравитации """
    n = len(bodies)
    accelerations = [(0.0, 0.0)] * n

    # Считаем силу взаимодействия каждой пары тел
    for i in range(n):
        ax_total, ay_total = 0.0, 0.0

        for j in range(n):
            if i == j:
                continue

            dx = bodies[j].x - bodies[i].x
            dy = bodies[j].y - bodies[i].y

            r_squared = dx * dx + dy * dy
            # Защита от деления на ноль при совпадении координат
            if r_squared < 1e-10:
                continue

            r_cubed = r_squared ** 1.5
            force_factor = G * bodies[j].mass / r_cubed

            ax_total += force_factor * dx
            ay_total += force_factor * dy

        accelerations[i] = (ax_total, ay_total)

    return accelerations