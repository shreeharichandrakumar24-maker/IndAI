"""Threshold sanity: every canonical machine's NORMAL baseline stays clean
while its simulator "Set Abnormal" values trip the detector.

Run:  python -m backend.tests.test_thresholds
Stdlib unittest only (no pytest dependency). Uses the REAL
abnormality.evaluate_telemetry with the REAL preset thresholds.
"""
import unittest
from types import SimpleNamespace

from backend.services.abnormality import evaluate_telemetry
from backend.services.factory_preset import get_preset

# code, machine_type, baseline, abnormal (mirrors the IoT simulator config)
FLEET = [
    ("M-001", "CNC",
     {"temperature": 68, "vibration": 2.0, "current": 8.0, "rpm": 1450},
     {"temperature": 95, "vibration": 6.5, "current": 12.0, "rpm": 1200}),
    ("M-002", "CNC",
     {"temperature": 72, "vibration": 2.5, "current": 9.5, "rpm": 1200},
     {"temperature": 98, "vibration": 7.0, "current": 14.0, "rpm": 900}),
    ("M-003", "Press",
     {"temperature": 55, "vibration": 3.5, "current": 15.0, "rpm": 0},
     {"temperature": 80, "vibration": 8.0, "current": 22.0, "rpm": 0}),
    ("M-004", "Grinder",
     {"temperature": 60, "vibration": 4.0, "current": 7.5, "rpm": 3000},
     {"temperature": 88, "vibration": 9.5, "current": 11.0, "rpm": 2200}),
    ("M-005", "Welder",
     {"temperature": 75, "vibration": 1.2, "current": 18.0, "rpm": 0},
     {"temperature": 105, "vibration": 4.5, "current": 26.0, "rpm": 0}),
    ("M-006", "Robot",
     {"temperature": 48, "vibration": 1.8, "current": 5.5, "rpm": 900},
     {"temperature": 72, "vibration": 5.5, "current": 9.0, "rpm": 600}),
    ("M-007", "Laser",
     {"temperature": 62, "vibration": 1.0, "current": 11.0, "rpm": 0},
     {"temperature": 90, "vibration": 3.8, "current": 16.0, "rpm": 0}),
    ("M-008", "Molder",
     {"temperature": 85, "vibration": 2.8, "current": 13.5, "rpm": 750},
     {"temperature": 115, "vibration": 7.5, "current": 19.0, "rpm": 500}),
]


def thresholds_for(profile, machine_type):
    sets = profile.thresholds or {}
    cand = sets.get(machine_type) or sets.get("_default")
    return {"temp_max": cand.temp_max, "vibration_max": cand.vibration_max,
            "current_max": cand.current_max, "rpm_min": cand.rpm_min}


def row_of(values):
    return SimpleNamespace(temperature=values["temperature"], vibration=values["vibration"],
                           current=values["current"], rpm=values["rpm"],
                           machine_status="RUNNING")


class TestThresholdSanity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = get_preset()

    def test_baselines_clean(self):
        for code, mtype, base, _ in FLEET:
            with self.subTest(machine=code):
                out = evaluate_telemetry(row_of(base), thresholds_for(self.profile, mtype))
                self.assertFalse(out["abnormal"], f"{code} baseline flagged: {out['breaches']}")

    def test_abnormals_trip(self):
        for code, mtype, _, abn in FLEET:
            with self.subTest(machine=code):
                out = evaluate_telemetry(row_of(abn), thresholds_for(self.profile, mtype))
                self.assertTrue(out["abnormal"], f"{code} abnormal NOT flagged")
                self.assertIsNotNone(out["severity"])

    def test_reference_spike_trips_cnc(self):
        # temp 95, vibration 6.5, current 12, rpm 1200 must flag on a CNC machine
        out = evaluate_telemetry(
            row_of({"temperature": 95, "vibration": 6.5, "current": 12.0, "rpm": 1200}),
            thresholds_for(self.profile, "CNC"))
        self.assertTrue(out["abnormal"])
        fields = {b["field"] for b in out["breaches"]}
        self.assertTrue({"temperature", "vibration", "current"} <= fields)


if __name__ == "__main__":
    unittest.main(verbosity=2)
