from datetime import datetime
from typing import Optional

from backend_fastapi.database.database import SessionLocal
from backend_fastapi.database.models import MaintenanceLog


def record_maintenance(
    machine_id: str,
    action: str,
    status: str,
    source: str,
    reason: Optional[str] = None,
    health_status: Optional[str] = None,
    risk: Optional[float] = None,
    is_whatif: bool = False,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            MaintenanceLog(
                timestamp=datetime.utcnow(),
                machine_id=machine_id,
                action=action,
                status=status,
                source=source,
                reason=reason,
                health_status=health_status,
                risk=risk,
                is_whatif=is_whatif,
            )
        )
        db.commit()
    except Exception as e:
        print("MAINTENANCE LOG WRITE ERROR:", e)
    finally:
        db.close()
