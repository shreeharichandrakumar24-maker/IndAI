"""Focused tests: Excel/CSV import (parse, mapping, validate, limits, confirm).

Pure tests run anywhere. DB tests use the live dev DB with uniquely-marked
temp rows and clean up after themselves.

Run: py -3 -m unittest backend.tests.test_imports -v
"""
import io
import unittest
from uuid import uuid4

from backend.services import importer as imp


def _xlsx_bytes(header, data_rows):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for r in data_rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestParse(unittest.TestCase):
    def test_csv_basic_and_empty_cells(self):
        h, rows = imp.parse_file("a.csv", b"Name,Qty\nMixer,5\nPump,\n")
        self.assertEqual(h, ["Name", "Qty"])
        self.assertEqual(rows[0], {"Name": "Mixer", "Qty": "5"})
        self.assertIsNone(rows[1]["Qty"])

    def test_csv_skips_empty_rows(self):
        h, rows = imp.parse_file("a.csv", b"a,b\n1,2\n,\n3,4\n")
        self.assertEqual(len(rows), 2)

    def test_csv_semicolon(self):
        h, rows = imp.parse_file("a.csv", "Nom;Qté\nMélangeur;5\n".encode("utf-8"))
        self.assertEqual(h, ["Nom", "Qté"])
        self.assertEqual(rows[0]["Qté"], "5")

    def test_csv_bad_encoding(self):
        with self.assertRaises(ValueError):
            imp.parse_file("a.csv", b"\xff\xfe\x00bad")

    def test_bad_extension(self):
        with self.assertRaises(ValueError):
            imp.parse_file("a.txt", b"x,y\n1,2\n")

    def test_too_big(self):
        with self.assertRaises(ValueError) as cm:
            imp.parse_file("big.csv", b"x" * (imp.MAX_BYTES + 1))
        self.assertIn("5 MB", str(cm.exception))

    def test_too_many_rows(self):
        body = "a\n" + "1\n" * (imp.MAX_ROWS + 1)
        with self.assertRaises(ValueError) as cm:
            imp.parse_file("big.csv", body.encode())
        self.assertIn("20,000", str(cm.exception))

    def test_xlsx_messy_headers(self):
        h, rows = imp.parse_file("t.xlsx", _xlsx_bytes(
            ["Mach No", "Temp(C)", "Vib", "Amp", "Speed", "State", "Time"],
            [["M-001", 68.5, 2.1, 8.2, 1450, "RUNNING", "2026-09-01T08:00:00"], [None] * 7]))
        self.assertEqual(h[0], "Mach No")
        self.assertEqual(len(rows), 1)  # empty row skipped
        self.assertEqual(rows[0]["Mach No"], "M-001")

    def test_xlsx_dup_headers_deduped(self):
        h, rows = imp.parse_file("t.xlsx", _xlsx_bytes(["Name", "Name"], [["a", "b"]]))
        self.assertEqual(h, ["Name", "Name_2"])
        self.assertEqual(rows[0]["Name_2"], "b")

    def test_xlsx_empty_sheet(self):
        import openpyxl
        wb = openpyxl.Workbook()
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        # brand-new sheet has no rows at all -> user-friendly error
        with self.assertRaises(ValueError):
            imp.parse_file("e.xlsx", buf.getvalue())
        # header-only sheet -> headers returned, zero data rows
        h, rows = imp.parse_file("h.xlsx", _xlsx_bytes(["Name", "Qty"], []))
        self.assertEqual(h, ["Name", "Qty"])
        self.assertEqual(rows, [])

    def test_formula_never_executed(self):
        h, rows = imp.parse_file("f.xlsx", _xlsx_bytes(["Name"], [["=1+1"]]))
        # data_only=True: no cached value -> None -> row skipped. Never evaluated.
        self.assertEqual(rows, [])


class TestMapping(unittest.TestCase):
    def test_employees_sample_headers(self):
        m, _ = imp.rule_based_mapping(
            "employees", ["Full Name", "Job Title", "Shift", "Competencies", "Cert"])
        self.assertEqual(m["Full Name"], "name")
        self.assertEqual(m["Job Title"], "role")
        self.assertEqual(m["Competencies"], "skills")
        self.assertEqual(m["Cert"], "certifications")

    def test_employee_code_aliases(self):
        for header in ["Emp ID", "employee_id", "EMP_CODE", "Employee Code", "Department", "Dept",
                       "Experience", "experience_years", "Designation"]:
            m, _ = imp.rule_based_mapping("employees", [header])
            self.assertIsNotNone(m[header], header)

    def test_orders_sample_headers(self):
        m, _ = imp.rule_based_mapping(
            "orders", ["Order #", "Client", "Item", "Qty", "Prio", "Due", "Progress", "State"])
        self.assertEqual(m, {"Order #": "order_number", "Client": "customer_name",
                            "Item": "product", "Qty": "quantity", "Prio": "priority",
                            "Due": "deadline", "Progress": "progress", "State": "status"})

    def test_telemetry_sample_headers(self):
        m, _ = imp.rule_based_mapping(
            "telemetry", ["Mach No", "Temp(C)", "Vib", "Amp", "Speed", "State", "Time"])
        self.assertEqual(m["Mach No"], "machine_code")
        self.assertEqual(m["Temp(C)"], "temperature")
        self.assertEqual(m["Time"], "timestamp")

    def test_machines_aliases(self):
        m, _ = imp.rule_based_mapping(
            "machines", ["Machine Name", "Asset ID", "Type", "Dept", "Criticality"])
        self.assertEqual(m["Asset ID"], "machine_code")
        self.assertEqual(m["Dept"], "department")
        self.assertEqual(m["Criticality"], "criticality")

    def test_ambiguous_second_header_unmapped_with_warning(self):
        headers = ["Order #", "Order No"]
        m, c = imp.rule_based_mapping("orders", headers)
        self.assertEqual(m["Order #"], "order_number")
        self.assertIsNone(m["Order No"])
        details, warnings = imp.describe_mapping("orders", headers, m, c, "rule-based")
        self.assertTrue(any("Ambiguous" in w for w in warnings))
        by_col = {d["source_column"]: d for d in details}
        self.assertEqual(by_col["Order #"]["confidence"], 1.0)
        self.assertIn("reason", by_col["Order #"])

    def test_unmapped_reported(self):
        headers = ["Order #", "Mystery Column"]
        m, c = imp.rule_based_mapping("orders", headers)
        details, warnings = imp.describe_mapping("orders", headers, m, c, "rule-based")
        unmapped = [h for h in headers if not m.get(h)]
        self.assertEqual(unmapped, ["Mystery Column"])
        self.assertTrue(any("Mystery Column" in w for w in warnings))

    def test_factory_id_never_mappable(self):
        self.assertNotIn("factory_id", imp.TARGET_FIELDS["orders"])
        self.assertNotIn("factory_id", imp.TARGET_FIELDS["employees"])


class TestRowValidation(unittest.TestCase):
    def test_order_ok_and_strict_numbers(self):
        kw, err, _ = imp.build_import_row(
            "orders", {"order_number": "ORD-1", "quantity": "10", "progress": "0.5"})
        self.assertIsNone(err)
        self.assertEqual(kw["quantity"], 10)
        kw, err, _ = imp.build_import_row("orders", {"order_number": "  ", "quantity": "1"})
        self.assertIn("order_number", err)
        _, err, _ = imp.build_import_row("orders", {"order_number": "O", "quantity": "abc"})
        self.assertIn("quantity", err)
        _, err, _ = imp.build_import_row(
            "orders", {"order_number": "O", "deadline": "not_a_date"})
        self.assertIn("deadline", err)

    def test_employee_requires_name_role(self):
        _, err, _ = imp.build_import_row("employees", {"name": "", "role": "R"})
        self.assertIn("name", err)
        _, err, _ = imp.build_import_row("employees", {"name": "N", "role": ""})
        self.assertIn("role", err)

    def test_machine_requires_name(self):
        _, err, _ = imp.build_import_row("machines", {"name": "  "})
        self.assertIn("name", err)

    def test_telemetry_bad_number(self):
        _, err, _ = imp.build_import_row(
            "telemetry", {"machine_id": str(uuid4()), "temperature": "hot"})
        self.assertIn("temperature", err)

    def test_extras_passthrough(self):
        kw, err, w = imp.build_import_row(
            "employees", {"name": "A", "role": "R", "employee_code": " E-1 ",
                          "department": " Mech ", "experience_years": "4"})
        self.assertIsNone(err)
        self.assertEqual(kw["employee_code"], "E-1")
        self.assertEqual(kw["department"], "Mech")
        self.assertEqual(kw["experience_years"], 4)
        kw, err, w = imp.build_import_row(
            "machines", {"name": "M-1 Lathe", "machine_code": "m-001", "criticality": "high"})
        self.assertIsNone(err)
        self.assertEqual(kw["machine_code"], "M-001")


class TestImportLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.db.database import SessionLocal
        cls.SessionLocal = SessionLocal
        cls.fid_a = uuid4()
        cls.fid_b = uuid4()
        cls.markers = []

    def _db(self, fid=None, include_null=False):
        from backend.db.scoping import set_factory_scope
        db = self.SessionLocal()
        self.addCleanup(db.close)
        if fid is not None:
            set_factory_scope(db, fid, include_null)
        return db

    def _confirm(self, db, target, rows, mapping):
        out = imp.run_import_confirm(db, target, rows, mapping)
        # track created order numbers for cleanup
        return out

    def _cleanup_markers(self, db):
        from backend.models.models import Employee, Machine, Order
        for model, field, values in self.markers:
            if values:
                db.query(model).filter(field.in_(values)).delete(synchronize_session=False)
        db.commit()
        self.markers = []

    def test_no_factory_rejected(self):
        from fastapi import HTTPException
        db = self._db()
        with self.assertRaises(HTTPException) as cm:
            imp.run_import_confirm(db, "orders",
                                   [{"order_number": "TIMP-NF-1"}],
                                   {"order_number": "order_number"})
        self.assertEqual(cm.exception.status_code, 400)
        with self.assertRaises(HTTPException):
            imp.run_import_preview(db, "orders", [], {})

    def test_confirm_writes_stamped_to_factory(self):
        from backend.models.models import Order
        num = f"TIMP-A-{uuid4().hex[:6]}"
        db = self._db(self.fid_a)
        out = self._confirm(db, "orders", [{"order_number": num, "quantity": "3"}],
                            {"order_number": "order_number", "quantity": "quantity"})
        self.assertEqual(out["inserted"], 1, out)
        row = db.query(Order).filter(Order.order_number == num).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.factory_id, self.fid_a)
        self.markers.append((Order, Order.order_number, [num]))
        self._cleanup_markers(self._db(self.fid_a))

    def test_failed_confirm_writes_nothing(self):
        from backend.models.models import Order
        num = f"TIMP-F-{uuid4().hex[:6]}"
        db = self._db(self.fid_a)
        rows = [{"order_number": num, "quantity": "bogus-qty"},
                {"order_number": "", "quantity": "1"}]
        out = self._confirm(db, "orders", rows,
                            {"order_number": "order_number", "quantity": "quantity"})
        self.assertEqual(out["inserted"], 0)
        self.assertEqual(out["failed"], 2)
        self.assertEqual(db.query(Order).filter(Order.order_number == num).count(), 0)

    def test_duplicates_skipped_in_file_and_on_reimport(self):
        from backend.models.models import Order
        num = f"TIMP-D-{uuid4().hex[:6]}"
        mapping = {"order_number": "order_number"}
        db = self._db(self.fid_a)
        out = self._confirm(db, "orders",
                            [{"order_number": num}, {"order_number": num}], mapping)
        self.assertEqual((out["inserted"], out["skipped_duplicates"]), (1, 1), out)
        out2 = self._confirm(db, "orders", [{"order_number": num}], mapping)
        self.assertEqual((out2["inserted"], out2["skipped_duplicates"]), (0, 1), out2)
        self.markers.append((Order, Order.order_number, [num]))
        self._cleanup_markers(self._db(self.fid_a))

    def test_factory_isolation(self):
        from backend.models.models import Order
        num = f"TIMP-I-{uuid4().hex[:6]}"
        mapping = {"order_number": "order_number"}
        out_a = self._confirm(self._db(self.fid_a), "orders", [{"order_number": num}], mapping)
        self.assertEqual(out_a["inserted"], 1, out_a)
        # Company B cannot see A's number: its duplicate check passes, and its
        # row is stamped to B.
        out_b = self._confirm(self._db(self.fid_b), "orders", [{"order_number": num}], mapping)
        self.assertEqual(out_b["inserted"], 1, out_b)
        self.assertEqual(out_b["skipped_duplicates"], 0)
        db_b = self._db(self.fid_b)
        self.assertEqual(db_b.query(Order).filter(Order.order_number == num).count(), 1)
        db_a = self._db(self.fid_a)
        self.assertEqual(db_a.query(Order).filter(Order.order_number == num).count(), 1)
        self.markers.append((Order, Order.order_number, [num]))
        # cleanup must remove both factory rows: unscoped delete by number
        raw = self.SessionLocal()
        try:
            raw.query(Order).filter(Order.order_number == num).delete(synchronize_session=False)
            raw.commit()
        finally:
            raw.close()
        self.markers = []

    def test_preview_writes_nothing(self):
        from backend.models.models import Order
        num = f"TIMP-P-{uuid4().hex[:6]}"
        db = self._db(self.fid_a)
        before = db.query(Order).filter(Order.order_number == num).count()
        out = imp.run_import_preview(db, "orders", [{"order_number": num}],
                                     {"order_number": "order_number"})
        self.assertEqual(out["valid_count"], 1)
        self.assertEqual(db.query(Order).filter(Order.order_number == num).count(), before)
        self.assertIn("valid_rows", out)
        self.assertIn("invalid_rows", out)
        self.assertIn("duplicate_rows", out)

    def test_employee_code_dedup(self):
        from backend.models.models import Employee
        code = f"TMP-{uuid4().hex[:6]}"
        mapping = {"name": "name", "role": "role", "employee_code": "employee_code"}
        db = self._db(self.fid_a)
        rows = [{"name": "Test Worker", "role": "Tester", "employee_code": code}]
        out = self._confirm(db, "employees", rows, mapping)
        self.assertEqual(out["inserted"], 1, out)
        out2 = self._confirm(db, "employees",
                             [{"name": "Someone Else", "role": "Other", "employee_code": code}],
                             mapping)
        self.assertEqual(out2["skipped_duplicates"], 1, out2)
        self.markers.append((Employee, Employee.employee_code, [code]))
        self._cleanup_markers(self._db(self.fid_a))


if __name__ == "__main__":
    unittest.main(verbosity=2)
