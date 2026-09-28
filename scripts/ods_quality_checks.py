# ============================================================================
# ODS quality checks shared by both validation paths
# ============================================================================
# Single source of truth for the diagnosis-family and simulated-stay checks.
#   - scripts/validate_fabric_data.py imports this module directly.
#   - scripts/build_validation_notebook.py embeds this file verbatim into the
#     Fabric validation notebook, which must stay self-contained.
# Keep this file dependency-free (standard library only) so it can be inlined.
#
# Every check's SQL returns a single violation count; 0 means PASS.
# A check whose required tables are absent reports SKIP (never PASS), and a
# query that cannot run reports FAIL rather than being silently ignored.

QUALITY_CHECKS = [
    # --- Diagnosis families (icd_reference) ---------------------------------
    {
        'name': 'Every diagnosis code resolves in icd_reference',
        'requires': ('diagnoses', 'icd_reference'),
        'sql': 'SELECT COUNT(*) FROM dbo.diagnoses d '
               'WHERE NOT EXISTS (SELECT 1 FROM dbo.icd_reference r WHERE r.icd_code = d.icd_code)',
    },
    {
        'name': 'Diagnosis descriptions match icd_reference',
        'requires': ('diagnoses', 'icd_reference'),
        'sql': 'SELECT COUNT(*) FROM dbo.diagnoses d '
               'JOIN dbo.icd_reference r ON r.icd_code = d.icd_code '
               'WHERE d.description IS NULL OR d.description <> r.description',
    },
    {
        'name': 'icd_reference rows are complete and unique',
        'requires': ('icd_reference',),
        'sql': 'SELECT (SELECT COUNT(*) FROM dbo.icd_reference '
               '        WHERE description IS NULL OR clinical_family IS NULL '
               '           OR icd_chapter IS NULL OR chapter_code_range IS NULL) '
               '     + (SELECT COUNT(*) - COUNT(DISTINCT icd_code) FROM dbo.icd_reference)',
    },
    # --- Simulated stays: length-of-stay plan --------------------------------
    # Episodes created before the length-of-stay model carry no plan
    # (target_los_hours IS NULL) and are intentionally excluded.
    {
        'name': 'Planned stay has a complete, self-consistent LOS plan',
        'requires': ('ops_simulated_episode',),
        'sql': 'SELECT COUNT(*) FROM dbo.ops_simulated_episode se '
               'WHERE se.target_los_hours IS NOT NULL AND ('
               '  se.icd_family IS NULL OR se.target_los_hours <= 0 '
               '  OR se.ed_dwell_hours IS NULL OR se.ed_dwell_hours <= 0 '
               '  OR se.icu_expected_flag IS NULL OR se.expected_discharge_datetime IS NULL '
               '  OR ABS(DATEDIFF(SECOND, DATEADD(SECOND, CAST(se.target_los_hours * 3600 AS INT), '
               '         se.created_datetime), se.expected_discharge_datetime)) > 60)',
    },
    {
        'name': 'Planned stay family matches one of its diagnoses',
        'requires': ('ops_simulated_episode', 'diagnoses', 'icd_reference'),
        'sql': 'SELECT COUNT(*) FROM dbo.ops_simulated_episode se '
               'WHERE se.icd_family IS NOT NULL AND NOT EXISTS ('
               '  SELECT 1 FROM dbo.diagnoses d JOIN dbo.icd_reference r ON r.icd_code = d.icd_code '
               '  WHERE d.encounter_id = se.encounter_id AND d.patient_id = se.patient_id '
               '    AND r.clinical_family = se.icd_family)',
    },
    {
        'name': 'No planned stay is clinically discharged before its planned release',
        'requires': ('ops_simulated_episode', 'admissions'),
        'sql': 'SELECT COUNT(*) FROM dbo.ops_simulated_episode se '
               'JOIN dbo.admissions a ON a.admission_id = se.admission_id '
               'WHERE se.expected_discharge_datetime IS NOT NULL AND a.discharge_datetime IS NOT NULL '
               '  AND a.discharge_datetime < DATEADD(MINUTE, -1, se.expected_discharge_datetime)',
    },
    {
        'name': 'Occupied bed carries its stay plan (survives transfers)',
        'requires': ('ops_simulated_episode', 'ops_bed_state'),
        'sql': 'SELECT COUNT(*) FROM dbo.ops_bed_state bs '
               'JOIN dbo.ops_simulated_episode se ON se.encounter_id = bs.encounter_id '
               "WHERE bs.occupancy_status = 'Occupied' AND se.expected_discharge_datetime IS NOT NULL "
               '  AND (bs.expected_release_datetime IS NULL OR ABS(DATEDIFF(SECOND, '
               '       bs.expected_release_datetime, se.expected_discharge_datetime)) > 1)',
    },
    {
        'name': 'ICU transfers only occur for ICU-flagged planned stays',
        'requires': ('ops_simulated_episode', 'ops_patient_movement'),
        'sql': 'SELECT COUNT(*) FROM dbo.ops_patient_movement pm '
               'JOIN dbo.ops_simulated_episode se ON se.encounter_id = pm.encounter_id '
               "WHERE pm.movement_type = 'ICU Transfer' AND se.target_los_hours IS NOT NULL "
               '  AND se.icu_expected_flag = 0',
    },
]

# Informational summaries: printed for review, never PASS/FAIL. Distribution
# targets are statistical and too noisy to gate on small simulated cohorts.
QUALITY_SUMMARIES = [
    {
        'name': 'Simulated length of stay by clinical family',
        'requires': ('ops_simulated_episode',),
        'sql': 'SELECT icd_family, COUNT(*) AS stays, '
               '  CAST(AVG(target_los_hours) / 24 AS DECIMAL(6,2)) AS mean_los_days, '
               '  CAST(AVG(ed_dwell_hours) AS DECIMAL(6,2)) AS mean_ed_dwell_hours, '
               '  CAST(100.0 * AVG(CAST(icu_expected_flag AS FLOAT)) AS DECIMAL(5,1)) AS icu_pct '
               'FROM dbo.ops_simulated_episode WHERE target_los_hours IS NOT NULL '
               'GROUP BY icd_family ORDER BY stays DESC',
    },
    {
        'name': 'Simulated ICU share (published benchmark ~18% of admissions)',
        'requires': ('ops_simulated_episode',),
        'sql': 'SELECT COUNT(*) AS planned_stays, '
               '  CAST(100.0 * AVG(CAST(icu_expected_flag AS FLOAT)) AS DECIMAL(5,1)) AS icu_pct '
               'FROM dbo.ops_simulated_episode WHERE target_los_hours IS NOT NULL',
    },
    {
        'name': 'Diagnoses by clinical family',
        'requires': ('diagnoses', 'icd_reference'),
        'sql': 'SELECT r.clinical_family, COUNT(*) AS diagnoses '
               'FROM dbo.diagnoses d JOIN dbo.icd_reference r ON r.icd_code = d.icd_code '
               'GROUP BY r.clinical_family ORDER BY diagnoses DESC',
    },
]


def run_quality_checks(fetch_rows, existing_tables):
    # fetch_rows(sql) -> list of row tuples; existing_tables: set of table names.
    # Returns a list of (name, status, detail) with status PASS / FAIL / SKIP.
    results = []
    for check in QUALITY_CHECKS:
        missing = [t for t in check['requires'] if t not in existing_tables]
        if missing:
            results.append((check['name'], 'SKIP', 'not deployed: ' + ', '.join(missing)))
            continue
        try:
            violations = int(fetch_rows(check['sql'])[0][0] or 0)
        except Exception as exc:  # noqa: BLE001 - a check that cannot run must fail loudly
            results.append((check['name'], 'FAIL', 'check could not run: ' + str(exc)[:200]))
            continue
        if violations:
            results.append((check['name'], 'FAIL', '{:,} violation(s)'.format(violations)))
        else:
            results.append((check['name'], 'PASS', '0 violations'))
    return results


def run_quality_summaries(fetch_table, existing_tables):
    # fetch_table(sql) -> (column_names, rows). Yields (name, columns, rows) or
    # (name, None, reason) when the summary cannot be produced.
    for summary in QUALITY_SUMMARIES:
        missing = [t for t in summary['requires'] if t not in existing_tables]
        if missing:
            yield summary['name'], None, 'not deployed: ' + ', '.join(missing)
            continue
        try:
            columns, rows = fetch_table(summary['sql'])
        except Exception as exc:  # noqa: BLE001 - informational only
            yield summary['name'], None, 'could not run: ' + str(exc)[:200]
            continue
        yield summary['name'], columns, rows


def format_table(columns, rows, indent='    '):
    text_rows = [[str(c) for c in columns]] + [['' if v is None else str(v) for v in r] for r in rows]
    widths = [max(len(r[i]) for r in text_rows) for i in range(len(columns))]
    lines = [indent + '  '.join(v.ljust(w) for v, w in zip(r, widths)) for r in text_rows]
    lines.insert(1, indent + '  '.join('-' * w for w in widths))
    return '\n'.join(lines)
