"""
Модуль элементов управления (Controls).

Содержит простые виджеты для боковой панели: кнопки, переключатели и
текстовые подписи (динамические значения dt, масштаба, времени и т.п.).

Панель сама раскладывает элементы по вертикали и обрабатывает клики мышью,
вызывая callback-функции, которые ей передаёт interface.py. Логику симуляции
этот модуль не знает — он только сообщает «кнопку нажали».
"""

import pygame


class Widget:
    """ Базовый элемент панели (кнопка / переключатель / подпись). """

    # Цвета
    BTN = (38, 44, 66)
    BTN_HOVER = (54, 62, 92)
    BTN_ACTIVE = (60, 120, 90)       # подсветка включённого переключателя
    TEXT = (220, 224, 236)
    HEADER = (130, 170, 230)
    VALUE = (170, 178, 200)

    def __init__(self, rect, text, kind="button",
                 callback=None, get_label=None, get_active=None):
        self.rect = rect
        self.text = text
        self.kind = kind                 # "button" | "toggle" | "header" | "value"
        self.callback = callback
        self.get_label = get_label       # функция -> str (динамический текст)
        self.get_active = get_active     # функция -> bool (подсветка)
        self.hovered = False

    def label(self) -> str:
        return self.get_label() if self.get_label else self.text

    def handle_event(self, event) -> bool:
        """ Возвращает True, если событие обработано (был клик по кнопке). """
        if self.kind in ("header", "value"):
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.callback:
                    self.callback()
                return True
        return False

    def draw(self, surface, font) -> None:
        if self.kind == "header":
            txt = font.render(self.label(), True, self.HEADER)
            surface.blit(txt, (self.rect.x, self.rect.y + 4))
            return
        if self.kind == "value":
            txt = font.render(self.label(), True, self.VALUE)
            surface.blit(txt, (self.rect.x, self.rect.y + 2))
            return

        # button / toggle
        active = self.get_active() if self.get_active else False
        if active:
            color = self.BTN_ACTIVE
        elif self.hovered:
            color = self.BTN_HOVER
        else:
            color = self.BTN
        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        pygame.draw.rect(surface, (70, 78, 110), self.rect, width=1, border_radius=6)

        txt = font.render(self.label(), True, self.TEXT)
        tx = self.rect.x + (self.rect.width - txt.get_width()) // 2
        ty = self.rect.y + (self.rect.height - txt.get_height()) // 2
        surface.blit(txt, (tx, ty))


class TextField:
    """
    Поле числового ввода (для редактора параметров тела).
    Фокусом управляет приложение (клик по полю), здесь — хранение и ввод текста.
    get_value() — функция чтения текущего значения, on_commit(float) — применение,
    fmt(float) -> str — как показать значение в незанятом поле.
    """

    BG = (26, 30, 46)
    BG_FOCUS = (44, 50, 76)
    BORDER = (70, 78, 110)
    BORDER_FOCUS = (110, 170, 240)
    TEXT = (228, 231, 240)
    LABEL = (150, 158, 182)
    LABEL_W = 64  # ширина подписи слева от поля

    ALLOWED = "0123456789.+-eE"

    def __init__(self, rect, label, get_value, on_commit, fmt):
        self.rect = rect            # вся строка (подпись + поле ввода)
        self.label = label
        self.get_value = get_value
        self.on_commit = on_commit
        self.fmt = fmt
        self.text = ""
        self.focused = False
        self._fresh = False  # True сразу после фокуса: первый ввод заменяет значение

    def box_rect(self):
        """ Прямоугольник самого поля ввода (без подписи). """
        return pygame.Rect(self.rect.x + self.LABEL_W, self.rect.y,
                           self.rect.width - self.LABEL_W, self.rect.height)

    def sync(self) -> None:
        """ Подтянуть текст из текущего значения (если поле не редактируется). """
        if not self.focused:
            try:
                self.text = self.fmt(self.get_value())
            except Exception:
                self.text = ""

    def focus(self) -> None:
        self.focused = True
        self._fresh = True  # показываем текущее значение, но первый ввод его заменит
        try:
            self.text = self.fmt(self.get_value())
        except Exception:
            self.text = ""

    def blur(self, commit: bool = True) -> None:
        if self.focused and commit:
            self.commit()
        self.focused = False

    def commit(self) -> None:
        try:
            self.on_commit(float(self.text))
        except (ValueError, TypeError):
            pass  # некорректный ввод — игнорируем, значение не меняем

    def handle_key(self, event) -> None:
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.commit()
            self.focused = False
        elif event.key == pygame.K_ESCAPE:
            self.focused = False
        elif event.key == pygame.K_BACKSPACE:
            self._fresh = False
            self.text = self.text[:-1]
        else:
            ch = event.unicode
            if ch and ch in self.ALLOWED:
                if self._fresh:        # первый символ заменяет старое значение
                    self.text = ""
                    self._fresh = False
                self.text += ch

    def draw(self, surface, font, label_font) -> None:
        lbl = label_font.render(self.label, True, self.LABEL)
        surface.blit(lbl, (self.rect.x, self.rect.y + (self.rect.height - lbl.get_height()) // 2))

        box = self.box_rect()
        pygame.draw.rect(surface, self.BG_FOCUS if self.focused else self.BG, box, border_radius=4)
        border = self.BORDER_FOCUS if self.focused else self.BORDER
        pygame.draw.rect(surface, border, box, width=1, border_radius=4)

        shown = self.text + ("|" if self.focused else "")
        txt = font.render(shown, True, self.TEXT)
        # обрезаем по правому краю, если не влезает
        clip = surface.get_clip()
        surface.set_clip(box.inflate(-8, 0))
        surface.blit(txt, (box.x + 5, box.y + (box.height - txt.get_height()) // 2))
        surface.set_clip(clip)


class ControlPanel:
    """ Боковая панель: хранит виджеты, автоматически раскладывает и рисует их. """

    BG_COLOR = (18, 20, 32)
    BORDER_COLOR = (40, 46, 68)
    PAD = 14
    BTN_H = 30
    GAP = 6

    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        self.widgets: list[Widget] = []
        self._cursor_y = rect.top + self.PAD
        pygame.font.init()
        self.font = pygame.font.SysFont("consolas", 15)
        self.header_font = pygame.font.SysFont("consolas", 14, bold=True)

    # --- Методы построения панели (вызываются из interface.py) ---
    def _alloc(self, height: int) -> pygame.Rect:
        r = pygame.Rect(self.rect.left + self.PAD, self._cursor_y,
                        self.rect.width - 2 * self.PAD, height)
        self._cursor_y += height + self.GAP
        return r

    def add_header(self, text: str) -> None:
        self._cursor_y += 4
        self.widgets.append(Widget(self._alloc(20), text, kind="header"))

    def add_value(self, get_label) -> None:
        self.widgets.append(Widget(self._alloc(20), "", kind="value", get_label=get_label))

    def add_button(self, text, callback, get_label=None, get_active=None,
                   width_frac: float = 1.0, same_row: bool = False) -> Widget:
        """ Добавляет кнопку. same_row=True ставит её рядом с предыдущей. """
        if same_row and self.widgets:
            prev = self.widgets[-1].rect
            x = prev.right + self.GAP
            w = int((self.rect.width - 2 * self.PAD - self.GAP) * width_frac)
            r = pygame.Rect(x, prev.y, w, self.BTN_H)
        else:
            full = self.rect.width - 2 * self.PAD
            w = int(full * width_frac)
            r = pygame.Rect(self.rect.left + self.PAD, self._cursor_y, w, self.BTN_H)
            self._cursor_y += self.BTN_H + self.GAP
        kind = "toggle" if get_active else "button"
        widget = Widget(r, text, kind=kind, callback=callback,
                        get_label=get_label, get_active=get_active)
        self.widgets.append(widget)
        return widget

    def add_spacer(self, h: int = 6) -> None:
        self._cursor_y += h

    # --- Отрисовка и обработка событий ---
    def draw(self, surface) -> None:
        pygame.draw.rect(surface, self.BG_COLOR, self.rect)
        pygame.draw.line(surface, self.BORDER_COLOR,
                         (self.rect.left, self.rect.top),
                         (self.rect.left, self.rect.bottom), 2)
        for w in self.widgets:
            font = self.header_font if w.kind == "header" else self.font
            w.draw(surface, font)

    def handle_event(self, event) -> bool:
        handled = False
        for w in self.widgets:
            if w.handle_event(event):
                handled = True
        return handled

    def contains(self, pos) -> bool:
        return self.rect.collidepoint(pos)
