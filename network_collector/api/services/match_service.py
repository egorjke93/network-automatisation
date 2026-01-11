"""
Match Service - сопоставление MAC с хостами.

TODO: Реализовать интеграцию с существующим кодом match.
"""

from ..schemas import Credentials, MatchRequest, MatchResponse


class MatchService:
    """Сервис сопоставления MAC с хостами."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials

    async def match(self, request: MatchRequest) -> MatchResponse:
        """Сопоставляет MAC-адреса с хостами."""
        # TODO: Реализовать
        return MatchResponse(
            success=False,
            entries=[],
            matched=0,
            unmatched=0,
        )
