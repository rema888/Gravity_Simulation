class Body:
    """ Небесное тело с массой, координатами и скоростью """
    def __init__(self, mass: float, x: float, y: float, vx: float, vy: float):
        self.mass = mass      # Масса (кг)
        self.x = x            # Координата X (м)
        self.y = y            # Координата Y (м)
        self.vx = vx          # Скорость по X (м/с)
        self.vy = vy          # Скорость по Y (м/с)
        self.ax = 0.0         # Ускорение по X (м/с²), обнуляется каждый шаг
        self.ay = 0.0         # Ускорение по Y (м/с²), обнуляется каждый шаг

    def get_position(self) -> tuple[float, float]:
        """ Возвращает текущие координаты (x, y) """
        return (self.x, self.y)

    def get_velocity(self) -> tuple[float, float]:
        """ Возвращает текущую скорость (vx, vy) """
        return (self.vx, self.vy)