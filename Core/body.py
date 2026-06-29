class Body:
    """ Небесное тело с массой, координатами и скоростью в 3D пространстве """
    def __init__(self, mass: float, x: float, y: float, z: float,
                 vx: float, vy: float, vz: float):
        self.mass = mass      # Масса (кг)
        self.x = x            # Координата X (м)
        self.y = y            # Координата Y (м)
        self.z = z            # Координата Z (м)
        self.vx = vx          # Скорость по X (м/с)
        self.vy = vy          # Скорость по Y (м/с)
        self.vz = vz          # Скорость по Z (м/с)
        self.ax = 0.0         # Ускорение по X (м/с²), обнуляется каждый шаг
        self.ay = 0.0         # Ускорение по Y (м/с²)
        self.az = 0.0         # Ускорение по Z (м/с²)

    def get_position(self) -> tuple[float, float, float]:
        """ Возвращает текущие координаты (x, y, z) """
        return (self.x, self.y, self.z)

    def get_velocity(self) -> tuple[float, float, float]:
        """ Возвращает текущую скорость (vx, vy, vz) """
        return (self.vx, self.vy, self.vz)