"""Automatic Production -> Task -> Order lifecycle sync.

Task-centric hierarchy (no new tables, no HTTP calls):

    Order -> Task -> ProductionRun

    production create/update
        |
        v
    sync_task_completion(task_id)  -> task DONE + progress 1.0 when every
                                      linked run is COMPLETED/DONE;
                                      otherwise quantity-based progress
                                      (completed / target over
                                      non-cancelled runs, capped at 1.0)
        |
        v (only when the task reads DONE/COMPLETED afterwards)
    sync_order_completion(order_id) -> order COMPLETED when every linked
                                       task is DONE/COMPLETED

    task create/update
        |
        v
    reopen_order_if_needed(order_id) -> a COMPLETED/DONE order with any
                                        open task returns to IN_PROGRESS
        +
    sync_order_completion(order_id)  -> re-completes when all tasks closed

Rules (hackathon-safe, minimal):
- A run counts as finished only when its status normalizes to COMPLETED
  or DONE. CANCELLED, quantities, or anything else never counts toward
  completion (quantities only drive the progress fraction).
- Completion stays status-based: quantity progress never marks DONE.
- A task with zero runs never auto-completes; an order with zero tasks
  never auto-completes and is never reopened.
- Runs/tasks without a link (task_id/order_id None) affect nothing.
- Only a COMPLETED/DONE order is ever reopened (to IN_PROGRESS, the
  existing active status); CANCELLED and other statuses are untouched.
- All reads go through the caller's scoped session, so rows from another
  factory read as not-found and never participate.
- Helpers only flush + set attributes; they never commit. The owning
  endpoint commits once, so a failure rolls everything back.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import Order, ProductionRun, Task

# A production run counts as finished only in these statuses.
FINISHED_RUN_STATUSES = frozenset({"COMPLETED", "DONE"})

# A task counts as closed in these statuses (existing task conventions:
# DONE/COMPLETED closed, CANCELLED is closed-but-not-successful so it
# never completes an order).
CLOSED_TASK_STATUSES = frozenset({"DONE", "COMPLETED"})


def _norm(status) -> str:
    """Status normalization matching the endpoint convention (strip + upper)."""
    return (status or "").strip().upper()


def sync_task_completion(db: Session, task_id: Optional[UUID]) -> Optional[Task]:
    """Sync a task from its production runs (status + quantity progress).

    - Every linked run finished (COMPLETED/DONE) -> task DONE + progress 1.0.
    - Otherwise, when the open (non-CANCELLED) runs carry quantity targets,
      task.progress tracks sum(completed) / sum(target), capped at 1.0.
      Quantity progress never marks DONE and never touches an already
      closed task.
    Returns the task when it reads DONE/COMPLETED afterwards (caller chains
    into sync_order_completion); None when there is nothing to do (no link,
    unknown/other-factory task, or zero runs).
    Never commits.
    """
    if task_id is None:
        return None
    db.flush()
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        return None
    runs = db.query(ProductionRun).filter(ProductionRun.task_id == task.id).all()
    if not runs:
        return None
    if all(_norm(r.status) in FINISHED_RUN_STATUSES for r in runs):
        if _norm(task.status) not in CLOSED_TASK_STATUSES:
            task.status = "DONE"
            task.progress = 1.0
        return task
    if _norm(task.status) not in CLOSED_TASK_STATUSES:
        _sync_quantity_progress(task, runs)
    return None


def _sync_quantity_progress(task: Task, runs) -> None:
    """Fractional progress from open runs; CANCELLED runs excluded."""
    open_runs = [r for r in runs if _norm(r.status) != "CANCELLED"]
    target = sum(int(r.quantity_target or 0) for r in open_runs)
    if target <= 0:
        return
    done = sum(int(r.quantity_completed or 0) for r in open_runs)
    task.progress = round(min(1.0, done / target), 4)


def sync_order_completion(db: Session, order_id: Optional[UUID]) -> Optional[Order]:
    """Mark an order COMPLETED when all of its tasks are DONE/COMPLETED.

    Returns the order when it reads COMPLETED afterwards, else None.
    Never commits.
    """
    if order_id is None:
        return None
    db.flush()
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        return None
    tasks = db.query(Task).filter(Task.order_id == order.id).all()
    if not tasks:
        return None
    if not all(_norm(t.status) in CLOSED_TASK_STATUSES for t in tasks):
        return None
    if _norm(order.status) != "COMPLETED":
        order.status = "COMPLETED"
    return order


def reopen_order_if_needed(db: Session, order_id: Optional[UUID]) -> Optional[Order]:
    """Return a COMPLETED/DONE order to IN_PROGRESS while work is open.

    Fires only when the order exists, has >= 1 task, reads COMPLETED/DONE,
    and at least one task is not DONE/COMPLETED (e.g. a new task was just
    added under it). Zero-task orders, missing/other-factory orders, and
    non-completed statuses (PENDING, IN_PROGRESS, CANCELLED, ...) are
    untouched. Never commits.
    """
    if order_id is None:
        return None
    db.flush()
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        return None
    if _norm(order.status) not in ("COMPLETED", "DONE"):
        return None
    tasks = db.query(Task).filter(Task.order_id == order.id).all()
    if not tasks:
        return None
    if all(_norm(t.status) in CLOSED_TASK_STATUSES for t in tasks):
        return None
    order.status = "IN_PROGRESS"
    return order
