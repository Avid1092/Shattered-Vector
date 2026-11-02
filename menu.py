"""UI: кнопки, слайдеры, выбор режима/разрешения, бинды, меню, настройки."""
import pygame
from settings import (
    WIDTH, HEIGHT, BG_COLOR, TEXT_COLOR, BUTTON_COLOR, BUTTON_HOVER, VERSION,
    KEYBIND_LABELS, MOUSE_BINDINGS, binding_display, mouse_button_to_name,
    DISPLAY_MODE_LABELS, WINDOW_MODE, FULLSCREEN_MODE, BORDERLESS_MODE,
    DEFAULT_DISPLAY_MODE, DEFAULT_RESOLUTION, _generate_resolutions,
)


class Button:
    def __init__(self, text, center, callback, font, size=(320, 64)):
        self.text = text
        self.rect = pygame.Rect((0, 0), size)
        self.rect.center = center
        self.callback = callback
        self.font = font
        self.hovered = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.callback()
                return True
        return False

    def draw(self, surface):
        color = BUTTON_HOVER if self.hovered else BUTTON_COLOR
        pygame.draw.rect(surface, color, self.rect, border_radius=10)
        pygame.draw.rect(surface, TEXT_COLOR, self.rect, width=2, border_radius=10)
        label = self.font.render(self.text, True, TEXT_COLOR)
        surface.blit(label, label.get_rect(center=self.rect.center))


class Slider:
    def __init__(self, x, y, w, value, callback, label, font=None):
        self.rect = pygame.Rect(x, y, w, 20)
        self.value = max(0.0, min(1.0, float(value)))
        self.callback = callback
        self.label = label
        self.font = font or pygame.font.SysFont("arial", 24)
        self.dragging = False

    def _hit_rect(self):
        return self.rect.inflate(0, 20)

    def _set_from_mouse(self, mx):
        rel = (mx - self.rect.x) / self.rect.width
        self.value = max(0.0, min(1.0, rel))
        self.callback(self.value)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._hit_rect().collidepoint(event.pos):
                self.dragging = True
                self._set_from_mouse(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._set_from_mouse(event.pos[0])

    def draw(self, surface):
        label = self.font.render(self.label, True, TEXT_COLOR)
        surface.blit(label, (self.rect.x, self.rect.y - label.get_height() - 8))

        pygame.draw.rect(surface, (50, 50, 70), self.rect, border_radius=6)
        fill_w = int(self.rect.width * self.value)
        if fill_w > 0:
            pygame.draw.rect(
                surface, (90, 140, 220),
                (self.rect.x, self.rect.y, fill_w, self.rect.height),
                border_radius=6,
            )
        knob_x = self.rect.x + fill_w
        pygame.draw.circle(surface, (230, 230, 245), (knob_x, self.rect.centery), 11)
        pygame.draw.circle(surface, (20, 20, 30), (knob_x, self.rect.centery), 11, 2)

        pct = self.font.render(f"{int(round(self.value * 100))}%", True, TEXT_COLOR)
        surface.blit(pct, (self.rect.right + 16, self.rect.centery - pct.get_height() // 2))


class CycleButton:
    def __init__(self, rect, options, get_index, on_change, font=None):
        self.rect = pygame.Rect(rect)
        self.options = list(options)
        self.get_index = get_index
        self.on_change = on_change
        self.font = font or pygame.font.SysFont("consolas", 20, bold=True)
        self.hovered = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if not self.options:
                    return True
                idx = self.get_index()
                idx = (idx + 1) % len(self.options)
                self.on_change(idx)
                return True
        return False

    def draw(self, surface, text):
        color = BUTTON_HOVER if self.hovered else BUTTON_COLOR
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        pygame.draw.rect(surface, TEXT_COLOR, self.rect, 2, border_radius=8)
        label = self.font.render(text, True, TEXT_COLOR)
        surface.blit(label, label.get_rect(center=self.rect.center))


class KeyButton:
    def __init__(self, action, rect, label):
        self.action = action
        self.rect = pygame.Rect(rect)
        self.label = label
        self.font_label = pygame.font.SysFont("arial", 22)
        self.font_value = pygame.font.SysFont("consolas", 18, bold=True)

    def draw(self, surface, bind_display_name, listening, hovered):
        lbl = self.font_label.render(self.label, True, TEXT_COLOR)
        lbl_rect = lbl.get_rect()
        lbl_rect.right = self.rect.x - 24
        lbl_rect.centery = self.rect.centery
        surface.blit(lbl, lbl_rect)

        if listening:
            color = (210, 170, 60)
        elif hovered:
            color = BUTTON_HOVER
        else:
            color = BUTTON_COLOR
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        pygame.draw.rect(surface, TEXT_COLOR, self.rect, 2, border_radius=8)

        text = "..." if listening else bind_display_name
        val = self.font_value.render(text, True, TEXT_COLOR)
        surface.blit(val, val.get_rect(center=self.rect.center))


class Menu:
    def __init__(self, game):
        self.game = game
        self.font_title = pygame.font.SysFont("arial", 72, bold=True)
        self.font_button = pygame.font.SysFont("arial", 40)
        self.font_version = pygame.font.SysFont("consolas", 16)
        self.buttons = [
            Button("Играть",    (WIDTH // 2, 320), game.start_game,    self.font_button),
            Button("Настройки", (WIDTH // 2, 410), game.open_settings, self.font_button),
            Button("Выйти",     (WIDTH // 2, 500), game.quit,          self.font_button),
        ]

    def handle_event(self, event):
        for b in self.buttons:
            if b.handle_event(event):
                break

    def draw(self, surface):
        surface.fill(BG_COLOR)
        title = self.font_title.render("Платформер", True, TEXT_COLOR)
        surface.blit(title, title.get_rect(center=(WIDTH // 2, 160)))
        for b in self.buttons:
            b.draw(surface)
        version_txt = self.font_version.render(f"v{VERSION}", True, (170, 170, 180))
        surface.blit(version_txt, version_txt.get_rect(bottomright=(WIDTH - 12, HEIGHT - 8)))


class SettingsScreen:
    def __init__(self, game):
        self.game = game
        self.font_title = pygame.font.SysFont("arial", 48, bold=True)
        self.font_section = pygame.font.SysFont("arial", 24, bold=True)
        self.font_label = pygame.font.SysFont("arial", 20)
        self.font_hint = pygame.font.SysFont("arial", 18, italic=True)
        self.font_button = pygame.font.SysFont("arial", 28)
        self.font_version = pygame.font.SysFont("consolas", 16)
        self.font_cycle = pygame.font.SysFont("consolas", 18, bold=True)

        # --- Разрешения ---
        self.resolutions = _generate_resolutions() or [tuple(DEFAULT_RESOLUTION)]
        cur_res = tuple(self.game.settings["resolution"])
        if cur_res not in self.resolutions:
            self.resolutions.append(cur_res)
            self.resolutions.sort(key=lambda s: (s[0] * s[1], s[0]))
        self._res_index = self.resolutions.index(cur_res)

        self._mode_order = [WINDOW_MODE, BORDERLESS_MODE, FULLSCREEN_MODE]
        try:
            self._mode_index = self._mode_order.index(
                self.game.settings.get("display_mode", DEFAULT_DISPLAY_MODE)
            )
        except ValueError:
            self._mode_index = 0

        # ===== РАСКЛАДКА (виртуальные 1280×720) =====
        # Левая колонка — громкость и управление
        self._left_x = 180
        self._left_w = 420

        # Правая колонка — экран
        self._right_x = 780
        self._right_w = 260

        # Громкость (сверху слева)
        self.music_slider = Slider(
            self._left_x, 145, self._left_w,
            game.settings["music_volume"],
            self._on_music, "Музыка",
        )
        self.sfx_slider = Slider(
            self._left_x, 215, self._left_w,
            game.settings["sfx_volume"],
            self._on_sfx, "Звуки",
        )

        # Экран (сверху справа) — кнопки шириной _right_w
        self.mode_btn = CycleButton(
            (self._right_x, 148, self._right_w, 32),
            self._mode_order,
            self._get_mode_index,
            self._on_mode_change,
            self.font_cycle,
        )
        self.res_btn = CycleButton(
            (self._right_x, 218, self._right_w, 32),
            self.resolutions,
            self._get_res_index,
            self._on_res_change,
            self.font_cycle,
        )

        # Управление (ниже слева) — 2 колонки по 3 строки, чтобы уложиться
        self.key_buttons = []
        actions = ["left", "right", "jump", "attack", "roll", "dash"]
        col_xs = [self._left_x, self._left_x + 240]
        y0 = 360
        for i, action in enumerate(actions):
            col = i // 3
            row = i % 3
            rect = pygame.Rect(col_xs[col] + 60, y0 + row * 56, 160, 32)
            self.key_buttons.append(KeyButton(action, rect, KEYBIND_LABELS[action]))

        self.listening_action = None

        self.reset_button = Button(
            "Сбросить", (WIDTH // 2 - 170, HEIGHT - 45),
            self._on_reset, self.font_button, size=(260, 46),
        )
        self.back_button = Button(
            "Назад", (WIDTH // 2 + 170, HEIGHT - 45),
            self._on_back, self.font_button, size=(260, 46),
        )

    # --- Разрешение/режим ---
    def _get_mode_index(self):
        return self._mode_index

    def _get_res_index(self):
        return self._res_index

    def _on_mode_change(self, idx):
        self._mode_index = idx
        new_mode = self._mode_order[idx]
        self.game.settings["display_mode"] = new_mode
        self.game.apply_display_mode()

    def _on_res_change(self, idx):
        self._res_index = idx
        new_res = self.resolutions[idx]
        self.game.settings["resolution"] = [new_res[0], new_res[1]]
        if self.game.settings["display_mode"] != FULLSCREEN_MODE:
            self.game.apply_display_mode()

    # --- Громкость ---
    def _on_music(self, v):
        self.game.settings["music_volume"] = v
        self.game.apply_audio_volumes()

    def _on_sfx(self, v):
        self.game.settings["sfx_volume"] = v
        self.game.apply_audio_volumes()

    # --- Сброс/назад ---
    def _on_reset(self):
        self.game.reset_settings_to_default()
        self.game.settings_screen = SettingsScreen(self.game)
        self.game.settings_screen.sync_from_game()

    def _on_back(self):
        self.game.save_settings()
        self.game.open_menu()

    def sync_from_game(self):
        self.music_slider.value = self.game.settings["music_volume"]
        self.sfx_slider.value = self.game.settings["sfx_volume"]

        try:
            self._mode_index = self._mode_order.index(
                self.game.settings.get("display_mode", DEFAULT_DISPLAY_MODE)
            )
        except ValueError:
            self._mode_index = 0

        cur_res = tuple(self.game.settings["resolution"])
        if cur_res in self.resolutions:
            self._res_index = self.resolutions.index(cur_res)
        else:
            self.resolutions.append(cur_res)
            self.resolutions.sort(key=lambda s: (s[0] * s[1], s[0]))
            self._res_index = self.resolutions.index(cur_res)

        self.listening_action = None

    # --- Бинды ---
    def _assign_binding(self, action, name):
        for other, other_val in list(self.game.settings["keybinds"].items()):
            if other != action and other_val == name:
                self.game.settings["keybinds"][other] = \
                    self.game.settings["keybinds"][action]
                break
        self.game.settings["keybinds"][action] = name
        self.game.resolve_keybinds()
        self.listening_action = None

    # --- События (координаты уже переведены в canvas-пространство в game.py) ---
    # --- События (координаты уже переведены в canvas-пространство в game.py) ---
    def handle_event(self, event):
        # Режим прослушивания новой клавиши/кнопки мыши
        if self.listening_action is not None:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.listening_action = None
                else:
                    self._assign_binding(self.listening_action, pygame.key.name(event.key))
            elif event.type == pygame.MOUSEBUTTONDOWN:
                name = mouse_button_to_name(event.button)
                if name:
                    self._assign_binding(self.listening_action, name)
                else:
                    self.listening_action = None
            return

        # ESC — назад
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._on_back()
            return

        # Слайдеры громкости
        self.music_slider.handle_event(event)
        self.sfx_slider.handle_event(event)

        # Кнопки режима и разрешения
        self.mode_btn.handle_event(event)
        self.res_btn.handle_event(event)

        # Кнопки биндов
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for kb in self.key_buttons:
                if kb.rect.collidepoint(event.pos):
                    self.listening_action = kb.action
                    return

        # Нижние кнопки
        self.reset_button.handle_event(event)
        self.back_button.handle_event(event)

    # --- Отрисовка ---
    def draw(self, surface):
        surface.fill(BG_COLOR)

        # Заголовок по центру виртуального canvas (1280×720)
        title = self.font_title.render("Настройки", True, TEXT_COLOR)
        surface.blit(title, title.get_rect(center=(WIDTH // 2, 45)))

        # ===== Секция «Громкость» (слева сверху) =====
        sec_audio = self.font_section.render("Громкость", True, TEXT_COLOR)
        surface.blit(sec_audio, (self._left_x, 105))
        self.music_slider.draw(surface)
        self.sfx_slider.draw(surface)

        # ===== Секция «Экран» (справа сверху) =====
        sec_disp = self.font_section.render("Экран", True, TEXT_COLOR)
        surface.blit(sec_disp, (self._right_x, 105))

        # Подпись «Режим» слева от кнопки
        lbl_mode = self.font_label.render("Режим:", True, TEXT_COLOR)
        lbl_rect = lbl_mode.get_rect()
        lbl_rect.left = self._right_x - 100
        lbl_rect.centery = self.mode_btn.rect.centery
        surface.blit(lbl_mode, lbl_rect)

        # Подпись «Разрешение» слева от кнопки
        lbl_res = self.font_label.render("Разрешение:", True, TEXT_COLOR)
        lbl_rect = lbl_res.get_rect()
        lbl_rect.left = self._right_x - 145
        lbl_rect.centery = self.res_btn.rect.centery
        surface.blit(lbl_res, lbl_rect)

        # Значение режима
        mode_text = DISPLAY_MODE_LABELS.get(
            self.game.settings.get("display_mode", DEFAULT_DISPLAY_MODE), "?"
        )
        self.mode_btn.draw(surface, mode_text)

        # Значение разрешения — в полном экране показываем «(нативное)»
        cur_mode = self.game.settings.get("display_mode")
        if cur_mode == FULLSCREEN_MODE:
            res_text = "(нативное)"
        else:
            rw, rh = self.game.settings["resolution"]
            res_text = f"{rw}×{rh}"
        self.res_btn.draw(surface, res_text)

        # ===== Секция «Управление» (слева ниже) =====
        sec_ctl = self.font_section.render("Управление", True, TEXT_COLOR)
        surface.blit(sec_ctl, (self._left_x, 315))

        mouse_pos = self.game._mouse_canvas_pos()
        for kb in self.key_buttons:
            listening = (self.listening_action == kb.action)
            hovered = kb.rect.collidepoint(mouse_pos) and not listening
            name = self.game.settings["keybinds"][kb.action]
            kb.draw(surface, binding_display(name), listening, hovered)

        # Подсказка в режиме прослушивания
        if self.listening_action:
            hint = self.font_hint.render(
                "Нажми клавишу или кнопку мыши…  (Esc — отмена)",
                True, (255, 220, 120),
            )
            surface.blit(hint, hint.get_rect(center=(WIDTH // 2, 560)))

        # ===== Нижние кнопки =====
        self.reset_button.draw(surface)
        self.back_button.draw(surface)

        # ===== Версия =====
        version_txt = self.font_version.render(f"v{VERSION}", True, (170, 170, 180))
        surface.blit(version_txt, version_txt.get_rect(bottomright=(WIDTH - 12, HEIGHT - 8)))