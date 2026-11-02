"""Глобальные настройки, пути к ресурсам, сохранение пользовательских настроек."""
import os
import json
import pygame

# --- Окно (дефолт и фоллбэк) ---
WIDTH, HEIGHT = 1280, 720
FPS = 60
TITLE = "Платформер"

# --- Версия проекта ---
VERSION = "0.1.0"

# --- Корень проекта ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Данные (контент) ---
DATA_DIR = os.path.join(BASE_DIR, "data")
MOBS_DIR = os.path.join(DATA_DIR, "mobs")
WORLD_DIR = os.path.join(DATA_DIR, "world")
SPRITES_DIR = os.path.join(DATA_DIR, "sprites")

# --- Игровые дефолты ---
DEFAULT_LEVEL = "level_01"
PLAYER_MOB = "player"

# --- Цвета UI ---
BG_COLOR = (30, 30, 40)
TEXT_COLOR = (240, 240, 240)
BUTTON_COLOR = (60, 60, 90)
BUTTON_HOVER = (90, 90, 140)

# --- Пользовательские настройки (в data/) ---
USER_SETTINGS_PATH = os.path.join(DATA_DIR, "user_settings.json")

DEFAULT_MUSIC_VOLUME = 0.7
DEFAULT_SFX_VOLUME = 0.8

# --- Режимы экрана ---
WINDOW_MODE = "window"
FULLSCREEN_MODE = "fullscreen"
BORDERLESS_MODE = "borderless"
DISPLAY_MODE_LABELS = {
    WINDOW_MODE: "Окно",
    FULLSCREEN_MODE: "Полный экран",
    BORDERLESS_MODE: "Без рамки",
}
DEFAULT_DISPLAY_MODE = WINDOW_MODE

# --- Разрешения ---
DEFAULT_RESOLUTIONS = [
    (1280, 720),
    (1366, 768),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
]
DEFAULT_RESOLUTION = (WIDTH, HEIGHT)


DEFAULT_KEYBINDS = {
    "left": "a",
    "right": "d",
    "jump": "space",
    "attack": "e",
    "roll": "s",
    "dash": "shift",
}

KEYBIND_LABELS = {
    "left": "Влево",
    "right": "Вправо",
    "jump": "Прыжок",
    "attack": "Удар",
    "roll": "Перекат",
    "dash": "Рывок",
}

# --- Мышиные бинды ---
MOUSE_BINDINGS = {
    "mouse_left": 1,
    "mouse_middle": 2,
    "mouse_right": 3,
    "mouse_x1": 4,
    "mouse_x2": 5,
}
MOUSE_DISPLAY = {
    1: "LMB",
    2: "MMB",
    3: "RMB",
    4: "M4",
    5: "M5",
}


def _generate_resolutions():
    """Базовые + режимы монитора. Без дублей, по возрастанию площади."""
    try:
        modes = pygame.display.list_modes() or []
    except pygame.error:
        modes = []
    out = set(DEFAULT_RESOLUTIONS)
    for m in modes:
        if isinstance(m, tuple) and len(m) == 2:
            w, h = int(m[0]), int(m[1])
            if w >= 800 and h >= 600:
                out.add((w, h))
    return sorted(out, key=lambda s: (s[0] * s[1], s[0]))


def default_settings():
    return {
        "music_volume": DEFAULT_MUSIC_VOLUME,
        "sfx_volume": DEFAULT_SFX_VOLUME,
        "display_mode": DEFAULT_DISPLAY_MODE,
        "resolution": list(DEFAULT_RESOLUTION),
        "keybinds": dict(DEFAULT_KEYBINDS),
    }


def load_user_settings():
    data = default_settings()
    if not os.path.exists(USER_SETTINGS_PATH):
        return data
    try:
        with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved.get("music_volume"), (int, float)):
            data["music_volume"] = max(0.0, min(1.0, float(saved["music_volume"])))
        if isinstance(saved.get("sfx_volume"), (int, float)):
            data["sfx_volume"] = max(0.0, min(1.0, float(saved["sfx_volume"])))

        mode = saved.get("display_mode")
        if mode in DISPLAY_MODE_LABELS:
            data["display_mode"] = mode

        res = saved.get("resolution")
        if (isinstance(res, (list, tuple)) and len(res) == 2
                and all(isinstance(x, (int, float)) and x > 0 for x in res)):
            data["resolution"] = [int(res[0]), int(res[1])]

        kb = saved.get("keybinds")
        if isinstance(kb, dict):
            for k, v in kb.items():
                if k in data["keybinds"] and isinstance(v, str) and v:
                    if v in MOUSE_BINDINGS or _is_known_key_name(v):
                        data["keybinds"][k] = v
    except (json.JSONDecodeError, OSError, ValueError) as e:
        print(f"[settings] не удалось загрузить {USER_SETTINGS_PATH}: {e}")
    return data


def save_user_settings(data):
    try:
        os.makedirs(os.path.dirname(USER_SETTINGS_PATH), exist_ok=True)
        with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[settings] не удалось сохранить настройки: {e}")


def _is_known_key_name(name):
    try:
        pygame.key.key_code(name)
        return True
    except (ValueError, AttributeError):
        return False


def is_mouse_binding(name):
    return isinstance(name, str) and name in MOUSE_BINDINGS


def binding_display(name):
    if is_mouse_binding(name):
        return MOUSE_DISPLAY[MOUSE_BINDINGS[name]]
    return str(name).upper()


def mouse_button_to_name(button):
    for name, btn in MOUSE_BINDINGS.items():
        if btn == button:
            return name
    return None


def key_name_to_code(name):
    try:
        return pygame.key.key_code(name)
    except (ValueError, AttributeError):
        return None


def binding_to_event(name):
    if is_mouse_binding(name):
        return ("mouse", MOUSE_BINDINGS[name])
    code = key_name_to_code(name)
    if code is not None:
        return ("key", code)
    return None


def resolve_keybinds(kb):
    resolved = {}
    for action, name in kb.items():
        ev = binding_to_event(name)
        if ev is None:
            print(f"[settings] не удалось распознать бинд {name!r} для {action!r}")
            continue
        resolved[action] = ev
    return resolved