"""Demo worker-credentials file helper (testing only - never commit real ones).

Single place for the 6-column format:
  name | role | employee_code | email | username | password

merge_cred_file(rows) merges rows of
  (name, role, employee_code, email, username, password_or_blank)
with the existing file WITHOUT losing plaintext:
- the existing file is backed up to docs/demo_worker_credentials.txt.bak first;
- existing non-blank passwords are preserved (understood in both the old
  4-column `name | role | username | password` layout and the 6-column one);
- blank passwords in `rows` fall back to the preserved ones;
- nothing is ever printed (callers print counts only, never secrets).
"""
import pathlib

CRED_FILE = "docs/demo_worker_credentials.txt"
BACKUP_FILE = CRED_FILE + ".bak"
HEADER_1 = "IndAI demo worker credentials (testing only - never commit real ones)"
HEADER_2 = ("name | role | employee_code | email | username | "
            "password (blank = unchanged, use old password)")


def _parse_line(line: str):
    """Returns (username, password) or None. Tolerates 4-col and 6-col."""
    parts = [p.strip() for p in line.split("|")]
    if len(parts) >= 6:
        uname, pwd = parts[4], parts[5]
    elif len(parts) == 4:
        uname, pwd = parts[2], parts[3]
    else:
        return None
    if not uname or not pwd or "unchanged" in pwd.lower():
        return None
    return uname, pwd


def merge_cred_file(rows) -> dict:
    rows = list(rows)
    preserved = {}
    order = []
    cred_path = pathlib.Path(CRED_FILE)
    if cred_path.exists():
        for line in cred_path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_line(line)
            if parsed is None:
                continue
            uname, pwd = parsed
            if uname not in preserved:
                preserved[uname] = pwd
                order.append(uname)
        backup = pathlib.Path(BACKUP_FILE)
        backup.write_text(cred_path.read_text(encoding="utf-8"), encoding="utf-8")
    merged = []
    preserved_count = 0
    for name, role, code, email, uname, pwd in rows:
        final_pwd = pwd or preserved.get(uname, "")
        if not pwd and final_pwd:
            preserved_count += 1
        merged.append((name, role or "", code or "", email or "", uname, final_pwd))
        if uname not in order:
            order.append(uname)
    by_uname = {m[4]: m for m in merged}
    with open(CRED_FILE, "w", encoding="utf-8") as f:
        f.write(HEADER_1 + "\n")
        f.write(HEADER_2 + "\n")
        for uname in order:
            if uname in by_uname:
                f.write(" | ".join(by_uname.pop(uname)) + "\n")
        for m in merged:
            if m[4] in by_uname:
                f.write(" | ".join(m) + "\n")
                del by_uname[m[4]]
    return {"rows": len(merged), "preserved_passwords": preserved_count}
