"""Focused tests: production reliability fixes (status, quantities, FK scope).

Uses the live dev DB with uniquely-marked temp rows; cleans up after itself.

Run: py -3 -m unittest backend.tests.test_production -v
"""
import unittest
from uuid import uuid4

from fastapi import HTTPException

from backend.api.endpoints import production as ep
from backend.schemas.production import ProductionRunCreate, ProductionRunUpdate


def _tag(prefix):
    return f"{prefix}-{uuid4().hex[:8]}"


class TestProductionLive(unittest.TestCase):
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

    def _make_order(self, db, number):
        from backend.models.models import Order
        o = Order(order_number=number)
        db.add(o)
        db.commit()
        db.refresh(o)
        self.addCleanup(lambda: self._wipe(Order, Order.order_number, number))
        return o

    def _make_machine(self, db, name):
        from backend.models.models import Machine
        m = Machine(name=name)
        db.add(m)
        db.commit()
        db.refresh(m)
        self.addCleanup(lambda: self._wipe(Machine, Machine.name, name))
        return m

    def _make_task(self, db, name):
        from backend.models.models import Task
        t = Task(name=name)
        db.add(t)
        db.commit()
        db.refresh(t)
        self.addCleanup(lambda: self._wipe(Task, Task.name, name))
        return t

    def _wipe(self, model, field, value):
        db = self.SessionLocal()
        try:
            db.query(model).filter(field == value).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def _create_run(self, db, **kwargs):
        run = ep.create_production(ProductionRunCreate(**kwargs), db=db)
        self.addCleanup(lambda: self._wipe_id(run.id))
        return run

    def _wipe_id(self, run_id):
        from backend.models.models import ProductionRun
        db = self.SessionLocal()
        try:
            db.query(ProductionRun).filter(ProductionRun.id == run_id).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    # ---- status ----

    def test_status_normalization(self):
        db = self._db(self.fid_a)
        run = self._create_run(db, status="in_progress", quantity_target=10)
        self.assertEqual(run.status, "IN_PROGRESS")
        run2 = self._create_run(db, status="  Planned ", quantity_target=0)
        self.assertEqual(run2.status, "PLANNED")

    def test_invalid_status_rejected(self):
        db = self._db(self.fid_a)
        with self.assertRaises(HTTPException) as cm:
            ep.create_production(ProductionRunCreate(status="RUNING"), db=db)
        self.assertEqual(cm.exception.status_code, 422)
        run = self._create_run(db)
        with self.assertRaises(HTTPException) as cm:
            ep.update_production(run.id, ProductionRunUpdate(status="bogus"), db=db)
        self.assertEqual(cm.exception.status_code, 422)

    def test_status_filter_case_insensitive(self):
        db = self._db(self.fid_a)
        self._create_run(db, status="PLANNED")
        lower = ep.get_productions(status="planned", db=db)
        upper = ep.get_productions(status="PLANNED", db=db)
        mixed = ep.get_productions(status="Planned", db=db)
        self.assertEqual({r.id for r in lower}, {r.id for r in upper})
        self.assertEqual({r.id for r in lower}, {r.id for r in mixed})
        self.assertGreaterEqual(len(lower), 1)

    # ---- quantities ----

    def test_valid_quantities(self):
        db = self._db(self.fid_a)
        run = self._create_run(db, quantity_target=0, quantity_completed=0)
        self.assertEqual((run.quantity_target, run.quantity_completed), (0, 0))
        run2 = self._create_run(db, quantity_target=100, quantity_completed=100)
        self.assertEqual(run2.quantity_completed, 100)

    def test_negative_quantity_rejected(self):
        db = self._db(self.fid_a)
        with self.assertRaises(HTTPException) as cm:
            ep.create_production(
                ProductionRunCreate(quantity_target=-1, quantity_completed=0), db=db)
        self.assertEqual(cm.exception.status_code, 422)
        run = self._create_run(db)
        with self.assertRaises(HTTPException) as cm:
            ep.update_production(run.id, ProductionRunUpdate(quantity_completed=-5), db=db)
        self.assertEqual(cm.exception.status_code, 422)

    def test_completed_over_target_rejected(self):
        db = self._db(self.fid_a)
        with self.assertRaises(HTTPException) as cm:
            ep.create_production(
                ProductionRunCreate(quantity_target=10, quantity_completed=11), db=db)
        self.assertEqual(cm.exception.status_code, 422)
        run = self._create_run(db, quantity_target=10, quantity_completed=5)
        with self.assertRaises(HTTPException) as cm:
            ep.update_production(run.id, ProductionRunUpdate(quantity_completed=20), db=db)
        self.assertEqual(cm.exception.status_code, 422)
        # lowering target below existing completed is also rejected
        with self.assertRaises(HTTPException) as cm:
            ep.update_production(run.id, ProductionRunUpdate(quantity_target=2), db=db)
        self.assertEqual(cm.exception.status_code, 422)

    # ---- FK scope ----

    def test_bogus_uuid_returns_404_not_500(self):
        db = self._db(self.fid_a)
        with self.assertRaises(HTTPException) as cm:
            ep.create_production(ProductionRunCreate(order_id=uuid4()), db=db)
        self.assertEqual(cm.exception.status_code, 404)
        with self.assertRaises(HTTPException) as cm:
            ep.create_production(ProductionRunCreate(task_id=uuid4()), db=db)
        self.assertEqual(cm.exception.status_code, 404)
        with self.assertRaises(HTTPException) as cm:
            ep.create_production(ProductionRunCreate(machine_id=uuid4()), db=db)
        self.assertEqual(cm.exception.status_code, 404)

    def test_cross_factory_references_rejected(self):
        db_b = self._db(self.fid_b)
        order = self._make_order(db_b, _tag("ORDX"))
        machine = self._make_machine(db_b, _tag("MACX"))
        task = self._make_task(db_b, _tag("TSKX"))
        db_a = self._db(self.fid_a)
        for kwargs in ({"order_id": order.id}, {"task_id": task.id}, {"machine_id": machine.id}):
            with self.assertRaises(HTTPException) as cm:
                ep.create_production(ProductionRunCreate(**kwargs), db=db_a)
            self.assertEqual(cm.exception.status_code, 404, kwargs)
            # generic message: no leak of the other factory's data
            self.assertIn("Unknown", cm.exception.detail)

    def test_same_factory_references_work(self):
        db = self._db(self.fid_a)
        order = self._make_order(db, _tag("ORDX"))
        machine = self._make_machine(db, _tag("MACX"))
        task = self._make_task(db, _tag("TSKX"))
        run = self._create_run(db, order_id=order.id, task_id=task.id, machine_id=machine.id)
        self.assertEqual((run.order_id, run.task_id, run.machine_id),
                         (order.id, task.id, machine.id))

    def test_nullable_references(self):
        db = self._db(self.fid_a)
        run = self._create_run(db)  # all links None
        self.assertIsNone(run.order_id)
        # unlink on update
        order = self._make_order(db, _tag("ORDX"))
        run2 = self._create_run(db, order_id=order.id)
        updated = ep.update_production(run2.id, ProductionRunUpdate(order_id=None), db=db)
        self.assertIsNone(updated.order_id)

    def test_factory_stamping(self):
        db = self._db(self.fid_a)
        run = self._create_run(db, quantity_target=5)
        self.assertEqual(run.factory_id, self.fid_a)


if __name__ == "__main__":
    unittest.main(verbosity=2)
