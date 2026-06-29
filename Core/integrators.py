from Core.body import Body

def euler_step(bodies: list[Body], accelerations: list[tuple[float, float, float]], dt: float) -> None:
    """ Метод Эйлера (1-й порядок точности) """
    for i, body in enumerate(bodies):
        ax, ay, az = accelerations[i]

        # Обновляем скорость
        body.vx += ax * dt
        body.vy += ay * dt
        body.vz += az * dt

        # Обновляем координаты с новой скоростью
        body.x += body.vx * dt
        body.y += body.vy * dt
        body.z += body.vz * dt

def rk4_step(bodies: list[Body], get_acc_func, dt: float) -> None:
    """ Метод Рунге-Кутты 4-го порядка """
    n = len(bodies)

    # Сохраняем начальные состояния
    x0 = [b.x for b in bodies]
    y0 = [b.y for b in bodies]
    z0 = [b.z for b in bodies]
    vx0 = [b.vx for b in bodies]
    vy0 = [b.vy for b in bodies]
    vz0 = [b.vz for b in bodies]

    # k1: ускорения в начале шага
    k1_v = get_acc_func(bodies)

    # Временное обновление для k2
    for i in range(n):
        bodies[i].vx = vx0[i] + 0.5 * dt * k1_v[i][0]
        bodies[i].vy = vy0[i] + 0.5 * dt * k1_v[i][1]
        bodies[i].vz = vz0[i] + 0.5 * dt * k1_v[i][2]
        bodies[i].x = x0[i] + 0.5 * dt * vx0[i]
        bodies[i].y = y0[i] + 0.5 * dt * vy0[i]
        bodies[i].z = z0[i] + 0.5 * dt * vz0[i]

    # k2: ускорения в середине шага
    k2_v = get_acc_func(bodies)

    # Временное обновление для k3
    for i in range(n):
        bodies[i].vx = vx0[i] + 0.5 * dt * k2_v[i][0]
        bodies[i].vy = vy0[i] + 0.5 * dt * k2_v[i][1]
        bodies[i].vz = vz0[i] + 0.5 * dt * k2_v[i][2]
        bodies[i].x = x0[i] + 0.5 * dt * (vx0[i] + 0.5 * dt * k1_v[i][0])
        bodies[i].y = y0[i] + 0.5 * dt * (vy0[i] + 0.5 * dt * k1_v[i][1])
        bodies[i].z = z0[i] + 0.5 * dt * (vz0[i] + 0.5 * dt * k1_v[i][2])

    # k3: ускорения в середине шага
    k3_v = get_acc_func(bodies)

    # Временное обновление для k4
    for i in range(n):
        bodies[i].vx = vx0[i] + dt * k3_v[i][0]
        bodies[i].vy = vy0[i] + dt * k3_v[i][1]
        bodies[i].vz = vz0[i] + dt * k3_v[i][2]
        bodies[i].x = x0[i] + dt * (vx0[i] + 0.5 * dt * k2_v[i][0])
        bodies[i].y = y0[i] + dt * (vy0[i] + 0.5 * dt * k2_v[i][1])
        bodies[i].z = z0[i] + dt * (vz0[i] + 0.5 * dt * k2_v[i][2])

    # k4: ускорения в конце шага
    k4_v = get_acc_func(bodies)

    # Финальное обновление по формуле RK4
    for i in range(n):
        dvx = (dt / 6.0) * (k1_v[i][0] + 2 * k2_v[i][0] + 2 * k3_v[i][0] + k4_v[i][0])
        dvy = (dt / 6.0) * (k1_v[i][1] + 2 * k2_v[i][1] + 2 * k3_v[i][1] + k4_v[i][1])
        dvz = (dt / 6.0) * (k1_v[i][2] + 2 * k2_v[i][2] + 2 * k3_v[i][2] + k4_v[i][2])

        dx = (dt / 6.0) * (vx0[i] + 2 * (vx0[i] + 0.5 * dt * k1_v[i][0]) +
                           2 * (vx0[i] + 0.5 * dt * k2_v[i][0]) +
                           (vx0[i] + dt * k3_v[i][0]))
        dy = (dt / 6.0) * (vy0[i] + 2 * (vy0[i] + 0.5 * dt * k1_v[i][1]) +
                           2 * (vy0[i] + 0.5 * dt * k2_v[i][1]) +
                           (vy0[i] + dt * k3_v[i][1]))
        dz = (dt / 6.0) * (vz0[i] + 2 * (vz0[i] + 0.5 * dt * k1_v[i][2]) +
                           2 * (vz0[i] + 0.5 * dt * k2_v[i][2]) +
                           (vz0[i] + dt * k3_v[i][2]))

        bodies[i].vx = vx0[i] + dvx
        bodies[i].vy = vy0[i] + dvy
        bodies[i].vz = vz0[i] + dvz
        bodies[i].x = x0[i] + dx
        bodies[i].y = y0[i] + dy
        bodies[i].z = z0[i] + dz