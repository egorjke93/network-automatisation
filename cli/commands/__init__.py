"""
CLI команды.

Каждый модуль содержит обработчики команд:
- collect.py: devices, mac, lldp, interfaces, inventory
- sync.py: sync-netbox
- backup.py: backup, run
- match.py: match-mac
- push.py: push-descriptions
- validate.py: validate-fields
- pipeline.py: pipeline (list, show, run, validate, create, delete)
"""

from .collect import (
    cmd_devices,
    cmd_mac,
    cmd_lldp,
    cmd_interfaces,
    cmd_inventory,
)
from .sync import cmd_sync_netbox, _print_sync_summary
from .backup import cmd_backup, cmd_run
from .match import cmd_match_mac
from .push import cmd_push_descriptions
from .validate import cmd_validate_fields
from .pipeline import cmd_pipeline

__all__ = [
    "cmd_devices",
    "cmd_mac",
    "cmd_lldp",
    "cmd_interfaces",
    "cmd_inventory",
    "cmd_sync_netbox",
    "cmd_backup",
    "cmd_run",
    "cmd_match_mac",
    "cmd_push_descriptions",
    "cmd_validate_fields",
    "cmd_pipeline",
    "_print_sync_summary",
]
