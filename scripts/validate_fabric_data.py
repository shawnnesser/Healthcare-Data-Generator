"""Comprehensive validation of the Fabric-hosted Healthcare ODS database after
the backfill run. Non-interactive (uses az CLI token + pyodbc, same pattern as
scripts/_verify_data.py) so it never hangs waiting for a browser login.
"""
import struct
import subprocess
import pyodbc

SERVER = "5mx5ymqwo74ezmng6awpg76wx4-f2smxdwfuzzenbkp2vylj5c5ca.database.fabric.microsoft.com"
DATABASE = "Healthcare ODS-63ba7f40-a784-49f0-ae76-387233bc2616"
SQL_COPT_SS_ACCESS_TOKEN = 1256


def get_token():
    ps_cmd = (
        '$token = (az account get-access-token --resource '
        '"https://database.windows.net/" | ConvertFrom-Json).accessToken; '
        'Write-Host $token'
    )
    result = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd],
                             capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


def token_struct(token):
    token_bytes = token.encode('utf-16-le')
    return struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)


def connect():
    token = get_token()
    conn_str = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server=tcp:{SERVER},1433;"
        f"Database={DATABASE};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct(token)})


def q(cur, sql, params=None):
    cur.execute(sql, params) if params else cur.execute(sql)
    cols = [c[0] for c in cur.description] if cur.description else []
    rows = cur.fetchall()
    return cols, rows


def section(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main():
    conn = connect()
    cur = conn.cursor()

    section("1. TABLE INVENTORY & ROW COUNTS")
    cols, rows = q(cur, """
        SELECT t.name AS table_name, p.rows AS row_count
        FROM sys.tables t
        JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0,1)
        ORDER BY t.name
    """)
    table_counts = {}
    for name, cnt in rows:
        table_counts[name] = cnt
        print(f"  {name:35s} {cnt:>10,}")

    section("2. ENCOUNTERS DATE RANGE & GAP CHECK")
    cols, rows = q(cur, "SELECT MIN(encounter_date), MAX(encounter_date), COUNT(DISTINCT CAST(encounter_date AS DATE)) FROM encounters")
    min_d, max_d, distinct_days = rows[0]
    print(f"  Min date: {min_d}   Max date: {max_d}   Distinct days: {distinct_days}")
    cols, rows = q(cur, """
        WITH RECURSIVE_CHECK AS (
            SELECT CAST(encounter_date AS DATE) AS d FROM encounters GROUP BY CAST(encounter_date AS DATE)
        )
        SELECT DATEDIFF(day, MIN(d), MAX(d)) + 1 AS calendar_days, COUNT(*) AS days_with_data FROM RECURSIVE_CHECK
    """)
    calendar_days, days_with_data = rows[0]
    missing = calendar_days - days_with_data
    print(f"  Calendar days in range: {calendar_days}   Days with data: {days_with_data}   Missing days: {missing}")

    section("3. DAILY VOLUME SANITY (last 10 days)")
    cols, rows = q(cur, """
        SELECT TOP 10 CAST(encounter_date AS DATE) AS d, COUNT(*) AS encounters
        FROM encounters GROUP BY CAST(encounter_date AS DATE) ORDER BY d DESC
    """)
    for d, cnt in rows:
        print(f"  {d}  {cnt:>7,} encounters")

    section("4. REFERENTIAL INTEGRITY (orphan checks)")
    checks = [
        ("diagnoses -> encounters", "SELECT COUNT(*) FROM diagnoses d LEFT JOIN encounters e ON d.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL"),
        ("procedures -> encounters", "SELECT COUNT(*) FROM procedures p LEFT JOIN encounters e ON p.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL"),
        ("medications -> encounters", "SELECT COUNT(*) FROM medications m LEFT JOIN encounters e ON m.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL"),
        ("labs -> encounters", "SELECT COUNT(*) FROM labs l LEFT JOIN encounters e ON l.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL"),
        ("encounters -> patients", "SELECT COUNT(*) FROM encounters e LEFT JOIN patients p ON e.patient_id = p.patient_id WHERE p.patient_id IS NULL"),
        ("billing -> encounters", "SELECT COUNT(*) FROM billing b LEFT JOIN encounters e ON b.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL"),
        ("admissions -> encounters", "SELECT COUNT(*) FROM admissions a LEFT JOIN encounters e ON a.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL"),
    ]
    for label, sql in checks:
        try:
            cols, rows = q(cur, sql)
            orphans = rows[0][0]
            status = "OK" if orphans == 0 else f"** {orphans} ORPHANS **"
            print(f"  {label:30s} {status}")
        except Exception as e:
            print(f"  {label:30s} skipped ({e})")

    section("5. DUPLICATE PRIMARY KEY CHECK")
    pk_checks = [
        ("patients", "patient_id"),
        ("doctors", "provider_id"),
        ("encounters", "encounter_id"),
        ("diagnoses", "diagnosis_id"),
        ("procedures", "procedure_id"),
        ("medications", "medication_id"),
        ("labs", "lab_id"),
        ("billing", "billing_id"),
        ("insurance", "insurance_id"),
        ("admissions", "admission_id"),
    ]
    for table, pk in pk_checks:
        if table not in table_counts:
            continue
        try:
            cols, rows = q(cur, f"SELECT COUNT(*) - COUNT(DISTINCT {pk}) FROM {table}")
            dupes = rows[0][0]
            status = "OK" if dupes == 0 else f"** {dupes} DUPLICATES **"
            print(f"  {table}.{pk:20s} {status}")
        except Exception as e:
            print(f"  {table}.{pk:20s} skipped ({e})")

    section("6. NULL CHECKS ON KEY COLUMNS")
    null_checks = [
        ("patients", "patient_id"),
        ("encounters", "patient_id"),
        ("encounters", "encounter_date"),
        ("encounters", "hospital_id"),
    ]
    for table, col in null_checks:
        if table not in table_counts:
            continue
        try:
            cols, rows = q(cur, f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")
            nulls = rows[0][0]
            status = "OK" if nulls == 0 else f"** {nulls} NULLS **"
            print(f"  {table}.{col:20s} {status}")
        except Exception as e:
            print(f"  {table}.{col:20s} skipped ({e})")

    section("7. REFERENCE DATA (hospitals / departments)")
    for t in ("hospitals", "departments", "date_dim"):
        if t in table_counts:
            print(f"  {t:20s} {table_counts[t]:>10,} rows")
        else:
            print(f"  {t:20s} ** MISSING **")

    section("8. PATIENT-LOCATION / VIEWS")
    for t in ("patient_bed_assignments", "hospital_department_beds"):
        if t in table_counts:
            print(f"  {t:30s} {table_counts[t]:>10,} rows")
        else:
            print(f"  {t:30s} ** MISSING **")

    for view in ("vw_current_er_beds", "vw_current_patient_beds", "vw_floor_plan", "vw_patient_location", "vw_floor_occupancy", "vw_hospital_status"):
        try:
            cols, rows = q(cur, f"SELECT COUNT(*) FROM {view}")
            print(f"  VIEW {view:25s} {rows[0][0]:>10,} rows")
        except Exception as e:
            print(f"  VIEW {view:25s} not queryable ({e})")

    section("9. BILLING ORPHAN DEEP-DIVE")
    try:
        cols, rows = q(cur, "SELECT COUNT(*), MIN(encounter_id), MAX(encounter_id) FROM billing")
        print(f"  billing total={rows[0][0]:,} encounter_id range=[{rows[0][1]}, {rows[0][2]}]")
        cols, rows = q(cur, "SELECT MIN(encounter_id), MAX(encounter_id) FROM encounters")
        print(f"  encounters encounter_id range=[{rows[0][0]}, {rows[0][1]}]")
        cols, rows = q(cur, """
            SELECT COUNT(*) FROM billing b
            WHERE NOT EXISTS (SELECT 1 FROM encounters e WHERE e.encounter_id = b.encounter_id)
            AND b.encounter_id IS NOT NULL
        """)
        print(f"  billing rows with non-null encounter_id but no matching encounter: {rows[0][0]:,}")
        cols, rows = q(cur, "SELECT COUNT(*) FROM billing WHERE encounter_id IS NULL")
        print(f"  billing rows with NULL encounter_id: {rows[0][0]:,}")
    except Exception as e:
        print(f"  deep-dive failed: {e}")

    section("SUMMARY")
    print(f"  Total tables: {len(table_counts)}")
    print(f"  Encounters date coverage: {min_d} -> {max_d} ({days_with_data}/{calendar_days} calendar days, {missing} missing)")

    conn.close()


if __name__ == '__main__':
    main()
