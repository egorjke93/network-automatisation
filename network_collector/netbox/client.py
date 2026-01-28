"""
Backward compatibility wrapper.

NetBox Client теперь разбит на модули в netbox/client/.
Этот файл обеспечивает обратную совместимость импортов.

Новый импорт:
    from network_collector.netbox.client import NetBoxClient

Или напрямую из модуля:
    from network_collector.netbox.client.devices import DevicesMixin
"""

# Re-export для обратной совместимости
from .client import NetBoxClient, PYNETBOX_AVAILABLE

__all__ = ["NetBoxClient", "PYNETBOX_AVAILABLE"]
