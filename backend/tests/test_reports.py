"""Focused tests: reports (order final, weekly, monthly, order statuses).

Read-only endpoints: every test also asserts no database writes happened.

Run: py -3 -m unittest backend.tests.test_reports -v
"""
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException

from backend.api.endpoints import reports as rep
from backend.api.endpoints import orders as ord_ep
from backend.schemas.order import OrderCreate, OrderUpdate


def _tag(prefix):
    return f"{prefix}-{uuid4().hex[:8]}"


class _Base(unittest.TestCase):
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

    def _snapshot(self, db):
        from backend.models.models import (AIRecommendation, Employee, FactoryMemory, Incident,
                                           Machine, Maintenance, Order, ProductionRun, Task)
        counts = {}
        for model in (Order, ProductionRun, Task, Employee, Machine, Incident, Maintenance,
                      FactoryMemory, AIRecommendation):
            counts[model.__tablename__] = db.query(model).count()
        return counts

    def assertNoWrites(self, db, before):
        self.assertEqual(self._snapshot(db), before)

    def _wipe(self, model, field, value):
        db = self.SessionLocal()
        try:
            db.query(model).filter(field == value).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


class TestOrderReport(_Base):
    def _make_order(self, db, number, **kwargs):
        from backend.models.models import Order
        o = Order(order_number=number, **kwargs)
        db.add(o)
        db.commit()
        db.refresh(o)
        self.addCleanup(lambda: self._wipe(Order, Order.order_number, number))
        return o

    def test_valid_order_report(self):
        from backend.models.models import Employee, Machine, Task
        db = self._db(self.fid_a)
        before = self._snapshot(db)
        num = _tag("ORDR")
        order = self._make_order(db, num, customer_name="Acme", product="Brackets",
                                 quantity=100, status="IN_PROGRESS")
        emp = Employee(name=_tag("EMP"), role="Tester")
        db.add(emp)
        db.commit()
        db.refresh(emp)
        self.addCleanup(lambda: self._wipe(Employee, Employee.name, emp.name))
        mac = Machine(name=_tag("MAC"))
        db.add(mac)
        db.commit()
        db.refresh(mac)
        self.addCleanup(lambda: self._wipe(Machine, Machine.name, mac.name))
        t = Task(name=_tag("TSK"), order_id=order.id, employee_id=emp.id,
                 machine_id=mac.id, status="DONE", progress=1.0)
        db.add(t)
        db.commit()
        from backend.models.models import ProductionRun
        run = ProductionRun(order_id=order.id, task_id=t.id, machine_id=mac.id,
                            quantity_target=100, quantity_completed=40, status="IN_PROGRESS")
        db.add(run)
        db.commit()
        self.addCleanup(lambda: self._wipe(ProductionRun, ProductionRun.id, run.id))

        out = rep.build_order_report(db, order.id)
        self.assertEqual(out["order"]["order_number"], num)
        self.assertFalse(out["order"]["is_final"])
        self.assertEqual(out["order"]["report_label"], "Order Report")
        self.assertEqual(out["production"]["run_count"], 1)
        self.assertEqual(out["production"]["target_quantity"], 100)
        self.assertEqual(out["production"]["completed_quantity"], 40)
        self.assertEqual(out["tasks"]["total"], 1)
        self.assertEqual(out["tasks"]["completed"], 1)
        self.assertEqual(out["tasks"]["items"][0]["employee_name"], emp.name)
        self.assertEqual(out["machines"]["count"], 1)
        self.assertEqual(out["summary"]["remaining_quantity"], 60)
        self.assertNoWrites(db, {**before,
                                 "orders": before["orders"] + 1,
                                 "employees": before["employees"] + 1,
                                 "machines": before["machines"] + 1,
                                 "tasks": before["tasks"] + 1,
                                 "production_runs": before["production_runs"] + 1})

    def test_completed_order_final_report(self):
        db = self._db(self.fid_a)
        num = _tag("ORDR")
        order = self._make_order(db, num, quantity=50, status="COMPLETED")
        from backend.models.models import ProductionRun
        run = ProductionRun(order_id=order.id, quantity_target=50,
                            quantity_completed=50, status="COMPLETED")
        db.add(run)
        db.commit()
        self.addCleanup(lambda: self._wipe(ProductionRun, ProductionRun.id, run.id))
        before = self._snapshot(db)
        out = rep.build_order_report(db, order.id)
        self.assertTrue(out["order"]["is_final"])
        self.assertEqual(out["order"]["report_label"], "Final Report")
        self.assertEqual(out["summary"]["remaining_quantity"], 0)
        self.assertNoWrites(db, before)

    def test_nonexistent_order_404(self):
        db = self._db(self.fid_a)
        before = self._snapshot(db)
        with self.assertRaises(HTTPException) as cm:
            rep.build_order_report(db, uuid4())
        self.assertEqual(cm.exception.status_code, 404)
        self.assertNoWrites(db, before)

    def test_cross_factory_order_404(self):
        db_b = self._db(self.fid_b)
        num = _tag("ORDR")
        order = self._make_order(db_b, num, status="COMPLETED")
        db_a = self._db(self.fid_a)
        before = self._snapshot(db_a)
        with self.assertRaises(HTTPException) as cm:
            rep.build_order_report(db_a, order.id)
        self.assertEqual(cm.exception.status_code, 404)
        self.assertIn("not found", cm.exception.detail.lower())
        self.assertNoWrites(db_a, before)

    def test_incidents_maintenance_ai_linkage(self):
        from backend.models.models import (AIRecommendation, FactoryMemory, Incident,
                                           Machine, Maintenance, Task)
        db = self._db(self.fid_a)
        num = _tag("ORDR")
        order = self._make_order(db, num, status="IN_PROGRESS")
        mac = Machine(name=_tag("MAC"))
        db.add(mac)
        db.commit()
        db.refresh(mac)
        self.addCleanup(lambda: self._wipe(Machine, Machine.name, mac.name))
        t = Task(name=_tag("TSK"), order_id=order.id, machine_id=mac.id, status="IN_PROGRESS")
        db.add(t)
        db.commit()
        db.refresh(t)
        self.addCleanup(lambda: self._wipe(Task, Task.id, t.id))
        inc_direct = Incident(machine_id=mac.id, order_id=order.id,
                              incident_type="TEST", severity="HIGH", status="OPEN")
        inc_task = Incident(machine_id=mac.id, task_id=t.id,
                            incident_type="TEST", severity="LOW", status="OPEN")
        db.add_all([inc_direct, inc_task])
        db.commit()
        self.addCleanup(lambda: self._wipe(Incident, Incident.id, inc_direct.id))
        self.addCleanup(lambda: self._wipe(Incident, Incident.id, inc_task.id))
        mnt = Maintenance(machine_id=mac.id, issue="Test upkeep", status="COMPLETED")
        db.add(mnt)
        db.commit()
        self.addCleanup(lambda: self._wipe(Maintenance, Maintenance.id, mnt.id))
        rec = AIRecommendation(recommendation_type="TEST", entity_type="ORDER",
                               entity_id=order.id, recommendation="Check this",
                               status="PENDING")
        db.add(rec)
        db.commit()
        self.addCleanup(lambda: self._wipe(AIRecommendation, AIRecommendation.id, rec.id))
        mem = FactoryMemory(title="note", event_type="NOTE", order_id=order.id)
        db.add(mem)
        db.commit()
        self.addCleanup(lambda: self._wipe(FactoryMemory, FactoryMemory.id, mem.id))
        before = self._snapshot(db)
        out = rep.build_order_report(db, order.id)
        self.assertEqual(out["incidents"]["linked_count"], 1)
        self.assertEqual(out["incidents"]["related_count"], 1)
        self.assertIn("task", out["incidents"]["related"][0]["via"])
        self.assertEqual(out["maintenance"]["count"], 1)
        self.assertIn("not necessarily order-specific", out["maintenance"]["note"])
        self.assertEqual(out["ai"]["recommendation_count"], 1)
        self.assertEqual(out["ai"]["memory_count"], 1)
        self.assertNoWrites(db, before)

    def test_endpoint_requires_factory(self):
        db = self._db()  # no scope
        with self.assertRaises(HTTPException) as cm:
            rep.order_report(uuid4(), db=db)
        self.assertEqual(cm.exception.status_code, 400)


class TestWeeklyMonthly(_Base):
    def test_weekly_compatible_and_scoped(self):
        db = self._db(self.fid_a)
        before = self._snapshot(db)
        start, end = rep.week_bounds(0)
        out = rep.build_weekly(db, start, end)
        for key in ("orders", "downtime", "top_failing_machines", "decisions"):
            self.assertIn(key, out)
        self.assertIn("completed_this_week", out["orders"])
        self.assertIn("late_now", out["orders"])
        self.assertIn("late_orders", out["orders"])
        self.assertIn("active_total", out["orders"])
        self.assertIn("incidents_raised_this_week", out["downtime"])
        self.assertIn("currently_open", out["downtime"])
        self.assertIn("admin_decisions_this_week", out["decisions"])
        self.assertNoWrites(db, before)

    def test_weekly_new_metrics_present(self):
        db = self._db(self.fid_a)
        out = rep.build_weekly(db, *rep.week_bounds(1))
        self.assertIn("production", out)
        self.assertIn("tasks", out)
        self.assertIn("machines", out)
        self.assertIn("maintenance", out)
        self.assertIn("telemetry", out)
        self.assertIn("employees", out)
        self.assertIn("severity_counts", out["downtime"])
        self.assertIn("completed_basis", out["orders"])

    def test_weekly_requires_factory(self):
        db = self._db()
        with self.assertRaises(HTTPException) as cm:
            rep.weekly_report(0, db=db)
        self.assertEqual(cm.exception.status_code, 400)

    def test_monthly_valid_and_scoped(self):
        db = self._db(self.fid_a)
        before = self._snapshot(db)
        out = rep.monthly_report("2026-09", db=db)
        self.assertEqual(out["month"], "2026-09")
        self.assertIn("period_start", out)
        self.assertIn("orders", out)
        self.assertIn("production", out)
        self.assertIn("tasks", out)
        self.assertNoWrites(db, before)

    def test_monthly_bounds(self):
        start, end = rep.month_bounds("2026-02")
        self.assertEqual((start.day, start.month), (1, 2))
        self.assertEqual((end.day, end.month), (28, 2))
        start, end = rep.month_bounds("2026-12")
        self.assertEqual(end.day, 31)

    def test_monthly_invalid(self):
        db = self._db(self.fid_a)
        for bad in ("2026-13", "2026-9", "sept", "", "2026/09"):
            with self.assertRaises(HTTPException, msg=bad):
                rep.monthly_report(bad, db=db)

    def test_monthly_requires_factory(self):
        db = self._db()
        with self.assertRaises(HTTPException) as cm:
            rep.monthly_report("2026-09", db=db)
        self.assertEqual(cm.exception.status_code, 400)

    def test_factory_isolation(self):
        from backend.models.models import Order
        num = _tag("ORDR")
        db_b = self._db(self.fid_b)
        order = Order(order_number=num, status="PENDING")
        db_b.add(order)
        db_b.commit()
        self.addCleanup(lambda: self._wipe(Order, Order.order_number, num))
        db_a = self._db(self.fid_a)
        out = rep.build_weekly(db_a, *rep.week_bounds(0))
        late_numbers = [o["order_number"] for o in out["orders"]["late_orders"]]
        self.assertNotIn(num, late_numbers)


class TestOrderStatus(_Base):
    def test_normalization(self):
        db = self._db(self.fid_a)
        from backend.models.models import Order
        num = _tag("ORDR")
        order = ord_ep.create_order(OrderCreate(order_number=num, status="  completed "), db=db)
        self.assertEqual(order.status, "COMPLETED")
        self.addCleanup(lambda: self._wipe(Order, Order.order_number, num))
        updated = ord_ep.update_order(order.id, OrderUpdate(status="in_progress"), db=db)
        self.assertEqual(updated.status, "IN_PROGRESS")

    def test_invalid_status_rejected(self):
        db = self._db(self.fid_a)
        with self.assertRaises(HTTPException) as cm:
            ord_ep.create_order(OrderCreate(order_number=_tag("ORDR"), status="BOGUS"), db=db)
        self.assertEqual(cm.exception.status_code, 422)
        from backend.models.models import Order
        num = _tag("ORDR")
        order = ord_ep.create_order(OrderCreate(order_number=num), db=db)
        self.addCleanup(lambda: self._wipe(Order, Order.order_number, num))
        with self.assertRaises(HTTPException) as cm:
            ord_ep.update_order(order.id, OrderUpdate(status="NOPE"), db=db)
        self.assertEqual(cm.exception.status_code, 422)

    def test_existing_valid_statuses_work(self):
        from backend.models.models import Order
        db = self._db(self.fid_a)
        for status in ("PENDING", "IN_PROGRESS", "COMPLETED", "DONE", "CANCELLED"):
            num = _tag("ORDR")
            order = ord_ep.create_order(OrderCreate(order_number=num, status=status), db=db)
            self.assertEqual(order.status, status)
            self.addCleanup(lambda n=num: self._wipe(Order, Order.order_number, n))


if __name__ == "__main__":
    unittest.main(verbosity=2)
