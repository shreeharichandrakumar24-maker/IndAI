"""Focused tests: natural-language what-if simulation (read-only).

Uses the live dev DB with uniquely-marked temp rows; cleans up after itself.
The LLM narrative is stubbed to LLMUnavailable so tests are deterministic.

Run: python -m unittest backend.tests.test_what_if -v
"""
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.api.endpoints import what_if as ep
from backend.schemas.what_if import WhatIfRequest
from backend.services import what_if as engine
from backend.services.llm import LLMUnavailable


def _tag(prefix):
    return f"{prefix}-{uuid4().hex[:8]}"


class TestWhatIf(unittest.TestCase):
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

    def _wipe(self, model, field, value):
        db = self.SessionLocal()
        try:
            db.query(model).filter(field == value).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def _make_employee(self, db, name, **kwargs):
        from backend.models.models import Employee
        kw = {"role": "Operator", "status": "ACTIVE", "availability": "AVAILABLE"}
        kw.update(kwargs)
        e = Employee(name=name, **kw)
        db.add(e)
        db.commit()
        db.refresh(e)
        self.addCleanup(lambda n=name: self._wipe(Employee, Employee.name, n))
        return e

    def _make_machine(self, db, name, code=None, **kwargs):
        from backend.models.models import Machine
        kw = {"machine_type": "CNC", "status": "OPERATIONAL", "health_status": "GOOD"}
        if code is not None:
            kw["machine_code"] = code
        kw.update(kwargs)
        m = Machine(name=name, **kw)
        db.add(m)
        db.commit()
        db.refresh(m)
        self.addCleanup(lambda n=name: self._wipe(Machine, Machine.name, n))
        return m

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
        from backend.models.models import ProductionRun
        r = ProductionRun(**kwargs)
        db.add(r)
        db.commit()
        db.refresh(r)
        self.addCleanup(lambda rid=r.id: self._wipe(ProductionRun, ProductionRun.id, rid))
        return r

    def _simulate(self, db, text):
        with patch.object(ep, "complete_json", side_effect=LLMUnavailable("no key")):
            return ep.simulate_what_if(WhatIfRequest(scenario=text), db=db)

    # ---- parsing ----

    def test_parse_employee_leave(self):
        db = self._db(self.fid_a)
        name = _tag("Ravi")
        emp = self._make_employee(db, name)
        out = engine.parse_scenario(db, f"What if {name} takes leave for 2 days?")
        self.assertEqual(out["type"], "EMPLOYEE_LEAVE")
        self.assertEqual(out["employee_id"], emp.id)
        self.assertEqual(out["duration_hours"], 48)

    def test_parse_machine_unavailable(self):
        db = self._db(self.fid_a)
        code = f"MC-{uuid4().int % 900 + 100}"
        mac = self._make_machine(db, _tag("CNCW"), code=code)
        out = engine.parse_scenario(db, f"What if {code} is unavailable for 4 hours?")
        self.assertEqual(out["type"], "MACHINE_UNAVAILABLE")
        self.assertEqual(out["machine_id"], mac.id)
        self.assertEqual(out["duration_hours"], 4)

    def test_unknown_employee_is_clear_error(self):
        db = self._db(self.fid_a)
        with self.assertRaises(engine.WhatIfError) as cm:
            engine.parse_scenario(db, "What if Zzzghost Person takes leave for 2 days?")
        self.assertIn("couldn't identify the employee", cm.exception.detail)

    def test_unknown_machine_is_clear_error(self):
        db = self._db(self.fid_a)
        with self.assertRaises(engine.WhatIfError) as cm:
            engine.parse_scenario(db, "What if ZZZ-9999 goes for maintenance for 1 day?")
        self.assertIn("couldn't identify the machine", cm.exception.detail)

    def test_unsupported_scenario_rejected(self):
        db = self._db(self.fid_a)
        with self.assertRaises(engine.WhatIfError) as cm:
            engine.parse_scenario(db, "What if it rains tomorrow for 2 days?")
        self.assertIn("employee leave and machine unavailability", cm.exception.detail)

    def test_missing_duration_required(self):
        db = self._db(self.fid_a)
        name = _tag("Ravi")
        self._make_employee(db, name)
        with self.assertRaises(engine.WhatIfError) as cm:
            engine.parse_scenario(db, f"What if {name} takes leave?")
        self.assertIn("duration", cm.exception.detail)

    # ---- cross-factory ----

    def test_cross_factory_employee_cannot_be_simulated(self):
        db_b = self._db(self.fid_b)
        name = _tag("Ravi")
        self._make_employee(db_b, name)
        db_a = self._db(self.fid_a)
        with self.assertRaises(engine.WhatIfError):
            engine.parse_scenario(db_a, f"What if {name} takes leave for 2 days?")

    def test_cross_factory_machine_cannot_be_simulated(self):
        db_b = self._db(self.fid_b)
        code = f"MC-{uuid4().int % 900 + 100}"
        self._make_machine(db_b, _tag("CNCW"), code=code)
        db_a = self._db(self.fid_a)
        with self.assertRaises(engine.WhatIfError):
            engine.parse_scenario(db_a, f"What if {code} is down for 4 hours?")

    # ---- employee simulation ----

    def test_employee_leave_impact_and_alternative(self):
        db = self._db(self.fid_a)
        ravi = self._make_employee(db, _tag("Ravi"), skills=["welding"])
        arun = self._make_employee(db, _tag("Arun"), skills=["welding"])
        self._make_employee(db, _tag("Meera"), skills=["painting"])
        order = self._make_order(db, _tag("ORDW"))
        self._make_task(db, _tag("TSKW"), employee_id=ravi.id, order_id=order.id,
                        required_skill="welding", status="IN_PROGRESS", progress=0.5)
        self._make_task(db, _tag("TSKW"), employee_id=ravi.id, order_id=order.id,
                        required_skill="welding", status="PENDING")
        res = self._simulate(db, f"What if {ravi.name} takes leave for 2 days?")
        self.assertEqual(res.scenario.type, "EMPLOYEE_LEAVE")
        self.assertEqual(res.impact.affected_tasks, 2)
        self.assertEqual(res.impact.affected_orders, 1)
        self.assertTrue(res.simulation_only)
        alts = [a.name for a in res.alternatives]
        self.assertIn(arun.name, alts)
        self.assertNotIn(ravi.name, alts)
        self.assertIn("0 hours", res.recommendation)

    def test_employee_leave_no_cover_says_so(self):
        db = self._db(self.fid_a)
        ravi = self._make_employee(db, _tag("Ravi"), skills=["exotic-alloy"])
        self._make_task(db, _tag("TSKW"), employee_id=ravi.id,
                        required_skill="exotic-alloy", status="IN_PROGRESS")
        res = self._simulate(db, f"What if {ravi.name} is absent for 8 hours?")
        self.assertEqual(res.alternatives, [])
        self.assertIn("No suitable replacement", res.recommendation)

    # ---- machine simulation ----

    def test_machine_downtime_impact_and_alternative(self):
        db = self._db(self.fid_a)
        code = f"MC-{uuid4().int % 900 + 100}"
        m1 = self._make_machine(db, _tag("CNCW"), code=code, machine_type="Laser")
        m2 = self._make_machine(db, _tag("CNCW"), machine_type="Laser")
        self._make_machine(db, _tag("CNCW"), machine_type="Press")
        order = self._make_order(db, _tag("ORDW"))
        task = self._make_task(db, _tag("TSKW"), order_id=order.id, status="IN_PROGRESS")
        self._make_run(db, machine_id=m1.id, task_id=task.id, order_id=order.id,
                       status="RUNNING", quantity_target=100, quantity_completed=40)
        res = self._simulate(db, f"What if {code} goes for maintenance for 1 day?")
        self.assertEqual(res.scenario.type, "MACHINE_UNAVAILABLE")
        self.assertEqual(res.impact.affected_production_runs, 1)
        self.assertEqual(res.impact.affected_tasks, 1)
        self.assertEqual(res.impact.affected_orders, 1)
        self.assertEqual(res.impact.estimated_units_at_risk, 60)
        self.assertIn(m2.name, [a.name for a in res.alternatives])
        self.assertIn("0 hours", res.recommendation)

    # ---- read-only: DB identical before/after ----

    def test_simulation_mutates_nothing(self):
        from backend.models.models import Employee, Machine, Order, ProductionRun, Task
        db = self._db(self.fid_a)
        emp = self._make_employee(db, _tag("Ravi"), skills=["welding"])
        alt = self._make_employee(db, _tag("Arun"), skills=["welding"])
        mac = self._make_machine(db, _tag("CNCW"), code=f"MC-{uuid4().int % 900 + 100}")
        order = self._make_order(db, _tag("ORDW"), status="IN_PROGRESS")
        task = self._make_task(db, _tag("TSKW"), employee_id=emp.id, order_id=order.id,
                               required_skill="welding", status="IN_PROGRESS", progress=0.25)
        run = self._make_run(db, machine_id=mac.id, task_id=task.id, order_id=order.id,
                             status="RUNNING", quantity_target=100, quantity_completed=10)

        def snapshot():
            s = self.SessionLocal()
            try:
                e = s.query(Employee).filter(Employee.id == emp.id).one()
                m = s.query(Machine).filter(Machine.id == mac.id).one()
                t = s.query(Task).filter(Task.id == task.id).one()
                o = s.query(Order).filter(Order.id == order.id).one()
                r = s.query(ProductionRun).filter(ProductionRun.id == run.id).one()
                return {
                    "emp": (e.status, e.availability),
                    "mac": (m.status, m.health_status),
                    "task": (t.status, t.progress, t.employee_id),
                    "order": (o.status,),
                    "run": (r.status, r.quantity_target, r.quantity_completed),
                    "counts": (s.query(Employee).count(), s.query(Machine).count(),
                               s.query(Task).count(), s.query(Order).count(),
                               s.query(ProductionRun).count()),
                    "alt": s.query(Employee).filter(Employee.id == alt.id).one().availability,
                }
            finally:
                s.close()

        before = snapshot()
        self._simulate(db, f"What if {emp.name} takes leave for 2 days?")
        self._simulate(db, f"What if {mac.machine_code} is down for 4 hours?")
        after = snapshot()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
