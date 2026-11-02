"""Игровой класс: состояния, камера, главный цикл, режим разработчика."""
import os
# Важно для корректной работы FULLSCREEN на Windows — ставим ДО pygame.init()
os.environ.setdefault("SDL_VIDEO_CENTERED", "1")

import pygame

from settings import (
    WIDTH, HEIGHT, FPS, TITLE, TEXT_COLOR,
    WORLD_DIR, MOBS_DIR, DEFAULT_LEVEL, PLAYER_MOB,
    default_settings, load_user_settings, save_user_settings, resolve_keybinds,
    DISPLAY_MODE_LABELS, WINDOW_MODE, FULLSCREEN_MODE, BORDERLESS_MODE,
)
from menu import Menu, SettingsScreen
from world import World
from entities import Player, load_mob
from camera import Camera


class Game:
    STATE_MENU = "menu"
    STATE_SETTINGS = "settings"
    STATE_PLAYING = "playing"

    # Виртуальное разрешение, в котором рисуется ВСЁ (UI + мир).
    VIRTUAL_WIDTH = WIDTH
    VIRTUAL_HEIGHT = HEIGHT

    def __init__(self):
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error as e:
            print(f"[audio] mixer init failed: {e}")

        self.settings = load_user_settings()
        self.keybinds = resolve_keybinds(self.settings["keybinds"])
        self._mouse_extra = {4: False, 5: False}

        # 1) сначала создаём окно — без set_mode() pygame.Surface.convert() падает
        self.screen_size = (WIDTH, HEIGHT)
        self._create_window()

        # 2) теперь можно конвертировать canvas под формат дисплея (быстрее blit)
        self.canvas = pygame.Surface(
            (self.VIRTUAL_WIDTH, self.VIRTUAL_HEIGHT)
        ).convert()

        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.running = True
        self.state = self.STATE_MENU

        self.apply_audio_volumes()

        self.menu = Menu(self)
        self.settings_screen = SettingsScreen(self)

        self.world = None
        self.player = None
        self.camera = None
        self.hud_font = pygame.font.SysFont("consolas", 18)
        self.debug_font = pygame.font.SysFont("consolas", 16)

        self.debug = False
        self.current_level = DEFAULT_LEVEL
        self.fps_value = 0.0

    # --- Окно и разрешение ---
    def _create_window(self):
        """Создать/пересоздать окно по display_mode + resolution."""
        mode = self.settings.get("display_mode", WINDOW_MODE)
        res = self.settings.get("resolution", [WIDTH, HEIGHT])
        rw, rh = int(res[0]), int(res[1])

        try:
            if mode == FULLSCREEN_MODE:
                info = pygame.display.Info()
                desktop = (info.current_w, info.current_h)
                if desktop[0] <= 0 or desktop[1] <= 0:
                    desktop = (rw, rh)
                self.screen = pygame.display.set_mode(desktop, pygame.FULLSCREEN)
            elif mode == BORDERLESS_MODE:
                self.screen = pygame.display.set_mode((rw, rh), pygame.NOFRAME)
            else:
                self.screen = pygame.display.set_mode((rw, rh))
        except pygame.error as e:
            print(f"[display] set_mode упал ({e}); фоллбэк на окно 1280×720")
            self.screen = pygame.display.set_mode((WIDTH, HEIGHT))

        self.screen_size = self.screen.get_size()

        # Canvas пересоздаём только если он уже существует (при смене режима).
        # На первом вызове его ещё нет — создастся после.
        if hasattr(self, "canvas") and self.canvas is not None:
            self.canvas = pygame.Surface(
                (self.VIRTUAL_WIDTH, self.VIRTUAL_HEIGHT)
            ).convert()

    def apply_display_mode(self):
        """Применить текущий display_mode + resolution."""
        self._create_window()
        if self.player is not None and self.camera is not None:
            self.camera.snap_to(self.player.rect)

    # --- Настройки ---
    def apply_audio_volumes(self):
        try:
            pygame.mixer.music.set_volume(float(self.settings["music_volume"]))
        except pygame.error:
            pass

    def save_settings(self):
        save_user_settings(self.settings)

    def reset_settings_to_default(self):
        self.settings = default_settings()
        self.keybinds = resolve_keybinds(self.settings["keybinds"])
        self.apply_audio_volumes()
        self.apply_display_mode()

    def resolve_keybinds(self):
        self.keybinds = resolve_keybinds(self.settings["keybinds"])

    # --- Управление состояниями ---
    def start_game(self):
        level_path = os.path.join(WORLD_DIR, f"{self.current_level}.json")
        self.world = World(level_path, MOBS_DIR)
        player_cfg = load_mob(MOBS_DIR, PLAYER_MOB)
        sx, sy = self.world.spawn
        self.player = Player(sx, sy, player_cfg, sprite_base_dir=MOBS_DIR)
        self.camera = Camera(
            self.VIRTUAL_WIDTH, self.VIRTUAL_HEIGHT,
            self.world.width, self.world.height,
        )
        self.camera.snap_to(self.player.rect)
        self.state = self.STATE_PLAYING

    def open_settings(self):
        self.settings_screen = SettingsScreen(self)
        self.settings_screen.sync_from_game()
        self.state = self.STATE_SETTINGS

    def open_menu(self):
        self.state = self.STATE_MENU

    def quit(self):
        self.save_settings()
        self.running = False

    def respawn_player(self):
        if not (self.player and self.world and self.camera):
            return
        sx, sy = self.world.spawn
        self.player.pos.update(sx, sy)
        self.player.velocity.update(0, 0)
        self.player.jumps_used = 0
        if self.player.rolling:
            self.player._interrupt_roll()
        self.player.dashing = False
        self.player.dash_timer = 0.0
        self.player.sync_rect()
        self.camera.snap_to(self.player.rect)

    # --- Ввод ---
    def _try_action_from_binding(self, kind, value):
        if not self.player:
            return
        target = (kind, value)
        if self.keybinds.get("jump") == target:
            self.player.try_jump()
        elif self.keybinds.get("attack") == target:
            self.player.try_attack()
        elif self.keybinds.get("roll") == target:
            self.player.try_roll()
        elif self.keybinds.get("dash") == target:
            self.player.try_dash()

    def _get_pressed_state(self):
        keys = pygame.key.get_pressed()
        mouse = pygame.mouse.get_pressed(num_buttons=3)
        state = {}
        for action, binding in self.keybinds.items():
            kind, value = binding
            if kind == "key":
                state[action] = bool(keys[value])
            elif kind == "mouse":
                if 1 <= value <= 3:
                    state[action] = bool(mouse[value - 1])
                else:
                    state[action] = self._mouse_extra.get(value, False)
            else:
                state[action] = False
        return state

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit()
                return

            if event.type == pygame.WINDOWFOCUSLOST:
                for k in self._mouse_extra:
                    self._mouse_extra[k] = False
                continue

            # Координаты мыши из реального окна → в canvas-пространство
            if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN,
                              pygame.MOUSEBUTTONUP):
                event = self._translate_mouse_event(event)

            if self.state == self.STATE_MENU:
                self.menu.handle_event(event)
            elif self.state == self.STATE_SETTINGS:
                self.settings_screen.handle_event(event)
            elif self.state == self.STATE_PLAYING:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.open_menu()
                    elif event.key == pygame.K_F1:
                        self.debug = not self.debug
                    else:
                        self._try_action_from_binding("key", event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button in self._mouse_extra:
                        self._mouse_extra[event.button] = True
                    self._try_action_from_binding("mouse", event.button)
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button in self._mouse_extra:
                        self._mouse_extra[event.button] = False

    # --- Координаты мыши ---
    def _compute_viewport(self):
        sw, sh = self.screen_size
        vw, vh = self.VIRTUAL_WIDTH, self.VIRTUAL_HEIGHT
        if sw <= 0 or sh <= 0:
            return 0, 0, 1.0
        scale = min(sw / vw, sh / vh)
        out_w = int(vw * scale)
        out_h = int(vh * scale)
        ox = (sw - out_w) // 2
        oy = (sh - out_h) // 2
        return ox, oy, scale

    def _translate_mouse_event(self, event):
        ox, oy, scale = self._compute_viewport()
        if scale <= 0:
            return event
        if event.type == pygame.MOUSEMOTION:
            mx = (event.pos[0] - ox) / scale
            my = (event.pos[1] - oy) / scale
            rel_x = event.rel[0] / scale
            rel_y = event.rel[1] / scale
            return pygame.event.Event(
                event.type,
                {"pos": (mx, my), "rel": (rel_x, rel_y),
                 "buttons": event.buttons},
            )
        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            mx = (event.pos[0] - ox) / scale
            my = (event.pos[1] - oy) / scale
            return pygame.event.Event(
                event.type,
                {"pos": (mx, my), "button": event.button},
            )
        return event

    def _mouse_canvas_pos(self):
        ox, oy, scale = self._compute_viewport()
        if scale <= 0:
            return (0, 0)
        mx, my = pygame.mouse.get_pos()
        return ((mx - ox) / scale, (my - oy) / scale)

    def update(self, dt):
        if self.state == self.STATE_PLAYING and self.player and self.world:
            self.player.handle_input(self._get_pressed_state())
            self.player.update(dt, self.world)
            self.world.apply_player_attack(self.player)
            self.world.update(dt)
            self.camera.update(self.player.rect, dt)

            if self.player.rect.top > self.world.height + 200:
                self.respawn_player()

    def draw(self):
        if self.state == self.STATE_MENU:
            self.menu.draw(self.canvas)
        elif self.state == self.STATE_SETTINGS:
            self.settings_screen.draw(self.canvas)
        elif self.state == self.STATE_PLAYING:
            if self.world:
                self.world.draw(self.canvas, self.camera, debug=self.debug)
            if self.player:
                self.player.draw(self.canvas, self.camera, debug=self.debug)
            self._draw_hud()
            if self.debug:
                self._draw_debug_overlay()

        self._blit_canvas_to_screen()
        pygame.display.flip()

    def _blit_canvas_to_screen(self):
        sw, sh = self.screen_size
        ox, oy, scale = self._compute_viewport()
        self.screen.fill((0, 0, 0))  # letterbox-поля
        if scale <= 0:
            return
        out_w = int(self.VIRTUAL_WIDTH * scale)
        out_h = int(self.VIRTUAL_HEIGHT * scale)
        if (out_w, out_h) == (self.VIRTUAL_WIDTH, self.VIRTUAL_HEIGHT):
            scaled = self.canvas
        else:
            scaled = pygame.transform.smoothscale(self.canvas, (out_w, out_h))
        self.screen.blit(scaled, (ox, oy))

    def _draw_hud(self):
        if not (self.player and self.world):
            return
        self.fps_value = self.clock.get_fps()
        p = self.player
        cd = p.attack_cooldown_timer
        rcd = p.roll_cooldown_timer
        dcd = p.dash_cooldown_timer
        jumps_left = p.max_jumps - p.jumps_used
        mode_label = DISPLAY_MODE_LABELS.get(self.settings["display_mode"], "?")
        info = (
            f"{mode_label} {self.screen_size[0]}×{self.screen_size[1]}  "
            f"X: {int(p.pos.x)}  Y: {int(p.pos.y)}  "
            f"Ящиков: {len(self.world.crates)}  Слизней: {len(self.world.slimes)}  "
            f"Удар: {'ok' if cd <= 0 else f'{cd:.2f}'}  "
            f"Перекат: {'ok' if rcd <= 0 else f'{rcd:.2f}'}  "
            f"Рывок: {'ok' if dcd <= 0 else f'{dcd:.2f}'}  "
            f"Прыжков: {jumps_left}/{p.max_jumps}"
        )
        txt = self.hud_font.render(info, True, TEXT_COLOR)
        self.canvas.blit(txt, (10, 10))

        if self.debug:
            dbg = (
                f"[DEV] FPS: {self.fps_value:.1f}   "
                f"vel: ({p.velocity.x:.0f}, {p.velocity.y:.0f})   "
                f"on_ground: {p.on_ground}   facing: {p.facing}   "
                f"attacking: {p.attacking}   rolling: {p.rolling}   dashing: {p.dashing}   "
                f"rect_h: {p.rect.height}   jumps_used: {p.jumps_used}   "
                f"level: {self.current_level}   [F1] выкл"
            )
            dtxt = self.debug_font.render(dbg, True, (255, 255, 0))
            self.canvas.blit(dtxt, (10, 34))

    def _draw_debug_overlay(self):
        if not (self.world and self.camera):
            return
        sx, sy = self.world.spawn
        cx = sx - round(self.camera.offset.x)
        cy = sy - round(self.camera.offset.y)
        color = (255, 80, 255)
        pygame.draw.line(self.canvas, color, (cx - 8, cy), (cx + 8, cy), 2)
        pygame.draw.line(self.canvas, color, (cx, cy - 8), (cx, cy + 8), 2)

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.handle_events()
            self.update(dt)
            self.draw()
        pygame.quit()