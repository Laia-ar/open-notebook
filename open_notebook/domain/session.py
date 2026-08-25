import hashlib
import secrets
from datetime import datetime, timezone
from typing import ClassVar, Optional

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.base import ObjectModel


class UserSession(ObjectModel):
    table_name: ClassVar[str] = "user_session"

    user_id: str
    token_hash: str
    expires_at: datetime
    revoked_at: Optional[datetime] = None

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    async def create_for_user(
        cls,
        user_id: str,
        expires_at: datetime,
    ) -> tuple["UserSession", str]:
        raw_token = cls.generate_token()

        session = cls(
            user_id=user_id,
            token_hash=cls.hash_token(raw_token),
            expires_at=expires_at,
        )

        await session.save()

        return session, raw_token

    @classmethod
    async def get_by_token(cls, token: str) -> Optional["UserSession"]:
        token_hash = cls.hash_token(token)

        result = await repo_query(
            """
            SELECT * FROM user_session
            WHERE token_hash = $token_hash
            LIMIT 1
            """,
            {"token_hash": token_hash},
        )

        if not result:
            return None

        return cls(**result[0])

    @property
    def is_valid(self) -> bool:
        now = datetime.now(timezone.utc)

        if self.revoked_at is not None:
            return False

        return self.expires_at > now

    async def revoke(self) -> None:
        self.revoked_at = datetime.now(timezone.utc)
        await self.save()

    def _prepare_save_data(self) -> dict:
        data = super()._prepare_save_data()
        data["user_id"] = ensure_record_id(self.user_id)
        return data