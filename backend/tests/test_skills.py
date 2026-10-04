"""Skill-format tolerance: old comma-string, new items-list, plain list.

Run:  python -m backend.tests.test_skills
Stdlib unittest only. Uses the REAL matcher.skills_of - the single parser
every allocation path (matcher, smart_split candidates, allocation) shares.
Employee rows are never modified by this test.
"""
import unittest
from types import SimpleNamespace

from backend.services.matcher import skills_of


def emp(skills):
    return SimpleNamespace(skills=skills)


class TestSkillFormats(unittest.TestCase):
    def test_old_comma_string(self):
        self.assertEqual(
            skills_of(emp({"skills": "CNC operation, Quality inspection"})),
            ["cnc operation", "quality inspection"])

    def test_new_items_list(self):
        self.assertEqual(
            skills_of(emp({"items": ["CNC operation", "Welding"]})),
            ["cnc operation", "welding"])

    def test_plain_list(self):
        self.assertEqual(skills_of(emp(["Grinding", "Assembly"])), ["grinding", "assembly"])

    def test_case_and_whitespace(self):
        self.assertEqual(
            skills_of(emp({"items": ["  CNC OPERATION ", "welding"]})),
            ["cnc operation", "welding"])

    def test_none_and_empty(self):
        self.assertEqual(skills_of(emp(None)), [])
        self.assertEqual(skills_of(emp({})), [])
        self.assertEqual(skills_of(emp({"items": []})), [])

    def test_value_shape(self):
        self.assertEqual(skills_of(emp({"value": "Molding"})), ["molding"])

    def test_match_substring_both_ways(self):
        have = skills_of(emp({"skills": "CNC operation, Quality inspection"}))
        need = "cnc operation"
        self.assertTrue(any(need in h or h in need for h in have))


if __name__ == "__main__":
    unittest.main(verbosity=2)
