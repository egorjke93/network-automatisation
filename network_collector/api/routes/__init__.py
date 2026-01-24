"""API Routes."""

from .auth import router as auth_router
from .devices import router as devices_router
from .mac import router as mac_router
from .lldp import router as lldp_router
from .interfaces import router as interfaces_router
from .inventory import router as inventory_router
from .backup import router as backup_router
from .sync import router as sync_router
from .match import router as match_router
from .push import router as push_router
from .pipelines import router as pipelines_router
from .history import router as history_router
from .device_management import router as device_management_router
from .tasks import router as tasks_router
from .fields import router as fields_router

__all__ = [
    "auth_router",
    "devices_router",
    "mac_router",
    "lldp_router",
    "interfaces_router",
    "inventory_router",
    "backup_router",
    "sync_router",
    "match_router",
    "push_router",
    "pipelines_router",
    "history_router",
    "device_management_router",
    "tasks_router",
    "fields_router",
]
