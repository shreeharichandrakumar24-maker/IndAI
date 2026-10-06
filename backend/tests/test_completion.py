"""Focused tests: automatic Production -> Task -> Order completion.

Uses the live dev DB with uniquely-marked temp rows; cleans up after itself.
Only exercises production/task/order endpoints + the completion service.

Run: python -m unittest backend.tests.test_completion -v
"""
import unittest
from uuid import uuid4

from backend.api.endpoints import production as prod_ep
from backend.api.endpoints import tasks as task_ep
from backend.schemas.production import ProductionRunCreate, ProductionRunUpdate
from backend.schemas.task import TaskCreate, TaskUpdate
from backend.services.completion import reopen_order_if_needed, sync_order_completion, sync_task_completion


def _tag(prefix):
    return f"{prefix}-{uuid4().hex[:8]}"


class TestCompletionPropagation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.db.database import SessionLocal
        cls.SessionLocal = SessionLocal
        cls.fid_a = uuid4()
        cls.fid_b = uuid4()

    def _db(self, fid=None):
        from backend.db.scoping import set_factory_scope
        db = self.SessionLocal()
        self.addCleanup(db.close)
        if fid is not None:
            set_factory_scope(db, fid, False)
        return db

    # ---- fixtures ----

    def _wipe(self, model, field, value):
        db = self.SessionLocal()
        try:
            db.query(model).filter(field == value).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def _make_order(self, db, number, **kwargs):
        from backend.models.models import Order
        o = Order(order_number=number, **kwargs)
        db.add(o)
        db.commit()
        db.refresh(o)
        self.addCleanup(lambda n=number: self._wipe(Order, Order.order_number, n))
        return o

    def _make_task(self, db, name, **kwargs):
        from backend.models.models import Task
        t = Task(name=name, **kwargs)
        db.add(t)
        db.commit()
        db.refresh(t)
        self.addCleanup(lambda n=name: self._wipe(Task, Task.name, n))
        return t

    def _make_run(self, db, **kwargs):
        run = prod_ep.create_production(ProductionRunCreate(**kwargs), db=db)
        self.addCleanup(lambda rid=run.id: self._wipe_id(rid))
        return run

    def _wipe_id(self, run_id):
        from backend.models.models import ProductionRun
        db = self.SessionLocal()
        try:
            db.query(ProductionRun).filter(ProductionRun.id == run_id).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def _fresh_task(self, task_id):
        from backend.models.models import Task
        db = self.SessionLocal()
        try:
            return db.query(Task).filter(Task.id == task_id).first()
        finally:
            db.close()

    def _fresh_order(self, order_id):
        from backend.models.models import Order
        db = self.SessionLocal()
        try:
            return db.query(Order).filter(Order.id == order_id).first()
        finally:
            db.close()

    # ---- A: one task + one run, RUNNING -> DONE => task DONE, 100% ----

    def test_a_single_run_completes_task(self):
        db = self._db(self.fid_a)
        order = self._make_order(db, _tag("ORDC"))
        task = self._make_task(db, _tag("TSKC"), order_id=order.id, status="IN_PROGRESS")
        run = self._make_run(db, task_id=task.id, order_id=order.id, status="RUNNING")
        prod_ep.update_production(run.id, ProductionRunUpdate(status="DONE"), db=db)
        fresh = self._fresh_task(task.id)
        self.assertEqual(fresh.status, "DONE")
        self.assertEqual(fresh.progress, 1.0)

    # ---- B: one DONE + one RUNNING => task NOT done ----

    def test_b_partial_runs_keep_task_open(self):
        db = self._db(self.fid_a)
        task = self._make_task(db, _tag("TSKC"), status="IN_PROGRESS")
        r1 = self._make_run(db, task_id=task.id, status="RUNNING")
        self._make_run(db, task_id=task.id, status="RUNNING")
        prod_ep.update_production(r1.id, ProductionRunUpdate(status="DONE"), db=db)
        fresh = self._fresh_task(task.id)
        self.assertNotIn((fresh.status or "").upper(), ("DONE", "COMPLETED"))

    # ---- C: all runs DONE => task DONE ----

    def test_c_all_runs_done_completes_task(self):
        db = self._db(self.fid_a)
        task = self._make_task(db, _tag("TSKC"), status="IN_PROGRESS")
        r1 = self._make_run(db, task_id=task.id, status="RUNNING")
        r2 = self._make_run(db, task_id=task.id, status="RUNNING")
        prod_ep.update_production(r1.id, ProductionRunUpdate(status="DONE"), db=db)
        prod_ep.update_production(r2.id, ProductionRunUpdate(status="COMPLETED"), db=db)
        fresh = self._fresh_task(task.id)
        self.assertEqual(fresh.status, "DONE")
        self.assertEqual(fresh.progress, 1.0)

    # ---- D: task with zero runs never auto-completes ----

    def test_d_task_without_runs_stays_open(self):
        db = self._db(self.fid_a)
        task = self._make_task(db, _tag("TSKC"), status="IN_PROGRESS")
        self.assertIsNone(sync_task_completion(db, task.id))
        fresh = self._fresh_task(task.id)
        self.assertEqual(fresh.status, "IN_PROGRESS")

    # ---- E: one DONE + one IN_PROGRESS task => order NOT completed ----

    def test_e_partial_tasks_keep_order_open(self):
        db = self._db(self.fid_a)
        order = self._make_order(db, _tag("ORDC"), status="IN_PROGRESS")
        t1 = self._make_task(db, _tag("TSKC"), order_id=order.id, status="IN_PROGRESS")
        self._make_task(db, _tag("TSKC"), order_id=order.id, status="IN_PROGRESS")
        task_ep.update_task(t1.id, TaskUpdate(status="DONE"), db=db)
        fresh = self._fresh_order(order.id)
        self.assertNotEqual((fresh.status or "").upper(), "COMPLETED")

    # ---- F: all tasks DONE => order COMPLETED ----

    def test_f_all_tasks_done_completes_order(self):
        db = self._db(self.fid_a)
        order = self._make_order(db, _tag("ORDC"), status="IN_PROGRESS")
        t1 = self._make_task(db, _tag("TSKC"), order_id=order.id, status="IN_PROGRESS")
        t2 = self._make_task(db, _tag("TSKC"), order_id=order.id, status="IN_PROGRESS")
        task_ep.update_task(t1.id, TaskUpdate(status="DONE"), db=db)
        task_ep.update_task(t2.id, TaskUpdate(status="COMPLETED"), db=db)
        fresh = self._fresh_order(order.id)
        self.assertEqual(fresh.status, "COMPLETED")

    # ---- G: CANCELLED run never completes the task ----

    def test_g_cancelled_run_does_not_complete_task(self):
        db = self._db(self.fid_a)
        task = self._make_task(db, _tag("TSKC"), status="IN_PROGRESS")
        run = self._make_run(db, task_id=task.id, status="RUNNING")
        prod_ep.update_production(run.id, ProductionRunUpdate(status="CANCELLED"), db=db)
        fresh = self._fresh_task(task.id)
        self.assertNotIn((fresh.status or "").upper(), ("DONE", "COMPLETED"))

    # ---- H: cross-factory rows never participate ----

    def test_h_cross_factory_sync_is_noop(self):
        db_a = self._db(self.fid_a)
        order = self._make_order(db_a, _tag("ORDC"), status="IN_PROGRESS")
        task = self._make_task(db_a, _tag("TSKC"), order_id=order.id, status="IN_PROGRESS")
        db_b = self._db(self.fid_b)
        # From factory B's scope the task reads as not-found: pure no-op.
        self.assertIsNone(sync_task_completion(db_b, task.id))
        self.assertIsNone(sync_order_completion(db_b, order.id))
        fresh_t = self._fresh_task(task.id)
        fresh_o = self._fresh_order(order.id)
        self.assertEqual(fresh_t.status, "IN_PROGRESS")
        self.assertEqual(fresh_o.status, "IN_PROGRESS")

    # ---- Bug 1: completed order + new pending task reopens ----

    def test_completed_order_reopens_on_new_task(self):
        db = self._db(self.fid_a)
        order = self._make_order(db, _tag("ORDC"), status="IN_PROGRESS")
        t1 = self._make_task(db, _tag("TSKC"), order_id=order.id, status="IN_PROGRESS")
        t2 = self._make_task(db, _tag("TSKC"), order_id=order.id, status="IN_PROGRESS")
        task_ep.update_task(t1.id, TaskUpdate(status="DONE"), db=db)
        task_ep.update_task(t2.id, TaskUpdate(status="DONE"), db=db)
        self.assertEqual(self._fresh_order(order.id).status, "COMPLETED")
        task_ep.create_task(TaskCreate(name=_tag("TSKC"), order_id=order.id), db=db)
        self.assertEqual(self._fresh_order(order.id).status, "IN_PROGRESS")

    def test_completed_order_stays_completed_on_done_task(self):
        db = self._db(self.fid_a)
        order = self._make_order(db, _tag("ORDC"), status="IN_PROGRESS")
        t1 = self._make_task(db, _tag("TSKC"), order_id=order.id, status="IN_PROGRESS")
        task_ep.update_task(t1.id, TaskUpdate(status="DONE"), db=db)
        self.assertEqual(self._fresh_order(order.id).status, "COMPLETED")
        task_ep.create_task(TaskCreate(name=_tag("TSKC"), order_id=order.id, status="DONE"), db=db)
        self.assertEqual(self._fresh_order(order.id).status, "COMPLETED")

    def test_moved_task_reopens_previous_order(self):
        db = self._db(self.fid_a)
        o1 = self._make_order(db, _tag("ORDC"), status="IN_PROGRESS")
        o2 = self._make_order(db, _tag("ORDC"), status="IN_PROGRESS")
        t1 = self._make_task(db, _tag("TSKC"), order_id=o1.id, status="IN_PROGRESS")
        t2 = self._make_task(db, _tag("TSKC"), order_id=o2.id, status="IN_PROGRESS")
        task_ep.update_task(t2.id, TaskUpdate(status="DONE"), db=db)
        self.assertEqual(self._fresh_order(o2.id).status, "COMPLETED")
        # Move open t1 into completed o2: o2 reopens; emptied o1 is untouched.
        task_ep.update_task(t1.id, TaskUpdate(order_id=o2.id), db=db)
        self.assertEqual(self._fresh_order(o2.id).status, "IN_PROGRESS")
        self.assertEqual(self._fresh_order(o1.id).status, "IN_PROGRESS")

    # ---- Bug 2: task-centric production ----

    def test_run_derives_order_from_task(self):
        db = self._db(self.fid_a)
        order = self._make_order(db, _tag("ORDC"))
        task = self._make_task(db, _tag("TSKC"), order_id=order.id)
        run = self._make_run(db, task_id=task.id, status="PLANNED")
        self.assertEqual(run.order_id, order.id)

    def test_explicit_order_id_is_never_overwritten(self):
        db = self._db(self.fid_a)
        o1 = self._make_order(db, _tag("ORDC"))
        o2 = self._make_order(db, _tag("ORDC"))
        task = self._make_task(db, _tag("TSKC"), order_id=o1.id)
        run = self._make_run(db, task_id=task.id, order_id=o2.id)
        self.assertEqual(run.order_id, o2.id)

    def test_cross_factory_task_reference_rejected(self):
        from fastapi import HTTPException
        db_b = self._db(self.fid_b)
        task_b = self._make_task(db_b, _tag("TSKC"))
        db_a = self._db(self.fid_a)
        with self.assertRaises(HTTPException) as cm:
            self._make_run(db_a, task_id=task_b.id)
        self.assertEqual(cm.exception.status_code, 404)

    def test_orderless_task_run_affects_no_order(self):
        db = self._db(self.fid_a)
        task = self._make_task(db, _tag("TSKC"), status="IN_PROGRESS")
        run = self._make_run(db, task_id=task.id, status="RUNNING")
        self.assertIsNone(run.order_id)
        prod_ep.update_production(run.id, ProductionRunUpdate(status="DONE"), db=db)
        self.assertEqual(self._fresh_task(task.id).status, "DONE")

    def test_order_only_run_leaves_order_open(self):
        db = self._db(self.fid_a)
        order = self._make_order(db, _tag("ORDC"), status="IN_PROGRESS")
        run = self._make_run(db, order_id=order.id, status="RUNNING")
        prod_ep.update_production(run.id, ProductionRunUpdate(status="DONE"), db=db)
        self.assertEqual(self._fresh_order(order.id).status, "IN_PROGRESS")

    # ---- Task progress from quantities ----

    def test_quantity_progress_single_run(self):
        db = self._db(self.fid_a)
        task = self._make_task(db, _tag("TSKC"), status="IN_PROGRESS")
        self._make_run(db, task_id=task.id, status="RUNNING",
                       quantity_target=100, quantity_completed=40)
        fresh = self._fresh_task(task.id)
        self.assertEqual(fresh.progress, 0.4)
        self.assertNotIn((fresh.status or "").upper(), ("DONE", "COMPLETED"))

    def test_quantity_progress_aggregates(self):
        db = self._db(self.fid_a)
        task = self._make_task(db, _tag("TSKC"), status="IN_PROGRESS")
        self._make_run(db, task_id=task.id, status="RUNNING",
                       quantity_target=60, quantity_completed=40)
        self._make_run(db, task_id=task.id, status="RUNNING",
                       quantity_target=40, quantity_completed=30)
        fresh = self._fresh_task(task.id)
        self.assertEqual(fresh.progress, 0.7)
        self.assertEqual(fresh.status, "IN_PROGRESS")

    def test_quantity_progress_ignores_cancelled(self):
        db = self._db(self.fid_a)
        task = self._make_task(db, _tag("TSKC"), status="IN_PROGRESS")
        r1 = self._make_run(db, task_id=task.id, status="RUNNING",
                            quantity_target=50, quantity_completed=50)
        r2 = self._make_run(db, task_id=task.id, status="RUNNING",
                            quantity_target=50, quantity_completed=50)
        prod_ep.update_production(r1.id, ProductionRunUpdate(status="DONE"), db=db)
        prod_ep.update_production(r2.id, ProductionRunUpdate(status="CANCELLED"), db=db)
        fresh = self._fresh_task(task.id)
        # Quantities hit 100% but completion is status-based: still open.
        self.assertEqual(fresh.progress, 1.0)
        self.assertNotIn((fresh.status or "").upper(), ("DONE", "COMPLETED"))


    def test_done_action_payload_completes_chain_idempotently(self):
        # The UI DONE button sends exactly {status: 'COMPLETED'}; the second
        # call must be a harmless no-op, never a duplicate or error.
        db = self._db(self.fid_a)
        order = self._make_order(db, _tag("ORDC"), status="IN_PROGRESS")
        task = self._make_task(db, _tag("TSKC"), order_id=order.id, status="IN_PROGRESS")
        run = self._make_run(db, task_id=task.id, order_id=order.id, status="RUNNING")
        prod_ep.update_production(run.id, ProductionRunUpdate(status="COMPLETED"), db=db)
        self.assertEqual(self._fresh_task(task.id).status, "DONE")
        self.assertEqual(self._fresh_order(order.id).status, "COMPLETED")
        again = prod_ep.update_production(run.id, ProductionRunUpdate(status="COMPLETED"), db=db)
        self.assertEqual(again.status, "COMPLETED")
        self.assertEqual(self._fresh_task(task.id).status, "DONE")
        self.assertEqual(self._fresh_order(order.id).status, "COMPLETED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
