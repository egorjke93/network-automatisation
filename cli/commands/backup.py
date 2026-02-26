"""
Команды backup и run.

Команды: backup, run
"""

import logging

from ..utils import prepare_collection, get_exporter

logger = logging.getLogger(__name__)


def cmd_run(args, ctx=None) -> None:
    """Обработчик команды run (произвольная команда)."""
    from ...core.connection import ConnectionManager, get_ntc_platform
    from ...parsers.textfsm_parser import NTCParser, NTC_AVAILABLE
    from ...config import config

    devices, credentials = prepare_collection(args)

    fields = args.fields.split(",") if args.fields else None

    # config.connection возвращает ConfigSection с методом .get()
    conn_config = config.connection
    conn_manager = ConnectionManager(
        transport=args.transport,
        max_retries=conn_config.get("max_retries", 2) if conn_config else 2,
        retry_delay=conn_config.get("retry_delay", 5) if conn_config else 5,
    )
    all_data = []

    for device in devices:
        try:
            with conn_manager.connect(device, credentials) as conn:
                hostname = conn_manager.get_hostname(conn)
                response = conn.send_command(args.cmd)
                output = response.result

                if args.format == "raw":
                    print(f"\n=== {hostname} ({device.host}) ===")
                    print(output)
                    continue

                if NTC_AVAILABLE:
                    parser = NTCParser()
                    platform = args.platform or get_ntc_platform(device.platform)
                    try:
                        parsed = parser.parse(
                            output=output,
                            platform=platform,
                            command=args.cmd,
                            fields=fields,
                        )
                        for row in parsed:
                            row["hostname"] = hostname
                            row["device_ip"] = device.host
                        all_data.extend(parsed)
                    except Exception as e:
                        logger.warning(
                            f"NTC парсинг не удался для {platform}/{args.cmd}: {e}"
                        )
                        all_data.append(
                            {
                                "hostname": hostname,
                                "device_ip": device.host,
                                "raw_output": output,
                            }
                        )
                else:
                    all_data.append(
                        {
                            "hostname": hostname,
                            "device_ip": device.host,
                            "raw_output": output,
                        }
                    )

        except Exception as e:
            logger.error(f"Ошибка на {device.host}: {e}")

    if args.format == "raw":
        return

    if not all_data:
        logger.warning("Нет данных для экспорта")
        return

    # --format parsed: NTC-парсированные данные в stdout (run не имеет нормализации)
    if args.format == "parsed":
        from ...exporters import RawExporter
        RawExporter().export(all_data, "custom_command_parsed")
        return

    exporter = get_exporter(args.format, args.output)
    file_path = exporter.export(all_data, "custom_command")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")


def _build_site_map(backup_results, devices, default_site=None):
    """
    Строит маппинг hostname → site из результатов бэкапа и списка устройств.

    Связка: BackupResult.device_ip → Device.host → Device.site

    Приоритет site:
    1. device.site (из devices_ips.py, per-device)
    2. default_site (из config.yaml)
    3. None (без группировки по сайтам)

    Args:
        backup_results: Результаты бэкапа (BackupResult с hostname и device_ip)
        devices: Список Device объектов
        default_site: Дефолтный сайт

    Returns:
        dict или None: {hostname: site_slug} или None
    """
    # Маппинг IP → site из devices_ips.py
    ip_to_site = {}
    for device in devices:
        site = getattr(device, "site", None) or default_site
        if site:
            ip_to_site[device.host] = site

    if not ip_to_site:
        return None

    # Маппинг hostname → site через BackupResult.device_ip
    site_map = {}
    for result in backup_results:
        if result.success and result.hostname:
            site = ip_to_site.get(result.device_ip)
            if site:
                site_map[result.hostname] = site

    return site_map if site_map else None



def _get_git_pusher():
    """Создаёт GitBackupPusher из config.yaml."""
    from ...config import config
    from ...core.git_pusher import GitBackupPusher

    git_cfg = config.git
    if not git_cfg or not getattr(git_cfg, "url", ""):
        logger.error("Git не настроен. Добавьте секцию 'git' в config.yaml")
        return None
    if not getattr(git_cfg, "token", ""):
        logger.error("Git token не указан в config.yaml")
        return None
    if not getattr(git_cfg, "repo", ""):
        logger.error("Git repo не указан в config.yaml")
        return None

    return GitBackupPusher(
        url=git_cfg.url,
        token=git_cfg.token,
        repo=git_cfg.repo,
        branch=getattr(git_cfg, "branch", "main"),
        verify_ssl=getattr(git_cfg, "verify_ssl", True),
        timeout=getattr(git_cfg, "timeout", 30),
    )


def cmd_backup(args, ctx=None) -> None:
    """Обработчик команды backup (резервное копирование конфигураций)."""
    output_folder = getattr(args, "output", "backups")

    # --git-test: только проверка подключения к Git
    if getattr(args, "git_test", False):
        pusher = _get_git_pusher()
        if pusher and pusher.test_connection():
            logger.info("Git подключение: OK")
        else:
            logger.error("Git подключение: ОШИБКА")
        return

    # --git-only: только пуш существующих бэкапов (без сбора)
    if getattr(args, "git_only", False):
        pusher = _get_git_pusher()
        if not pusher:
            return
        default_site = getattr(args, "site", None)
        git_results = pusher.push_backups(
            backup_folder=output_folder,
            default_site=default_site,
        )
        _print_git_results(git_results)
        return

    # Обычный бэкап: сбор с устройств
    from ...collectors import ConfigBackupCollector

    devices, credentials = prepare_collection(args)

    collector = ConfigBackupCollector(
        credentials=credentials,
        transport=args.transport,
    )

    results = collector.backup(devices, output_folder=output_folder)

    success = sum(1 for r in results if r.success)
    failed = len(results) - success

    logger.info("=== РЕЗУЛЬТАТЫ БЭКАПА ===")
    logger.info(f"Успешно: {success}")
    logger.info(f"Ошибки: {failed}")

    for r in results:
        if not r.success:
            logger.error(f"  {r.hostname}: {r.error}")

    # --push-git: после сбора отправить в Git
    if getattr(args, "push_git", False):
        pusher = _get_git_pusher()
        if pusher:
            logger.info("=== GIT PUSH ===")
            # site_map: hostname → site из devices_ips.py (per-device site)
            default_site = getattr(args, "site", None)
            site_map = _build_site_map(results, devices, default_site)
            git_results = pusher.push_backups(
                backup_folder=output_folder,
                site_map=site_map,
            )
            _print_git_results(git_results)


def _print_git_results(results) -> None:
    """Выводит результаты Git push."""
    created = sum(1 for r in results if r.action == "created")
    updated = sum(1 for r in results if r.action == "updated")
    unchanged = sum(1 for r in results if r.action == "unchanged")
    failed = sum(1 for r in results if not r.success)

    logger.info("=== РЕЗУЛЬТАТЫ GIT PUSH ===")
    logger.info(f"Создано: {created}")
    logger.info(f"Обновлено: {updated}")
    logger.info(f"Без изменений: {unchanged}")
    if failed:
        logger.error(f"Ошибки: {failed}")
        for r in results:
            if not r.success:
                logger.error(f"  {r.hostname}: {r.error}")
