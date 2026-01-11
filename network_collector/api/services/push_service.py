"""
Push Service - push описаний интерфейсов.

TODO: Реализовать интеграцию с существующим кодом push-descriptions.
"""

from ..schemas import Credentials, PushDescriptionsRequest, PushDescriptionsResponse


class PushService:
    """Сервис push описаний."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials

    async def push(self, request: PushDescriptionsRequest) -> PushDescriptionsResponse:
        """Отправляет описания на устройства."""
        # TODO: Реализовать
        return PushDescriptionsResponse(
            success=False,
            dry_run=request.dry_run,
            results=[],
            total_success=0,
            total_failed=0,
            total_skipped=0,
        )
