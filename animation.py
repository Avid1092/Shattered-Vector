"""Спрайт-листы, анимации и наборы состояний.

Поддерживает:
  "colorkey": [255, 0, 255] | "auto" | отсутствует
  "scale_to": [w, h]                — уменьшить каждый кадр

Отладочный лог: DEBUG = True.
"""
import os
import pygame

DEBUG = True  # ⚠️ поставь False, когда всё заработает


def _log(*args):
    if DEBUG:
        print("[animation]", *args)


class SpriteSheet:
    """Режет картинку на кадры по сетке frame_width x frame_height."""

    def __init__(self, image, frame_width, frame_height, scale_to=None):
        self.image = image
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.scale_to = scale_to
        self.frames = self._slice()

    def _slice(self):
        frames = []
        w, h = self.image.get_size()
        cols = max(1, w // self.frame_width)
        rows = max(1, h // self.frame_height)
        if w % self.frame_width or h % self.frame_height:
            _log(
                f"⚠ размер картинки {w}x{h} не делится нацело на кадр "
                f"{self.frame_width}x{self.frame_height}"
            )
        _log(f"сетка кадров: {cols}×{rows} (всего {cols * rows})")
        for row in range(rows):
            for col in range(cols):
                rect = pygame.Rect(
                    col * self.frame_width,
                    row * self.frame_height,
                    self.frame_width,
                    self.frame_height,
                )
                try:
                    frame = self.image.subsurface(rect).copy()
                except ValueError as e:
                    _log(f"subsurface провалился для {rect}: {e}")
                    continue
                if self.scale_to:
                    frame = pygame.transform.smoothscale(frame, self.scale_to)
                frames.append(frame)
        return frames


class Animation:
    """Последовательность кадров с FPS и опцией зацикливания."""

    def __init__(self, frames, fps=8, loop=True):
        self.frames = list(frames) if frames else []
        self.fps = max(1, int(fps))
        self.loop = loop
        self._frame_time = 1.0 / self.fps
        self._timer = 0.0
        self.index = 0
        self.finished = False

    def reset(self):
        self._timer = 0.0
        self.index = 0
        self.finished = False

    def update(self, dt):
        if not self.frames or (self.finished and not self.loop):
            return
        self._timer += dt
        while self._timer >= self._frame_time:
            self._timer -= self._frame_time
            self.index += 1
            if self.index >= len(self.frames):
                if self.loop:
                    self.index = 0
                else:
                    self.index = len(self.frames) - 1
                    self.finished = True
                    break

    def current_frame(self):
        return self.frames[self.index] if self.frames else None


class AnimationSet:
    """Набор анимаций + текущее состояние."""

    def __init__(self, animations):
        self.animations = animations
        self.current_name = None
        self.current = None

    def play(self, name, restart=False):
        if name not in self.animations:
            return
        if self.current_name == name and not restart:
            return
        self.current_name = name
        self.current = self.animations[name]
        self.current.reset()

    def update(self, dt):
        if self.current:
            self.current.update(dt)

    def frame(self):
        return self.current.current_frame() if self.current else None


def _apply_colorkey(image, ck):
    """Применить прозрачность по цвету. Возвращает (image, applied_color|None)."""
    if ck is None:
        return image, None
    if ck == "auto":
        color = image.get_at((0, 0))[:3]
    elif isinstance(ck, (list, tuple)) and len(ck) >= 3:
        color = (int(ck[0]), int(ck[1]), int(ck[2]))
    else:
        return image, None
    image.set_colorkey(color)
    return image, color


def load_animation_set(sprite_cfg, base_dir):
    """Собирает AnimationSet из секции "sprite" JSON-конфига.
    Возвращает None при любой проблеме — тогда рисуется прямоугольник.
    """
    if not sprite_cfg:
        return None

    sheet_rel = sprite_cfg.get("sheet")
    if not sheet_rel:
        _log("в sprite-конфиге нет поля 'sheet'")
        return None

    sheet_path = os.path.join(base_dir, sheet_rel)
    if not os.path.exists(sheet_path):
        _log(f"файл спрайта не найден: {sheet_path}")
        return None

    try:
        image = pygame.image.load(sheet_path).convert_alpha()
    except pygame.error as e:
        _log(f"не удалось загрузить {sheet_path}: {e}")
        return None

    image, applied_ck = _apply_colorkey(image, sprite_cfg.get("colorkey"))
    _log(f"спрайт загружен: {sheet_path}")
    _log(f"размер файла: {image.get_size()}, colorkey: {applied_ck}")

    frame_w = sprite_cfg.get("frame_width", image.get_width())
    frame_h = sprite_cfg.get("frame_height", image.get_height())
    scale_to = sprite_cfg.get("scale_to")
    if scale_to:
        scale_to = (int(scale_to[0]), int(scale_to[1]))
        _log(f"масштабирование кадров: -> {scale_to}")

    sheet = SpriteSheet(image, frame_w, frame_h, scale_to=scale_to)
    if not sheet.frames:
        _log("⚠ не получено ни одного кадра — фоллбэк на прямоугольник")
        return None

    animations = {}
    for name, anim_cfg in sprite_cfg.get("animations", {}).items():
        indices = anim_cfg.get("frames", [])
        frames = [sheet.frames[i] for i in indices if 0 <= i < len(sheet.frames)]
        if frames:
            animations[name] = Animation(
                frames,
                fps=anim_cfg.get("fps", 8),
                loop=anim_cfg.get("loop", True),
            )
        else:
            _log(f"анимация '{name}': ни один индекс {indices} не валиден "
                 f"(доступно кадров: {len(sheet.frames)})")

    # Fallback: если есть walk, но нет idle/jump/fall — берём кадр walk[0]
    if "walk" in animations:
        base_frame = animations["walk"].frames[0]
        for missing in ("idle", "jump", "fall"):
            if missing not in animations:
                animations[missing] = Animation([base_frame], fps=1, loop=False)
                _log(f"анимация '{missing}' отсутствовала — создана из walk[0]")

    if not animations:
        _log("⚠ нет ни одной валидной анимации — фоллбэк на прямоугольник")
        return None

    _log(f"готово. Анимации: {list(animations.keys())}")
    return AnimationSet(animations)