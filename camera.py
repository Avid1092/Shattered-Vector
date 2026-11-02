"""Камера: плавное следование за целью без ограничения границами мира."""
import pygame


class Camera:
    """
    Камера с центрированием на цели и lerp-сглаживанием.
    offset — точка мира (левый верхний угол), которую видит камера.

    Ограничения по границам мира сняты: игрок может выходить за край карты,
    камера продолжает за ним следовать.
    """

    def __init__(self, view_width, view_height, world_width, world_height, lerp_speed=10.0):
        self.view_width = view_width
        self.view_height = view_height
        self.world_width = world_width    # оставлено для совместимости / будущих флагов
        self.world_height = world_height
        self.lerp_speed = lerp_speed
        self.offset = pygame.Vector2(0, 0)

    def snap_to(self, target_rect):
        """Мгновенно переместить камеру к цели."""
        self.offset = self._target_offset(target_rect)

    def update(self, target_rect, dt):
        """Плавно подтянуть камеру к цели."""
        target = self._target_offset(target_rect)
        factor = min(1.0, self.lerp_speed * dt)
        self.offset.x += (target.x - self.offset.x) * factor
        self.offset.y += (target.y - self.offset.y) * factor

    def _target_offset(self, target_rect):
        x = target_rect.centerx - self.view_width // 2
        y = target_rect.centery - self.view_height // 2
        return pygame.Vector2(x, y)