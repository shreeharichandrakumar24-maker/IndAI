"""Unit tests: command_policy tiers/defaults + commands behavior.

Run: py -3 -m unittest backend.tests.test_commands -v
Uses the live dev DB with temp rows only; cleans up after itself.
"""
import unittest
from datetime import datetime, timedelta
from uuid import UUID

from backend.db.database import SessionLocal
from backend.models.models import AIRecommendation, Employee, FactoryMemory, Task
from backend.services import command_policy as pol
from backend.services import commands as svc


class TestPolicyPure(unittest.TestCase):
    def test_forbidden_delete(self):
        ok, reason = pol.is_forbidden("delete that task")
        self.assertTrue(ok)
        self.assertIn("Tasks", pol.refusal_for(reason))

    def test_forbidden_variants(self):
        for text, reason in [("remove the order", "delete"),
                             ("reset his password", "credentials"),
                             ("show me the token", "credentials"),
                             ("mark her on leave", "availability"),
                             ("change thresholds", "profile"),
                             ("factory profile settings", "profile")]:
            ok, got = pol.is_forbidden(text)
            self.assertTrue(ok, text)
            self.assertEqual(got, reason, text)

    def test_allowed_plain(self):
        for text in ["assign a CNC operation task to Ravi Kumar",
                     "create an order for 50 gear housings",
                     "mark the task completed",
                     "schedule maintenance for M-001"]:
            ok, _ = pol.is_forbidden(text)
            self.assertFalse(ok, text)

    def test_deadline_default_tomorrow_6pm(self):
        now = datetime(2026, 10, 5, 10, 0, tzinfo=pol.IST)  # a Monday
        dl = pol.parse_deadline("", now=now)
        self.assertEqual((dl.day, dl.hour, dl.minute), (6, 18, 0))

    def test_deadline_friday(self):
        now = datetime(2026, 10, 5, 10, 0, tzinfo=pol.IST)
        dl = pol.parse_deadline("by Friday", now=now)
        self.assertEqual(dl.weekday(), 4)
        self.assertEqual(dl.hour, 18)

    def test_deadline_in_days(self):
        now = datetime(2026, 10, 5, 10, 0, tzinfo=pol.IST)
        dl = pol.parse_deadline("in 3 days", now=now)
        self.assertEqual(dl.day, 8)

    def test_deadline_tonight(self):
        now = datetime(2026, 10, 5, 10, 0, tzinfo=pol.IST)
        dl = pol.parse_deadline("tonight", now=now)
        self.assertEqual((dl.day, dl.hour), (5, 21))

    def test_deadline_iso(self):
        dl = pol.parse_deadline("2026-10-20T00:00:00")
        self.assertEqual((dl.year, dl.month, dl.day), (2026, 10, 20))

    def test_speak_due(self):
        self.assertIn("tomorrow", pol.speak_due(
            datetime.now(pol.IST) + timedelta(days=1, hours=2)))

    def test_priority_words(self):
        self.assertEqual(pol.parse_priority("urgent welding task"), "URGENT")
        self.assertEqual(pol.parse_priority("high priority"), "HIGH")
        self.assertEqual(pol.parse_priority("low"), "LOW")
        self.assertEqual(pol.parse_priority("normal job"), "NORMAL")

    def test_task_name(self):
        self.assertEqual(pol.task_name_from("CNC operation task"), "CNC operation")
        self.assertEqual(pol.task_name_from("a welding job"), "welding")

    def test_skill_match(self):
        skills = ["CNC operation", "Welding", "Assembly"]
        self.assertEqual(pol.match_skill("do a cnc operation now", skills), "CNC operation")
        self.assertIsNone(pol.match_skill("paint the wall", skills))

    def test_order_numbers(self):
        self.assertEqual(pol.next_order_number([]), "ORD-001")
        self.assertEqual(pol.next_order_number(["ORD-001", "ORD-009"]), "ORD-010")


class TestTaskNameCleaning(unittest.TestCase):
    """Spoken command -> clean task name (no selection/person words)."""

    @staticmethod
    def _spans(emp=None, mac=None, order=None):
        from types import SimpleNamespace as NS
        d = {}
        if emp:
            d["employee"] = NS(name=emp)
        if mac:
            d["machine"] = NS(name=mac)
        if order:
            d["order"] = NS(order_number=order)
        return d

    def _name(self, text, emp=None, mac=None, order=None, skill=None):
        return svc._task_name_from_command(text, self._spans(emp, mac, order), skill)

    def test_required_examples(self):
        self.assertEqual(self._name(
            "assign the best welder to a new task called weld frame"), "weld frame")
        self.assertEqual(self._name(
            "assign any available CNC operator a task called roughing"), "roughing")
        self.assertEqual(self._name(
            "give Ravi Kumar a CNC operation task", emp="Ravi Kumar"), "CNC operation")
        self.assertEqual(self._name(
            "assign a welding task to EMP-004", skill="Welding"), "welding")
        self.assertEqual(self._name(
            "assign the best person to inspect the housings"), "inspect the housings")

    def test_more_examples(self):
        self.assertEqual(self._name(
            "create an urgent CNC milling task for M-004", mac="M-004 Surface Grinder"),
            "CNC milling")
        self.assertEqual(self._name(
            "assign a deburr task to Asha Menon tonight", emp="Asha Menon"), "deburr")
        self.assertEqual(self._name("make another laser cut job"), "laser cut")
        self.assertEqual(self._name(
            "add a quality inspection task for ORD-007", order="ORD-007"),
            "quality inspection")
        self.assertEqual(self._name(
            "assign the best available person to a task called press forming"),
            "press forming")

    def test_fallbacks_and_filler(self):
        self.assertEqual(self._name("assign anyone", skill="Welding"), "Welding")
        self.assertEqual(self._name("assign anyone"), "General task")
        self.assertEqual(self._name(
            "give the best welder a welding task", skill="Welding"), "welding")
        self.assertEqual(self._name(
            "assign a low priority deburr task by Friday"), "deburr")
        self.assertEqual(self._name(
            "please assign the best available person a task called weld frame"),
            "weld frame")

    def test_existing_phrasing_unchanged(self):
        self.assertEqual(self._name(
            "assign a TSTEST milling task to Ravi Kumar", emp="Ravi Kumar"),
            "TSTEST milling")
        self.assertEqual(self._name("CNC operation task"), "CNC operation")


class TestCommandsLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.temp_tasks = []
        cls.temp_orders = []
        cls.temp_mems = []

    @classmethod
    def tearDownClass(cls):
        from backend.models.models import Order as _O
        db = SessionLocal()
        try:
            for tid in cls.temp_tasks:
                t = db.query(Task).filter(Task.id == tid).first()
                if t is not None:
                    db.delete(t)
            for oid in cls.temp_orders:
                o = db.query(_O).filter(_O.id == oid).first()
                if o is not None:
                    db.delete(o)
            for mid in cls.temp_mems:
                m = db.query(FactoryMemory).filter(FactoryMemory.id == mid).first()
                if m is not None:
                    db.delete(m)
            db.commit()
        finally:
            db.close()
        cls.db.close()

    def _track(self, out):
        if out.get("command_id"):
            from uuid import UUID as _U
            self.temp_mems.append(_U(out["command_id"]))

    def test_create_assign_undo_flow(self):
        db = self.__class__.db
        out = svc.run_create_task(db, text="assign a TSTEST milling task to Ravi Kumar",
                                  source="test")
        self._track(out)
        self.assertTrue(out["undo_available"])
        self.assertIn("no order linked", out["warnings"])
        tid = out["command_id"] and db.query(FactoryMemory).filter(
            FactoryMemory.id == UUID(out["command_id"])).first().metadata_["created"]["task_id"]
        self.temp_tasks.append(UUID(tid))
        t = db.query(Task).filter(Task.id == UUID(tid)).first()
        self.assertEqual(t.status, "PENDING")
        self.assertIsNotNone(t.employee_id)
        # duplicate guard
        dup = svc.run_create_task(db, text="assign a TSTEST milling task to Ravi Kumar",
                                  source="test")
        self.assertFalse(dup["undo_available"])
        self.assertIn("reusing", dup["warnings"][0])
        # undo works
        u = svc.undo_command(db, out["command_id"])
        self.assertTrue(u["undone"])
        self.assertIsNone(db.query(Task).filter(Task.id == UUID(tid)).first())
        self.temp_tasks.remove(UUID(tid))
        # idempotent
        u2 = svc.undo_command(db, out["command_id"])
        self.assertTrue(u2["undone"])

    def test_undo_refused_after_start(self):
        db = self.__class__.db
        out = svc.run_create_task(db, text="TSTEST grind probe", source="test")
        self._track(out)
        tid = db.query(FactoryMemory).filter(
            FactoryMemory.id == UUID(out["command_id"])).first().metadata_["created"]["task_id"]
        self.temp_tasks.append(UUID(tid))
        t = db.query(Task).filter(Task.id == UUID(tid)).first()
        t.status = "IN_PROGRESS"
        db.commit()
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as cm:
            svc.undo_command(db, out["command_id"])
        self.assertEqual(cm.exception.status_code, 409)
        t.status = "PENDING"
        db.commit()

    def test_ask_mode_proposes(self):
        db = self.__class__.db
        res = svc.propose_instead(db, action_type="DRAFT_ASSIGNMENT",
                                  params={"task_name": "TSTEST ask probe"},
                                  reason="test")
        self._track({**res, "command_id": res["command_id"]})
        self.assertFalse(res["undo_available"])
        self.assertIsNotNone(res["proposal_id"])
        row = db.query(AIRecommendation).filter(
            AIRecommendation.id == UUID(res["proposal_id"])).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.status, "PENDING")
        db.delete(row)
        db.commit()
        mem = db.query(FactoryMemory).filter(
            FactoryMemory.id == UUID(res["command_id"])).first()
        db.delete(mem)
        db.commit()
        self.temp_mems.remove(UUID(res["command_id"]))

    def test_clean_name_dupe_and_undo_live(self):
        db = self.__class__.db
        phrase = "assign Ravi Kumar a task called TSTCLEAN inspect housings"
        out = svc.run_create_task(db, text=phrase, source="test")
        self._track(out)
        tid = UUID(db.query(FactoryMemory).filter(
            FactoryMemory.id == UUID(out["command_id"])).first()
            .metadata_["created"]["task_id"])
        self.temp_tasks.append(tid)
        t = db.query(Task).filter(Task.id == tid).first()
        self.assertEqual(t.name, "TSTCLEAN inspect housings")
        # duplicate guard still catches the same wording
        dup = svc.run_create_task(db, text=phrase, source="test")
        self.assertFalse(dup["undo_available"])
        self.assertIn("reusing", dup["warnings"][0])
        # undo still removes the created task
        u = svc.undo_command(db, out["command_id"])
        self.assertTrue(u["undone"])
        self.assertIsNone(db.query(Task).filter(Task.id == tid).first())
        self.temp_tasks.remove(tid)

    def test_autonomy_roundtrip(self):
        db = self.__class__.db
        self.assertEqual(svc.get_autonomy(db), "FAST")
        self.assertEqual(svc.set_autonomy(db, "ASK"), "ASK")
        self.assertEqual(svc.get_autonomy(db), "ASK")
        self.assertEqual(svc.set_autonomy(db, "FAST"), "FAST")


if __name__ == "__main__":
    unittest.main(verbosity=2)
