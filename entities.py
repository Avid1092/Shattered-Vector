"""Сущности: базовый класс, игрок, ящик, слизень. Спрайты и анимации."""
import os
import json
import copy
import random
import pygame

from animation import load_animation_set


# ---------- Загрузка конфигов мобов из единого mobs.json ----------
MOBS_FILENAME = "mobs.json"
_mobs_cache = {}


def _load_mobs_file(mobs_dir):
    key = os.path.abspath(mobs_dir)
    if key in _mobs_cache:
        return _mobs_cache[key]
    path = os.path.join(mobs_dir, MOBS_FILENAME)
    if not os.path.exists(path):
        raise FileNotFoundError(f"не найден {MOBS_FILENAME}: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _mobs_cache[key] = data
    return data


def load_mob(mobs_dir, mob_id):
    data = _load_mobs_file(mobs_dir)
    if mob_id not in data:
        raise KeyError(
            f"моб {mob_id!r} отсутствует в {MOBS_FILENAME}. "
            f"Доступные: {list(data.keys())}"
        )
    return copy.deepcopy(data[mob_id])


class Entity:
    """Базовый класс: AABB-коллайдер, физика, анимации."""

    def __init__(self, x, y, width, height, config=None, sprite_base_dir=None):
        self.config = config or {}
        self.pos = pygame.Vector2(x, y)
        self.rect = pygame.Rect(int(x), int(y), int(width), int(height))
        self.velocity = pygame.Vector2(0, 0)
        self.on_ground = False
        self.facing = 1
        self.color = tuple(self.config.get("color", (200, 50, 50)))
        self.dead = False

        sprite_cfg = self.config.get("sprite") or {}
        off = sprite_cfg.get("offset", (0, 0))
        self.sprite_offset = (int(off[0]), int(off[1]))

        self.anims = None
        if sprite_base_dir and config:
            self.anims = load_animation_set(config.get("sprite"), sprite_base_dir)
        if self.anims and self.anims.animations:
            first = "idle" if "idle" in self.anims.animations else next(iter(self.anims.animations))
            self.anims.play(first)
        else:
            self.anims = None

    def sync_rect(self):
        self.rect.x = round(self.pos.x)
        self.rect.y = round(self.pos.y)

    def update(self, dt, world):
        pass

    def play_anim(self, name, restart=False):
        if self.anims:
            self.anims.play(name, restart)

    def update_animation(self, dt):
        if self.anims:
            self.anims.update(dt)

    def draw(self, surface, camera, debug=False):
        screen_rect = self.rect.copy()
        screen_rect.x -= round(camera.offset.x)
        screen_rect.y -= round(camera.offset.y)

        frame = self.anims.frame() if self.anims else None
        if frame is None:
            pygame.draw.rect(surface, self.color, screen_rect, border_radius=6)
        else:
            if self.facing < 0:
                frame = pygame.transform.flip(frame, True, False)
            draw_rect = frame.get_rect(center=screen_rect.center)
            draw_rect.x += self.sprite_offset[0]
            draw_rect.y += self.sprite_offset[1]
            surface.blit(frame, draw_rect)

        if debug:
            pygame.draw.rect(surface, (255, 0, 0), screen_rect, 1)
            cx, cy = screen_rect.center
            pygame.draw.line(surface, (255, 255, 0), (cx - 4, cy), (cx + 4, cy), 1)
            pygame.draw.line(surface, (255, 255, 0), (cx, cy - 4), (cx, cy + 4), 1)
            pygame.draw.line(
                surface, (0, 255, 255),
                (cx, cy),
                (cx + self.velocity.x * 0.1, cy + self.velocity.y * 0.1),
                2,
            )


class Player(Entity):
    """Игрок: движение, прыжок (двойной), удар, перекат, рывок.

    Перекат и рывок можно прервать любым другим действием:
    - прыжок прерывает перекат (hitbox восстанавливается, если есть место);
    - прыжок прерывает рывок;
    - атака прерывает и перекат, и рывок;
    - рывок прерывает перекат;
    - перекат прерывает рывок (если на земле).
    Кулдаун при прерывании не сбрасывается — он тикает с момента старта.
    """

    def __init__(self, x, y, config, sprite_base_dir=None):
        super().__init__(x, y, config["width"], config["height"], config, sprite_base_dir)
        self.speed = config.get("speed", 300)
        self.jump_power = config.get("jump_power", 700)
        self.double_jump_power = config.get("double_jump_power", self.jump_power)
        self.max_jumps = max(1, int(config.get("max_jumps", 2)))
        self.jumps_used = 0
        self.max_fall_speed = config.get("max_fall_speed", 1200)

        # --- Перекат ---
        self.roll_speed = float(config.get("roll_speed", self.speed * 1.6))
        self.roll_duration = float(config.get("roll_duration", 0.35))
        self.roll_cooldown = float(config.get("roll_cooldown", 0.55))
        self.roll_height_scale = float(config.get("roll_height_scale", 0.5))
        self.rolling = False
        self.roll_timer = 0.0
        self.roll_cooldown_timer = 0.0
        self._roll_dir = 1
        self._roll_restore_h = None
        self._pending_roll_exit = False

        # --- Рывок ---
        self.dash_speed = float(config.get("dash_speed", self.speed * 3))
        self.dash_duration = float(config.get("dash_duration", 0.16))
        self.dash_cooldown = float(config.get("dash_cooldown", 0.6))
        self.dashing = False
        self.dash_timer = 0.0
        self.dash_cooldown_timer = 0.0
        self._dash_dir = 1

        # --- Урон от падения ---
        self.fall_damage_speed = float(config.get("fall_damage_speed", 1200))
        self.fall_damage_amount = int(config.get("fall_damage_amount", 10))
        self.fall_damage_immunity_this_landing = False
        self._prev_vy_after_gravity = 0.0

        # --- Атака ---
        atk = config.get("attack", {}) or {}
        self.attack_damage = int(atk.get("damage", 10))
        self.attack_range = int(atk.get("range", 56))
        self.attack_height = int(atk.get("height", 50))
        self.attack_duration = float(atk.get("duration", 0.15))
        self.attack_cooldown = float(atk.get("cooldown", 0.35))
        self.attack_recoil = float(atk.get("recoil", 0))
        self.attack_show_zone = bool(atk.get("show_zone", True))

        self.attacking = False
        self.attack_timer = 0.0
        self.attack_cooldown_timer = 0.0
        self.attack_hit_set = set()

    # ---------- Прерывания ----------
    def _interrupt_roll(self):
        """Прервать перекат. Восстановить hitbox, если места хватает."""
        if not self.rolling:
            return
        self.rolling = False
        self.roll_timer = 0.0
        # помечаем, что пора разжаться; фактическое разжатие — в update()
        self._pending_roll_exit = True

    def _interrupt_dash(self):
        if not self.dashing:
            return
        self.dashing = False
        self.dash_timer = 0.0

    # ---------- Прыжок ----------
    def can_jump(self):
        return self.jumps_used < self.max_jumps

    def try_jump(self):
        if not self.can_jump():
            return False
        # прерываем перекат/рывок — прыжок приоритетнее
        self._interrupt_roll()
        self._interrupt_dash()
        power = self.jump_power if self.jumps_used == 0 else self.double_jump_power
        self.velocity.y = -power
        self.jumps_used += 1
        self.on_ground = False
        return True

    # ---------- Атака ----------
    def can_attack(self):
        # атака разрешена всегда, кроме активной атаки и кулдауна
        return not self.attacking and self.attack_cooldown_timer <= 0.0

    def try_attack(self):
        if not self.can_attack():
            return False
        self._interrupt_roll()
        self._interrupt_dash()
        self.attacking = True
        self.attack_timer = self.attack_duration
        self.attack_cooldown_timer = self.attack_cooldown
        self.attack_hit_set.clear()
        self.play_anim("attack", restart=True)
        if self.attack_recoil > 0:
            self.velocity.x = -self.facing * self.attack_recoil
        return True

    def get_attack_rect(self):
        if not self.attacking:
            return None
        if self.facing >= 0:
            x = self.rect.right
        else:
            x = self.rect.left - self.attack_range
        y = self.rect.centery - self.attack_height // 2
        return pygame.Rect(x, y, self.attack_range, self.attack_height)

    # ---------- Перекат ----------
    def can_roll(self):
        return (self.on_ground and not self.rolling
                and self.roll_cooldown_timer <= 0.0)

    def try_roll(self):
        if not self.can_roll():
            return False
        self._interrupt_dash()
        self._start_roll(self.facing)
        return True

    def _start_roll(self, direction):
        self.rolling = True
        self.roll_timer = self.roll_duration
        self.roll_cooldown_timer = self.roll_cooldown
        self._roll_dir = 1 if direction >= 0 else -1
        self.facing = self._roll_dir
        self._shrink_hitbox_for_roll()
        self.play_anim("roll", restart=True)

    def _shrink_hitbox_for_roll(self):
        if self._roll_restore_h is None:
            self._roll_restore_h = self.rect.height
        bottom = self.rect.bottom
        new_h = max(8, int(round(self._roll_restore_h * self.roll_height_scale)))
        self.rect.height = new_h
        self.rect.bottom = bottom
        self.pos.x = self.rect.x
        self.pos.y = self.rect.y

    def _try_exit_roll(self, world):
        """Восстановить hitbox после переката, если есть место. Иначе — отложить."""
        if not self._pending_roll_exit or self._roll_restore_h is None:
            return
        bottom = self.rect.bottom
        old_h = self.rect.height
        new_h = self._roll_restore_h
        test = pygame.Rect(self.rect.x, bottom - new_h, self.rect.width, new_h)
        solids = world.solid_rects(exclude=None)
        blocked = any(test.colliderect(p) for p in solids)
        if blocked:
            allowed = old_h
            for h in range(new_h, old_h, -1):
                t = pygame.Rect(self.rect.x, bottom - h, self.rect.width, h)
                if not any(t.colliderect(p) for p in solids):
                    allowed = h
                    break
            if allowed > old_h:
                self.rect.height = allowed
                self.rect.bottom = bottom
                self.pos.x = self.rect.x
                self.pos.y = self.rect.y
            return
        self.rect.height = new_h
        self.rect.bottom = bottom
        self.pos.x = self.rect.x
        self.pos.y = self.rect.y
        self._roll_restore_h = None
        self._pending_roll_exit = False

    # ---------- Рывок ----------
    def can_dash(self):
        return (not self.dashing
                and self.dash_cooldown_timer <= 0.0)

    def try_dash(self):
        if not self.can_dash():
            return False
        self._interrupt_roll()
        self.dashing = True
        self.dash_timer = self.dash_duration
        self.dash_cooldown_timer = self.dash_cooldown
        self._dash_dir = 1 if self.facing >= 0 else -1
        self.play_anim("dash", restart=True)
        return True

    # ---------- Ввод ----------
    def handle_input(self, state):
        self.velocity.x = 0
        if state.get("left"):
            self.velocity.x -= self.speed
            self.facing = -1
        if state.get("right"):
            self.velocity.x += self.speed
            self.facing = 1

    # ---------- Обновление ----------
    def update(self, dt, world):
        # Таймеры
        if self.attack_cooldown_timer > 0:
            self.attack_cooldown_timer = max(0.0, self.attack_cooldown_timer - dt)
        if self.roll_cooldown_timer > 0:
            self.roll_cooldown_timer = max(0.0, self.roll_cooldown_timer - dt)
        if self.dash_cooldown_timer > 0:
            self.dash_cooldown_timer = max(0.0, self.dash_cooldown_timer - dt)

        if self.attacking:
            self.attack_timer -= dt
            if self.attack_timer <= 0:
                self.attacking = False
                self.attack_timer = 0.0

        if self.rolling:
            self.roll_timer -= dt
            if self.roll_timer <= 0:
                self.rolling = False
                self.roll_timer = 0.0
                self._pending_roll_exit = True

        if self.dashing:
            self.dash_timer -= dt
            if self.dash_timer <= 0:
                self.dashing = False
                self.dash_timer = 0.0

        # Горизонтальная скорость
        if self.rolling:
            self.velocity.x = self.roll_speed * self._roll_dir
        elif self.dashing:
            self.velocity.x = self.dash_speed * self._dash_dir
        # иначе — обычное управление из handle_input

        # Гравитация
        self.velocity.y += world.gravity * dt
        if self.dashing:
            self.velocity.y *= 0.5
        if self.velocity.y > self.max_fall_speed:
            self.velocity.y = self.max_fall_speed

        self._prev_vy_after_gravity = self.velocity.y
        self.fall_damage_immunity_this_landing = self.rolling

        solids = world.solid_rects(exclude=None)

        # X
        self.pos.x += self.velocity.x * dt
        self.sync_rect()
        self._resolve_collisions(solids, axis="x")
        self.pos.x = self.rect.x

        # Y
        self.pos.y += self.velocity.y * dt
        self.sync_rect()
        self.on_ground = False
        self._resolve_collisions(solids, axis="y")
        self.pos.y = self.rect.y

        if self.on_ground:
            self.jumps_used = 0

        # Пытаемся «разжаться» после переката — и когда он завершился сам,
        # и когда его прервали. Если сейчас места нет — восстановим позже.
        self._try_exit_roll(world)

        self._maybe_fall_damage()

        self._update_anim_state()
        self.update_animation(dt)

    def _maybe_fall_damage(self):
        """Урон от падения. Гасится перекатом в момент приземления."""
        if not self.on_ground:
            return
        if self._prev_vy_after_gravity <= self.fall_damage_speed:
            return
        if self.fall_damage_immunity_this_landing:
            return
        # Заглушка: HP игрока пока нет.
        # Когда появится — здесь будет self.take_damage(self.fall_damage_amount).

    def _update_anim_state(self):
        if not self.anims:
            return
        if self.rolling:
            self.play_anim("roll")
            return
        if self.dashing:
            self.play_anim("dash")
            return
        if self.attacking:
            self.play_anim("attack")
            return
        if not self.on_ground:
            self.play_anim("jump" if self.velocity.y < 0 else "fall")
        elif abs(self.velocity.x) > 1:
            self.play_anim("walk")
        else:
            self.play_anim("idle")

    def _resolve_collisions(self, solids, axis):
        for p in solids:
            if not self.rect.colliderect(p):
                continue
            if axis == "x":
                if self.velocity.x > 0:
                    self.rect.right = p.left
                elif self.velocity.x < 0:
                    self.rect.left = p.right
                self.velocity.x = 0
            else:
                if self.velocity.y > 0:
                    self.rect.bottom = p.top
                    self.on_ground = True
                elif self.velocity.y < 0:
                    self.rect.top = p.bottom
                self.velocity.y = 0

    def draw(self, surface, camera, debug=False):
        super().draw(surface, camera, debug=debug)
        if self.attacking and self.attack_show_zone:
            zone = self.get_attack_rect()
            if zone:
                sr = zone.copy()
                sr.x -= round(camera.offset.x)
                sr.y -= round(camera.offset.y)
                overlay = pygame.Surface(sr.size, pygame.SRCALPHA)
                overlay.fill((255, 220, 80, 90))
                surface.blit(overlay, sr.topleft)
                pygame.draw.rect(surface, (255, 200, 0), sr, 2)


class Crate(Entity):
    """Твёрдый блок с HP."""

    def __init__(self, x, y, config, sprite_base_dir=None):
        super().__init__(x, y, config["width"], config["height"], config, sprite_base_dir)
        self.max_hp = int(config.get("max_hp", 20))
        self.hp = self.max_hp
        self.max_fall_speed = 1400
        self.damage_on_fall_speed = float(config.get("damage_on_fall_speed", 900))
        self.damage_on_fall_amount = int(config.get("damage_on_fall_amount", 0))
        self._prev_vy = 0.0
        self.hit_flash = 0.0

    def take_damage(self, amount):
        if amount <= 0 or self.dead:
            return
        self.hp -= int(amount)
        self.hit_flash = 0.15
        if self.hp <= 0:
            self.hp = 0
            self.dead = True

    def update(self, dt, world):
        self.hit_flash = max(0.0, self.hit_flash - dt)

        self.velocity.y += world.gravity * dt
        if self.velocity.y > self.max_fall_speed:
            self.velocity.y = self.max_fall_speed

        solids = world.solid_rects(exclude=self)

        self._prev_vy = self.velocity.y
        self.pos.y += self.velocity.y * dt
        self.sync_rect()
        self.on_ground = False
        self._resolve_collisions(solids, axis="y")
        self.pos.y = self.rect.y

        if self.on_ground and self._prev_vy > self.damage_on_fall_speed and self.damage_on_fall_amount > 0:
            self.take_damage(self.damage_on_fall_amount)

        self.update_animation(dt)

    def _resolve_collisions(self, solids, axis):
        for p in solids:
            if not self.rect.colliderect(p):
                continue
            if axis == "y":
                if self.velocity.y > 0:
                    self.rect.bottom = p.top
                    self.on_ground = True
                elif self.velocity.y < 0:
                    self.rect.top = p.bottom
                self.velocity.y = 0

    def draw(self, surface, camera, debug=False):
        super().draw(surface, camera, debug=debug)

        if self.hit_flash > 0:
            screen_rect = self.rect.copy()
            screen_rect.x -= round(camera.offset.x)
            screen_rect.y -= round(camera.offset.y)
            overlay = pygame.Surface(screen_rect.size, pygame.SRCALPHA)
            overlay.fill((255, 80, 80, int(120 * (self.hit_flash / 0.15))))
            surface.blit(overlay, screen_rect.topleft)

        self._draw_hp_bar(surface, camera)

    def _draw_hp_bar(self, surface, camera):
        if self.max_hp <= 0:
            return
        w = self.rect.width
        h = 6
        x = self.rect.x - round(camera.offset.x)
        y = self.rect.y - round(camera.offset.y) - h - 4
        if y + h < 0 or y > surface.get_height():
            return

        pygame.draw.rect(surface, (40, 0, 0), (x, y, w, h), border_radius=2)
        ratio = max(0.0, self.hp / self.max_hp)
        fill_w = int(w * ratio)
        if fill_w > 0:
            color = (220, 40, 40) if ratio > 0.3 else (255, 160, 40)
            pygame.draw.rect(surface, color, (x, y, fill_w, h), border_radius=2)
        pygame.draw.rect(surface, (0, 0, 0), (x, y, w, h), 1, border_radius=2)


class Slime(Entity):
    """Слизень: физика, патрулирование влево-вправо, урон от удара, анимации."""

    def __init__(self, x, y, config, sprite_base_dir=None):
        super().__init__(x, y, config["width"], config["height"], config, sprite_base_dir)
        self.max_hp = int(config.get("max_hp", 20))
        self.hp = self.max_hp
        self.speed = float(config.get("speed", 100))
        self.patrol_distance = float(config.get("patrol_distance", 150))
        self.jump_power = float(config.get("jump_power", 400))
        self.jump_chance = float(config.get("jump_chance", 0.0))
        self.ledge_detection = bool(config.get("ledge_detection", True))
        self.max_fall_speed = float(config.get("max_fall_speed", 1400))
        self.damage_on_fall_speed = float(config.get("damage_on_fall_speed", 900))
        self.damage_on_fall_amount = int(config.get("damage_on_fall_amount", 0))

        self.direction = 1
        self.facing = 1
        self._traveled = 0.0
        self._prev_vy = 0.0
        self.hit_flash = 0.0

    def take_damage(self, amount):
        if amount <= 0 or self.dead:
            return
        self.hp -= int(amount)
        self.hit_flash = 0.15
        if self.hp <= 0:
            self.hp = 0
            self.dead = True

    def update(self, dt, world):
        self.hit_flash = max(0.0, self.hit_flash - dt)

        solids = world.solid_rects(exclude=self)

        self.velocity.y += world.gravity * dt
        if self.velocity.y > self.max_fall_speed:
            self.velocity.y = self.max_fall_speed

        if self.on_ground:
            if self._traveled >= self.patrol_distance:
                self.direction *= -1
                self._traveled = 0.0

            if self.ledge_detection:
                probe_x = self.rect.right + 2 if self.direction > 0 else self.rect.left - 6
                probe = pygame.Rect(probe_x, self.rect.bottom + 2, 4, 8)
                if not any(probe.colliderect(p) for p in solids):
                    self.direction *= -1
                    self._traveled = 0.0

            self.facing = self.direction

            if self.jump_chance > 0 and random.random() < self.jump_chance * dt:
                self.velocity.y = -self.jump_power
                self.on_ground = False

        self.velocity.x = self.speed * self.direction

        prev_x = self.rect.x
        self.pos.x += self.velocity.x * dt
        self.sync_rect()
        self._resolve_collisions(solids, axis="x")
        self.pos.x = self.rect.x
        if self.on_ground:
            self._traveled += abs(self.rect.x - prev_x)

        self._prev_vy = self.velocity.y
        self.pos.y += self.velocity.y * dt
        self.sync_rect()
        self.on_ground = False
        self._resolve_collisions(solids, axis="y")
        self.pos.y = self.rect.y

        if self.on_ground and self._prev_vy > self.damage_on_fall_speed and self.damage_on_fall_amount > 0:
            self.take_damage(self.damage_on_fall_amount)

        self._update_anim_state()
        self.update_animation(dt)

    def _update_anim_state(self):
        if not self.anims:
            return
        if not self.on_ground:
            self.play_anim("jump" if self.velocity.y < 0 else "fall")
        elif abs(self.velocity.x) > 1:
            self.play_anim("walk")
        else:
            self.play_anim("idle")

    def _resolve_collisions(self, solids, axis):
        for p in solids:
            if not self.rect.colliderect(p):
                continue
            if axis == "x":
                if self.velocity.x > 0:
                    self.rect.right = p.left
                    self.direction = -1
                    self.facing = -1
                elif self.velocity.x < 0:
                    self.rect.left = p.right
                    self.direction = 1
                    self.facing = 1
                self.velocity.x = 0
                self._traveled = 0.0
            else:
                if self.velocity.y > 0:
                    self.rect.bottom = p.top
                    self.on_ground = True
                elif self.velocity.y < 0:
                    self.rect.top = p.bottom
                self.velocity.y = 0

    def draw(self, surface, camera, debug=False):
        super().draw(surface, camera, debug=debug)

        if self.hit_flash > 0:
            screen_rect = self.rect.copy()
            screen_rect.x -= round(camera.offset.x)
            screen_rect.y -= round(camera.offset.y)
            overlay = pygame.Surface(screen_rect.size, pygame.SRCALPHA)
            overlay.fill((255, 80, 80, int(120 * (self.hit_flash / 0.15))))
            surface.blit(overlay, screen_rect.topleft)

        self._draw_hp_bar(surface, camera)

    def _draw_hp_bar(self, surface, camera):
        if self.max_hp <= 0:
            return
        w = self.rect.width
        h = 5
        x = self.rect.x - round(camera.offset.x)
        y = self.rect.y - round(camera.offset.y) - h - 4
        if y + h < 0 or y > surface.get_height():
            return

        pygame.draw.rect(surface, (40, 0, 0), (x, y, w, h), border_radius=2)
        ratio = max(0.0, self.hp / self.max_hp)
        fill_w = int(w * ratio)
        if fill_w > 0:
            color = (220, 40, 40) if ratio > 0.3 else (255, 160, 40)
            pygame.draw.rect(surface, color, (x, y, fill_w, h), border_radius=2)
        pygame.draw.rect(surface, (0, 0, 0), (x, y, w, h), 1, border_radius=2)