"""Мир: платформы, ящики, слизни, гравитация, спавн, границы, удар."""
import json
import os
import pygame

from entities import Crate, Slime, load_mob


MOB_CLASS_MAP = {
    "crate": Crate,
    "slime": Slime,
}


class Platform:
    def __init__(self, x, y, w, h, color, image=None):
        self.rect = pygame.Rect(int(x), int(y), int(w), int(h))
        self.color = color
        self.image = image

    def draw(self, surface, camera, debug=False):
        screen_rect = self.rect.copy()
        screen_rect.x -= round(camera.offset.x)
        screen_rect.y -= round(camera.offset.y)

        if screen_rect.right < 0 or screen_rect.left > surface.get_width():
            return
        if screen_rect.bottom < 0 or screen_rect.top > surface.get_height():
            return

        if self.image is not None:
            img = pygame.transform.scale(self.image, (self.rect.width, self.rect.height))
            surface.blit(img, screen_rect)
        else:
            pygame.draw.rect(surface, self.color, screen_rect, border_radius=4)

        if debug:
            pygame.draw.rect(surface, (0, 255, 0), screen_rect, 1)


class World:
    def __init__(self, path, mobs_dir):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.gravity = data.get("gravity", 2000)
        self.background = tuple(data.get("background", (135, 206, 235)))
        self.spawn = tuple(data.get("spawn", (100, 100)))
        self.width = int(data.get("width", 1280))
        self.height = int(data.get("height", 720))
        default_color = tuple(data.get("platform_color", (80, 80, 80)))

        base_dir = os.path.dirname(path)
        self._mobs_dir = mobs_dir

        tile_cfg = data.get("tile_sprite")
        default_image = self._try_load(tile_cfg, base_dir, "тайл уровня")

        self.platforms = []
        for p in data.get("platforms", []):
            color = tuple(p.get("color", default_color))
            image = default_image
            if "sprite" in p:
                image = self._try_load(p["sprite"], base_dir, "тайл платформы")
            self.platforms.append(Platform(p["x"], p["y"], p["w"], p["h"], color, image))

        self.crates = []
        for c in data.get("crates", []):
            obj = self._spawn_mob(c, default="crate")
            if obj is not None:
                self.crates.append(obj)

        self.slimes = []
        for s in data.get("slimes", []):
            obj = self._spawn_mob(s, default="slime")
            if obj is not None:
                self.slimes.append(obj)

    def _spawn_mob(self, entry, default="crate"):
        """Создать сущность из записи уровня {mob, x, y} через MOB_CLASS_MAP."""
        mob_id = entry.get("mob", default)
        cls = MOB_CLASS_MAP.get(mob_id)
        if cls is None:
            print(f"[world] неизвестный mob: {mob_id!r} (нет в MOB_CLASS_MAP)")
            return None
        try:
            cfg = load_mob(self._mobs_dir, mob_id)
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            print(f"[world] не удалось загрузить конфиг {mob_id}: {e}")
            return None
        return cls(entry["x"], entry["y"], cfg, sprite_base_dir=self._mobs_dir)

    @staticmethod
    def _try_load(rel_path, base_dir, label):
        if not rel_path:
            return None
        img_path = os.path.join(base_dir, rel_path)
        if not os.path.exists(img_path):
            return None
        try:
            return pygame.image.load(img_path).convert_alpha()
        except pygame.error as e:
            print(f"[world] не удалось загрузить {label} {img_path}: {e}")
            return None

    def platform_rects(self):
        return [p.rect for p in self.platforms]

    def solid_rects(self, exclude=None):
        rects = [p.rect for p in self.platforms]
        for c in self.crates:
            if c.dead or c is exclude:
                continue
            rects.append(c.rect)
        return rects

    def apply_player_attack(self, player):
        if player is None:
            return
        zone = player.get_attack_rect()
        if zone is None:
            return

        targets = []
        targets.extend(self.crates)
        targets.extend(self.slimes)

        for t in targets:
            if getattr(t, "dead", False):
                continue
            if not hasattr(t, "take_damage"):
                continue
            if id(t) in player.attack_hit_set:
                continue
            if zone.colliderect(t.rect):
                t.take_damage(player.attack_damage)
                player.attack_hit_set.add(id(t))

    def update(self, dt):
        for c in self.crates:
            if not c.dead:
                c.update(dt, self)
        self.crates = [c for c in self.crates if not c.dead]

        for s in self.slimes:
            if not s.dead:
                s.update(dt, self)
        self.slimes = [
            s for s in self.slimes
            if not s.dead and s.rect.top < self.height + 400
        ]

    def draw(self, surface, camera, debug=False):
        surface.fill(self.background)
        for p in self.platforms:
            p.draw(surface, camera, debug=debug)
        for c in self.crates:
            c.draw(surface, camera, debug=debug)
        for s in self.slimes:
            s.draw(surface, camera, debug=debug)