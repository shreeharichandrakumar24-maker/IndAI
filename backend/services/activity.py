"""Best-effort activity log for task changes (Part 1: plan tracking).

log_task_activity() writes a factory_memory WORKER_UPDATE entry. It NEVER
raises: any failure is swallowed (and printed without secrets) so a logging
problem can never fail the worker request it annotates.
"""
from datetime import datetime, timezone


def log_task_activity(db, *, task, employee, action,
                      from_status=None, to_status=None,
                      progress=None, quantity_completed=None,
                      quantity_target=None):
    """action: started | progress | output | completed | updated."""
    try:
        from backend.models.models import FactoryMemory

        verbs = {
            "started": "started",
            "progress": "updated progress on",
            "output": "logged output for",
            "completed": "finished",
            "updated": "updated",
        }
        verb = verbs.get(action, "updated")
        title = f"{(employee.name if employee else 'Someone')} {verb} '{(task.name or 'task')[:80]}'"
        bits = []
        if from_status and to_status and from_status != to_status:
            bits.append(f"{from_status} -> {to_status}")
        if progress is not None:
            try:
                bits.append(f"progress {float(progress):.0%}")
            except (TypeError, ValueError):
                pass
        if quantity_completed is not None:
            bits.append(f"qty {quantity_completed}"
                        + (f"/{quantity_target}" if quantity_target else ""))
        description = ("; ".join(bits) or verb) + "."
        db.add(FactoryMemory(
            title=title[:255],
            event_type="WORKER_UPDATE",
            description=description[:2000],
            machine_id=task.machine_id,
            order_id=task.order_id,
            task_id=task.id,
            metadata_={
                "task_id": str(task.id),
                "action": action,
                "from_status": from_status,
                "to_status": to_status,
                "progress": progress,
                "quantity_completed": quantity_completed,
                "quantity_target": quantity_target,
                "employee_id": str(employee.id) if employee is not None else None,
                "employee_name": employee.name if employee is not None else None,
                "logged_at": datetime.now(timezone.utc).isoformat(),
            },
        ))
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"WARNING: log_task_activity failed ({type(e).__name__}); request unaffected.")
