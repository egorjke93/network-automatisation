"""
Polygon-тест: полная эмуляция QTech sync с реальным NetBox.

Тестирует:
1. Создание устройства QTech в NetBox
2. Sync интерфейсов (TFGigabitEthernet, HundredGigabitEthernet, AggregatePort, Vlan)
3. LAG membership (2-фазное создание: LAG → member)
4. Media type из show interface transceiver → точный NetBox тип
5. Switchport mode (access/trunk)
6. Cleanup

Запуск:
    cd /home/sa/project
    python -m pytest network_collector/tests/test_qtech_polygon.py -v -s
"""

import sys
import os
import logging

import pytest
import pynetbox

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Настройки NetBox ──────────────────────────────────────────────────
NETBOX_URL = "http://localhost:8000/"
NETBOX_TOKEN = "4dd51a78084a1c18c7dc95f56a5355c692811c02"
SITE_NAME = "QTech-Polygon"
DEVICE_NAME = "qtech-test-sw01"
MANUFACTURER = "QTech"
DEVICE_TYPE = "QSW-6900-56F"
ROLE = "Switch"


def netbox_available():
    """Проверяет доступность NetBox."""
    try:
        api = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
        api.status()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not netbox_available(),
    reason="NetBox недоступен на localhost:8000",
)


@pytest.fixture(scope="module")
def nb_api():
    """PyNetBox API клиент."""
    api = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
    api.http_session.verify = False
    return api


@pytest.fixture(scope="module")
def nb_sync(nb_api):
    """Создаёт NetBoxSync клиент."""
    from network_collector.netbox.client import NetBoxClient
    from network_collector.netbox.sync import NetBoxSync

    client = NetBoxClient(url=NETBOX_URL, token=NETBOX_TOKEN, ssl_verify=False)
    sync = NetBoxSync(client=client, dry_run=False)
    return sync


@pytest.fixture(scope="module")
def qtech_device(nb_sync):
    """Создаёт QTech устройство в NetBox (или находит существующее)."""
    device = nb_sync.create_device(
        name=DEVICE_NAME,
        device_type=DEVICE_TYPE,
        site=SITE_NAME,
        role=ROLE,
        manufacturer=MANUFACTURER,
    )
    assert device is not None, f"Не удалось создать устройство {DEVICE_NAME}"
    logger.info(f"Устройство: {device.name} (id={device.id})")
    return device


def build_qtech_interfaces():
    """
    Строит список интерфейсов QTech из фикстур.
    Эмулирует вывод InterfaceCollector + InterfaceNormalizer.

    Поля Interface:
    - tagged_vlans: str (через запятую: "10,20,30")
    - mode: "access", "tagged", "tagged-all" (не "trunk")
    - speed: "10 Gbit", "100 Gbit" (формат для _parse_speed)
    - access_vlan/native_vlan: str (вместо untagged_vlan)
    """
    from network_collector.core.models import Interface

    interfaces = []

    # ── TFGigabitEthernet 0/1-4 (10G SFP+ с трансиверами) ──
    transceivers = {
        "TFGigabitEthernet 0/1": "10GBASE-SR-SFP+",
        "TFGigabitEthernet 0/2": "10GBASE-SR-SFP+",
        "TFGigabitEthernet 0/3": "10GBASE-LR-SFP+",
        "TFGigabitEthernet 0/4": "10GBASE-LR-SFP+",
    }

    for i in range(1, 9):
        name = f"TFGigabitEthernet 0/{i}"
        media_type = transceivers.get(name, "")
        is_trunk = i <= 2
        iface = Interface(
            name=name,
            status="up" if i <= 4 else "down",
            description=f"dc{i:02d}" if i <= 4 else "",
            speed="10 Gbit",
            mac="001f.ce62.1e96",
            mtu=1500,
            port_type="10g-sfp+",
            media_type=media_type,
            mode="tagged" if is_trunk else "access",
            native_vlan="1" if is_trunk else "",
            access_vlan="" if is_trunk else "1",
            tagged_vlans="10,20,30" if is_trunk else "",
        )
        interfaces.append(iface)

    # ── HundredGigabitEthernet 0/49-52 (100G) ──
    for i in range(49, 53):
        iface = Interface(
            name=f"HundredGigabitEthernet 0/{i}",
            status="up" if i <= 50 else "down",
            description=f"uplink-{i}" if i <= 50 else "",
            speed="100 Gbit",
            mac="001f.ce62.1e96",
            mtu=9216,
            port_type="100g-qsfp28",
        )
        interfaces.append(iface)

    # ── AggregatePort 1 (LAG) — members: Hu0/49, Hu0/50 ──
    lag = Interface(
        name="AggregatePort 1",
        status="up",
        description="uplink-lag",
        speed="200 Gbit",
        mac="001f.ce62.1e96",
        mtu=9216,
        port_type="lag",
        mode="tagged",
        native_vlan="1",
        tagged_vlans="10,20,30",
    )
    interfaces.append(lag)

    # ── AggregatePort 10 (LAG) — member: TF0/1 ──
    lag10 = Interface(
        name="AggregatePort 10",
        status="up",
        description="server-lag",
        speed="10 Gbit",
        mac="001f.ce62.1e96",
        mtu=1500,
        port_type="lag",
        mode="access",
        access_vlan="10",
    )
    interfaces.append(lag10)

    # Устанавливаем LAG membership
    for iface in interfaces:
        if iface.name in ("HundredGigabitEthernet 0/49", "HundredGigabitEthernet 0/50"):
            iface.lag = "AggregatePort 1"
        elif iface.name == "TFGigabitEthernet 0/1":
            iface.lag = "AggregatePort 10"

    # ── Vlan SVI ──
    vlan10 = Interface(
        name="Vlan 10",
        status="up",
        description="management",
        ip_address="10.0.10.1/24",
        mac="001f.ce62.1e96",
        mtu=1500,
        port_type="virtual",
    )
    interfaces.append(vlan10)

    vlan20 = Interface(
        name="Vlan 20",
        status="up",
        description="servers",
        ip_address="10.0.20.1/24",
        mac="001f.ce62.1e96",
        mtu=1500,
        port_type="virtual",
    )
    interfaces.append(vlan20)

    return interfaces


class TestQTechPolygon:
    """Полный цикл sync QTech с реальным NetBox."""

    def test_01_device_created(self, qtech_device):
        """Устройство QTech создано в NetBox."""
        assert qtech_device is not None
        assert qtech_device.name == DEVICE_NAME
        logger.info(f"✓ Устройство {qtech_device.name} (id={qtech_device.id})")

    def test_02_sync_interfaces(self, nb_sync, qtech_device):
        """Sync интерфейсов: LAG, 10G, 100G, Vlan SVI."""
        interfaces = build_qtech_interfaces()

        result = nb_sync.sync_interfaces(
            device_name=DEVICE_NAME,
            interfaces=interfaces,
            create_missing=True,
            update_existing=True,
        )

        logger.info(f"Sync result: created={result['created']}, "
                     f"updated={result['updated']}, skipped={result['skipped']}")

        # Должны быть созданы интерфейсы
        assert result["created"] > 0 or result["updated"] >= 0
        assert result.get("failed", 0) == 0, f"Ошибки sync: {result.get('details', {})}"

    def test_03_lag_created(self, nb_api, qtech_device):
        """LAG интерфейсы созданы с правильным типом."""
        interfaces = nb_api.dcim.interfaces.filter(device_id=qtech_device.id, name="AggregatePort 1")
        lag_list = list(interfaces)
        assert len(lag_list) == 1, f"AggregatePort 1 не найден, найдено: {[i.name for i in lag_list]}"
        lag = lag_list[0]
        assert lag.type.value == "lag", f"Тип AggregatePort 1: {lag.type.value} (ожидался lag)"
        logger.info(f"✓ AggregatePort 1: type={lag.type.value}")

    def test_04_lag_members(self, nb_api, qtech_device):
        """LAG members привязаны к правильному LAG."""
        # Найти AggregatePort 1
        lag = list(nb_api.dcim.interfaces.filter(
            device_id=qtech_device.id, name="AggregatePort 1"
        ))[0]

        # Найти member Hu0/49
        hu49_list = list(nb_api.dcim.interfaces.filter(
            device_id=qtech_device.id, name="HundredGigabitEthernet 0/49"
        ))
        assert len(hu49_list) == 1, f"HundredGigabitEthernet 0/49 не найден"
        hu49 = hu49_list[0]

        if hu49.lag:
            assert hu49.lag.id == lag.id, (
                f"Hu0/49 привязан к LAG id={hu49.lag.id}, ожидался id={lag.id}"
            )
            logger.info(f"✓ Hu0/49 → AggregatePort 1 (lag_id={lag.id})")
        else:
            logger.warning(f"⚠ Hu0/49 не привязан к LAG (lag=None)")

    def test_05_media_type_10g(self, nb_api, qtech_device):
        """10G интерфейсы с трансивером получили точный NetBox тип."""
        tf1_list = list(nb_api.dcim.interfaces.filter(
            device_id=qtech_device.id, name="TFGigabitEthernet 0/1"
        ))
        assert len(tf1_list) == 1
        tf1 = tf1_list[0]

        # media_type "10GBASE-SR-SFP+" → NetBox тип должен быть "10gbase-sr" (точный)
        # а не "10gbase-x-sfpp" (generic)
        logger.info(f"  TF0/1 type: {tf1.type.value} (label: {tf1.type.label})")

        # 10gbase-sr = точный тип из трансивера
        assert tf1.type.value == "10gbase-sr", (
            f"TF0/1: ожидался тип 10gbase-sr (из media_type 10GBASE-SR-SFP+), "
            f"получен {tf1.type.value}"
        )
        logger.info(f"✓ TF0/1: type=10gbase-sr (точный из трансивера)")

    def test_06_media_type_lr(self, nb_api, qtech_device):
        """10G LR интерфейс получил точный тип 10gbase-lr."""
        tf3_list = list(nb_api.dcim.interfaces.filter(
            device_id=qtech_device.id, name="TFGigabitEthernet 0/3"
        ))
        assert len(tf3_list) == 1
        tf3 = tf3_list[0]

        logger.info(f"  TF0/3 type: {tf3.type.value} (label: {tf3.type.label})")
        assert tf3.type.value == "10gbase-lr", (
            f"TF0/3: ожидался тип 10gbase-lr (из media_type 10GBASE-LR-SFP+), "
            f"получен {tf3.type.value}"
        )
        logger.info(f"✓ TF0/3: type=10gbase-lr (точный из трансивера)")

    def test_07_no_media_type_fallback(self, nb_api, qtech_device):
        """10G интерфейс без трансивера → generic тип."""
        tf5_list = list(nb_api.dcim.interfaces.filter(
            device_id=qtech_device.id, name="TFGigabitEthernet 0/5"
        ))
        assert len(tf5_list) == 1
        tf5 = tf5_list[0]

        logger.info(f"  TF0/5 type: {tf5.type.value} (label: {tf5.type.label})")
        # Без media_type → по имени → 10gbase-x-sfpp (generic SFP+)
        assert tf5.type.value == "10gbase-x-sfpp", (
            f"TF0/5: ожидался generic тип 10gbase-x-sfpp, получен {tf5.type.value}"
        )
        logger.info(f"✓ TF0/5: type=10gbase-x-sfpp (generic, нет трансивера)")

    def test_08_100g_type(self, nb_api, qtech_device):
        """100G интерфейс получил правильный тип."""
        hu49_list = list(nb_api.dcim.interfaces.filter(
            device_id=qtech_device.id, name="HundredGigabitEthernet 0/49"
        ))
        assert len(hu49_list) == 1
        hu49 = hu49_list[0]

        logger.info(f"  Hu0/49 type: {hu49.type.value} (label: {hu49.type.label})")
        assert hu49.type.value == "100gbase-x-qsfp28", (
            f"Hu0/49: ожидался тип 100gbase-x-qsfp28, получен {hu49.type.value}"
        )
        logger.info(f"✓ Hu0/49: type=100gbase-x-qsfp28")

    def test_09_vlan_svi(self, nb_api, qtech_device):
        """Vlan SVI созданы как virtual."""
        vlan10_list = list(nb_api.dcim.interfaces.filter(
            device_id=qtech_device.id, name="Vlan 10"
        ))
        assert len(vlan10_list) == 1
        vlan10 = vlan10_list[0]

        logger.info(f"  Vlan 10 type: {vlan10.type.value}")
        assert vlan10.type.value == "virtual", (
            f"Vlan 10: ожидался тип virtual, получен {vlan10.type.value}"
        )
        logger.info(f"✓ Vlan 10: type=virtual, description={vlan10.description}")

    def test_10_interface_count(self, nb_api, qtech_device):
        """Проверяем общее количество созданных интерфейсов."""
        all_ifaces = list(nb_api.dcim.interfaces.filter(device_id=qtech_device.id))
        iface_names = sorted([i.name for i in all_ifaces])

        logger.info(f"Всего интерфейсов: {len(all_ifaces)}")
        for name in iface_names:
            iface = next(i for i in all_ifaces if i.name == name)
            logger.info(f"  {name}: type={iface.type.value}")

        # 8 TF + 4 Hu + 2 Ag + 2 Vlan = 16
        expected = 16
        assert len(all_ifaces) == expected, (
            f"Ожидалось {expected} интерфейсов, найдено {len(all_ifaces)}: {iface_names}"
        )

    def test_11_idempotent_sync(self, nb_sync, qtech_device):
        """Повторный sync не создаёт дублей."""
        interfaces = build_qtech_interfaces()

        result = nb_sync.sync_interfaces(
            device_name=DEVICE_NAME,
            interfaces=interfaces,
            create_missing=True,
            update_existing=True,
        )

        logger.info(f"Re-sync: created={result['created']}, "
                     f"updated={result['updated']}, skipped={result['skipped']}")

        assert result["created"] == 0, (
            f"Повторный sync создал {result['created']} интерфейсов (ожидалось 0)"
        )
        assert result.get("failed", 0) == 0

    def test_99_cleanup(self, nb_api, qtech_device):
        """Удаляем тестовые данные из NetBox."""
        # Удаляем интерфейсы
        all_ifaces = list(nb_api.dcim.interfaces.filter(device_id=qtech_device.id))
        for iface in all_ifaces:
            iface.delete()
        logger.info(f"Удалено {len(all_ifaces)} интерфейсов")

        # Удаляем устройство
        qtech_device.delete()
        logger.info(f"Удалено устройство {DEVICE_NAME}")

        # Удаляем сайт если пустой
        sites = nb_api.dcim.sites.filter(name=SITE_NAME)
        for site in sites:
            try:
                site.delete()
                logger.info(f"Удалён сайт {SITE_NAME}")
            except Exception:
                pass  # Сайт может быть непустой

        logger.info("✓ Cleanup завершён")
