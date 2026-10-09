"""
Entity package for reiseverlauftracker.

All platform entities inherit from (PlatformEntity, ReiseverlaufEntity).
Entities read coordinator.data only. Unique IDs follow the pattern {entry_id}_{description.key}.
"""

from .base import ReiseverlaufEntity

__all__ = ["ReiseverlaufEntity"]
