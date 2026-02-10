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


def cmd_backup(args, ctx=None) -> None:
    """Обработчик команды backup (резервное копирование конфигураций)."""
    from ...collectors import ConfigBackupCollector

    devices, credentials = prepare_collection(args)

    collector = ConfigBackupCollector(
        credentials=credentials,
        transport=args.transport,
    )

    output_folder = getattr(args, "output", "backups")
    results = collector.backup(devices, output_folder=output_folder)

    success = sum(1 for r in results if r.success)
    failed = len(results) - success

    logger.info("=== РЕЗУЛЬТАТЫ ===")
    logger.info(f"Успешно: {success}")
    logger.info(f"Ошибки: {failed}")

    for r in results:
        if not r.success:
            logger.error(f"  {r.hostname}: {r.error}")
