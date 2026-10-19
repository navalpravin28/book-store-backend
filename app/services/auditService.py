import logging

from app.core.utils import utcnow

logger = logging.getLogger("bookstore.audit")


class AuditService:
    """Append-only trail of admin / sensitive actions. Never breaks the main request."""

    def __init__(self, db):
        self.col = db.auditLogs

    async def log(self, actor_id: str | None, action: str, resource: str,
                  resource_id: str | None = None, meta: dict | None = None) -> None:
        try:
            await self.col.insert_one({
                "actorId": actor_id,
                "action": action,
                "resource": resource,
                "resourceId": resource_id,
                "meta": meta or {},
                "createdAt": utcnow(),
            })
        except Exception:  # pragma: no cover
            logger.exception("Failed to write audit log")
