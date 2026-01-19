"""
Команда validate-fields.

Валидация fields.yaml против моделей.
"""

import sys
import logging

logger = logging.getLogger(__name__)


def cmd_validate_fields(args, ctx=None) -> None:
    """
    Валидация fields.yaml против моделей.

    Проверяет что все поля в конфигурации существуют в моделях.
    """
    from ...core.field_registry import (
        validate_fields_config,
        print_field_registry,
        FIELD_REGISTRY,
    )

    # Показать реестр полей
    if args.show_registry:
        print_field_registry(args.type)
        return

    print("Validating fields.yaml against models...\n")

    # Валидация
    errors = validate_fields_config()

    if errors:
        print(f"Found {len(errors)} issue(s):\n")
        for err in errors:
            print(f"  ✗ {err}")
        print()
        sys.exit(1)
    else:
        print("✓ All fields are valid!\n")

    # Статистика
    if args.verbose:
        print("Field Registry Statistics:")
        for data_type, fields in FIELD_REGISTRY.items():
            enabled_count = len([f for f in fields.values() if f.aliases])
            print(f"  {data_type}: {len(fields)} fields ({enabled_count} with aliases)")

        print("\n  Use --show-registry to see all fields")
        print("  Use --type <type> to filter by data type")
