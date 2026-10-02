"""Hard-coded CNC / Mechanical preset (Phase A5).

Demo-safe default and deterministic fallback when the LLM fails.
Mirrors the canonical 8 machines (M-001..M-008) the simulator seeds and
the current thresholds from abnormality.py.
"""
from backend.schemas.profile import FactoryProfileData

CNC_PRESET: dict = {
    "industry": "CNC / Mechanical",
    "description": "Mechanical job shop: CNC milling/turning, press, grinding, welding, robot assembly, laser, molding.",
    "terminology": {"machine": "machine", "order": "order", "task": "task"},
    "machines": [
        {"code": "M-001", "name": "M-001 CNC Milling Machine", "machine_type": "CNC", "location": "Bay A - North", "sensors": ["temperature", "vibration", "current", "rpm"]},
        {"code": "M-002", "name": "M-002 CNC Turning Machine", "machine_type": "CNC", "location": "Bay A - South", "sensors": ["temperature", "vibration", "current", "rpm"]},
        {"code": "M-003", "name": "M-003 Hydraulic Press", "machine_type": "Press", "location": "Bay B - Center", "sensors": ["temperature", "vibration", "current"]},
        {"code": "M-004", "name": "M-004 Surface Grinder", "machine_type": "Grinder", "location": "Bay B - East", "sensors": ["temperature", "vibration", "current", "rpm"]},
        {"code": "M-005", "name": "M-005 Welding Station", "machine_type": "Welder", "location": "Bay C - West", "sensors": ["temperature", "vibration", "current"]},
        {"code": "M-006", "name": "M-006 Assembly Robot", "machine_type": "Robot", "location": "Bay C - Center", "sensors": ["temperature", "vibration", "current", "rpm"]},
        {"code": "M-007", "name": "M-007 Laser Cutter", "machine_type": "Laser", "location": "Bay D - North", "sensors": ["temperature", "vibration", "current"]},
        {"code": "M-008", "name": "M-008 Injection Molding Machine", "machine_type": "Molder", "location": "Bay D - South", "sensors": ["temperature", "vibration", "current", "rpm"]},
    ],
    "thresholds": {
        "CNC": {"temp_max": 85.0, "vibration_max": 5.0, "current_max": 10.0, "rpm_min": 1300.0},
        "Press": {"temp_max": 85.0, "vibration_max": 5.0, "current_max": 10.0, "rpm_min": 1300.0},
        "Grinder": {"temp_max": 85.0, "vibration_max": 5.0, "current_max": 10.0, "rpm_min": 1300.0},
        "Welder": {"temp_max": 85.0, "vibration_max": 5.0, "current_max": 10.0, "rpm_min": 1300.0},
        "Robot": {"temp_max": 85.0, "vibration_max": 5.0, "current_max": 10.0, "rpm_min": 1300.0},
        "Laser": {"temp_max": 85.0, "vibration_max": 5.0, "current_max": 10.0, "rpm_min": 1300.0},
        "Molder": {"temp_max": 85.0, "vibration_max": 5.0, "current_max": 10.0, "rpm_min": 1300.0},
        "_default": {"temp_max": 85.0, "vibration_max": 5.0, "current_max": 10.0, "rpm_min": 1300.0},
    },
    "task_templates": [
        {"name": "CNC milling setup + run", "description": "Fixture setup, tool check, first-article inspection, production run.", "required_skill": "CNC operation", "machine_type": "CNC", "typical_order": "Milled brackets / housings"},
        {"name": "CNC turning run", "description": "Chuck setup, program load, dimensional checks during run.", "required_skill": "CNC operation", "machine_type": "CNC", "typical_order": "Shafts / bushings"},
        {"name": "Press forming batch", "description": "Die setup, press cycle, visual + gauge inspection.", "required_skill": "Press operation", "machine_type": "Press", "typical_order": "Stamped brackets"},
        {"name": "Surface grinding finish", "description": "Grind to tolerance, surface finish check.", "required_skill": "Grinding", "machine_type": "Grinder", "typical_order": "Precision plates"},
        {"name": "Welding job", "description": "Fit-up, weld, visual inspection.", "required_skill": "Welding", "machine_type": "Welder", "typical_order": "Welded frames"},
        {"name": "Robot-assisted assembly", "description": "Load parts, supervise robot cycle, functional check.", "required_skill": "Assembly", "machine_type": "Robot", "typical_order": "Sub-assemblies"},
        {"name": "Laser cutting job", "description": "Nest program, cut, deburr and inspect.", "required_skill": "Laser operation", "machine_type": "Laser", "typical_order": "Sheet-metal panels"},
        {"name": "Molding run + QC", "description": "Mold setup, run, dimensional sampling.", "required_skill": "Molding", "machine_type": "Molder", "typical_order": "Plastic covers"},
        {"name": "Preventive maintenance check", "description": "Lubrication, coolant, vibration spot-check.", "required_skill": "Maintenance", "machine_type": "CNC", "typical_order": "N/A"},
    ],
    "skills": ["CNC operation", "Press operation", "Grinding", "Welding", "Assembly", "Laser operation", "Molding", "Quality inspection", "Maintenance"],
    "certifications": ["Forklift", "Welding cert", "ISO 9001 awareness"],
    "shifts": ["Morning (6-14)", "Evening (14-22)"],
    "main_problems": ["Machine breakdowns", "Order delays"],
    "layout": {
        "width": 1000,
        "height": 600,
        "zones": [
            {"id": "machining", "name": "Machining Bay", "x": 20, "y": 20, "w": 300, "h": 560},
            {"id": "press", "name": "Press & Fabrication", "x": 340, "y": 20, "w": 300, "h": 560},
            {"id": "assembly", "name": "Assembly & Molding", "x": 660, "y": 20, "w": 320, "h": 560},
        ],
        "machines": {
            "M-001": {"x": 80, "y": 120, "zone_id": "machining"},
            "M-002": {"x": 80, "y": 300, "zone_id": "machining"},
            "M-004": {"x": 80, "y": 480, "zone_id": "machining"},
            "M-003": {"x": 400, "y": 120, "zone_id": "press"},
            "M-005": {"x": 400, "y": 300, "zone_id": "press"},
            "M-007": {"x": 400, "y": 480, "zone_id": "press"},
            "M-006": {"x": 720, "y": 200, "zone_id": "assembly"},
            "M-008": {"x": 720, "y": 420, "zone_id": "assembly"},
        },
    },
}


def get_preset() -> FactoryProfileData:
    return FactoryProfileData.model_validate(CNC_PRESET).sanitized()
