-- ============================================================================
-- 006_create_snapshot_views.sql
-- Hospital Operations - application snapshot views for the future Fabric App
-- / Rayfin command-center UI. All views are prefixed vw_ops_ to avoid
-- colliding with the generator's own vw_floor_plan / vw_hospital_status /
-- etc. Every view is built ONLY from actual existing source tables and the
-- new ops_* tables (see docs/HOSPITAL_OPERATIONS_EXISTING_MODEL_ANALYSIS.md
-- section 8, source-to-target mapping). CREATE OR ALTER is used so this
-- script is idempotent/re-runnable, matching the generator's own convention.
-- Upper-level views (health-system/hospital/building/floor/unit) intentionally
-- expose ONLY counts/aggregates -- never patient names -- per the demo-safety
-- requirement ("avoid exposing unnecessary synthetic PII at upper navigation
-- levels").
-- ============================================================================

CREATE OR ALTER VIEW dbo.vw_ops_bed_snapshot AS
SELECT
    b.bed_id, b.room_id, b.hospital_id, b.floor_number, b.room_number, b.bed_position, b.bed_type,
    b.status AS generator_bed_status,
    ISNULL(bs.operational_status, 'Available') AS operational_status,
    ISNULL(bs.occupancy_status, 'Available') AS occupancy_status,
    bs.encounter_id, bs.patient_id, bs.admission_id,
    bs.assigned_datetime, bs.expected_release_datetime,
    ISNULL(bs.cleaning_required_flag, 0) AS cleaning_required_flag,
    u.unit_id, u.unit_name, u.clinical_specialty,
    bs.updated_datetime, bs.simulation_run_id
FROM dbo.beds b
LEFT JOIN dbo.ops_bed_state bs ON b.bed_id = bs.bed_id
LEFT JOIN dbo.ops_unit u ON u.hospital_id = b.hospital_id AND u.source_floor_number = b.floor_number;
GO

CREATE OR ALTER VIEW dbo.vw_ops_room_snapshot AS
SELECT
    r.room_id, r.hospital_id, r.floor_number, r.room_number, r.bed_count, r.room_type,
    ra.unit_id, ra.room_name, ra.floor_x, ra.floor_y, ra.width, ra.height,
    ISNULL(ra.isolation_capable_flag, 0) AS isolation_capable_flag,
    ISNULL(ra.negative_pressure_flag, 0) AS negative_pressure_flag,
    ISNULL(ra.telemetry_capable_flag, 0) AS telemetry_capable_flag,
    ISNULL(ra.private_room_flag, 0) AS private_room_flag,
    ISNULL(rs.operational_status, 'Available') AS operational_status,
    ISNULL(rs.isolation_status, 'None') AS isolation_status,
    ISNULL(rs.cleaning_status, 'Clean') AS cleaning_status,
    ISNULL(rs.maintenance_status, 'None') AS maintenance_status,
    ISNULL(rs.current_patient_count, 0) AS current_patient_count,
    ISNULL(rs.available_bed_count, r.bed_count) AS available_bed_count,
    rs.last_cleaned_datetime, rs.next_expected_available_datetime,
    (SELECT COUNT(*) FROM dbo.ops_operational_alert oa WHERE oa.room_id = r.room_id AND oa.status <> 'Resolved') AS active_alert_count,
    rs.updated_datetime, rs.simulation_run_id
FROM dbo.rooms r
LEFT JOIN dbo.ops_room_attribute ra ON r.room_id = ra.room_id
LEFT JOIN dbo.ops_room_state rs ON r.room_id = rs.room_id;
GO

CREATE OR ALTER VIEW dbo.vw_ops_unit_snapshot AS
SELECT
    u.unit_id, u.hospital_id, h.name AS hospital_name, u.building_id, ob.building_name,
    u.source_floor_number AS floor_number, u.unit_code, u.unit_name, u.unit_type, u.clinical_specialty,
    u.licensed_bed_count, u.staffed_bed_count,
    (SELECT COUNT(*) FROM dbo.beds b WHERE b.hospital_id = u.hospital_id AND b.floor_number = u.source_floor_number) AS total_beds,
    (SELECT COUNT(*) FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id
        WHERE b.hospital_id = u.hospital_id AND b.floor_number = u.source_floor_number AND bs.occupancy_status = 'Occupied') AS occupied_beds,
    (SELECT COUNT(*) FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id
        WHERE b.hospital_id = u.hospital_id AND b.floor_number = u.source_floor_number AND bs.occupancy_status = 'Available') AS available_beds,
    (SELECT COUNT(*) FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id
        WHERE b.hospital_id = u.hospital_id AND b.floor_number = u.source_floor_number AND bs.occupancy_status = 'Cleaning') AS cleaning_beds,
    (SELECT COUNT(*) FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id
        WHERE b.hospital_id = u.hospital_id AND b.floor_number = u.source_floor_number AND bs.occupancy_status = 'Blocked') AS blocked_beds,
    staff_charge.display_name AS charge_nurse_display_name,
    ss.required_rn_count, ss.present_rn_count, ss.staffing_coverage_pct, ss.staffing_status,
    (SELECT COUNT(*) FROM dbo.ops_equipment eq LEFT JOIN dbo.ops_equipment_state es ON eq.equipment_id = es.equipment_id
        WHERE eq.unit_id = u.unit_id AND ISNULL(es.availability_status, 'Available') <> 'Available') AS equipment_unavailable_count,
    (SELECT COUNT(*) FROM dbo.ops_operational_alert oa WHERE oa.unit_id = u.unit_id AND oa.status <> 'Resolved') AS active_alert_count,
    u.active_flag, SYSUTCDATETIME() AS last_refresh_datetime
FROM dbo.ops_unit u
JOIN dbo.hospitals h ON u.hospital_id = h.hospital_id
LEFT JOIN dbo.ops_building ob ON u.building_id = ob.building_id
LEFT JOIN dbo.ops_staffing_state ss ON u.unit_id = ss.unit_id
LEFT JOIN dbo.ops_staff staff_charge ON ss.charge_nurse_staff_id = staff_charge.staff_id;
GO

CREATE OR ALTER VIEW dbo.vw_ops_floor_snapshot AS
SELECT
    hospital_id, hospital_name, building_id, building_name, floor_number,
    COUNT(*) AS unit_count,
    SUM(total_beds) AS total_beds, SUM(occupied_beds) AS occupied_beds, SUM(available_beds) AS available_beds,
    SUM(active_alert_count) AS active_alert_count
FROM dbo.vw_ops_unit_snapshot
GROUP BY hospital_id, hospital_name, building_id, building_name, floor_number;
GO

CREATE OR ALTER VIEW dbo.vw_ops_building_snapshot AS
SELECT
    ob.building_id, ob.hospital_id, h.name AS hospital_name, ob.building_code, ob.building_name, ob.building_type,
    ob.latitude, ob.longitude, ob.floor_count,
    COUNT(DISTINCT u.unit_id) AS unit_count,
    SUM(u.staffed_bed_count) AS staffed_bed_count,
    SYSUTCDATETIME() AS last_refresh_datetime
FROM dbo.ops_building ob
JOIN dbo.hospitals h ON ob.hospital_id = h.hospital_id
LEFT JOIN dbo.ops_unit u ON ob.building_id = u.building_id
GROUP BY ob.building_id, ob.hospital_id, h.name, ob.building_code, ob.building_name, ob.building_type, ob.latitude, ob.longitude, ob.floor_count;
GO

CREATE OR ALTER VIEW dbo.vw_ops_hospital_snapshot AS
SELECT
    h.hospital_id, h.name AS hospital_name, h.specialty AS hospital_type, h.bed_count AS licensed_beds,
    SUM(u.staffed_bed_count) AS staffed_beds,
    SUM(CASE WHEN bs.occupancy_status = 'Occupied' THEN 1 ELSE 0 END) AS occupied_beds,
    SUM(CASE WHEN bs.occupancy_status = 'Available' THEN 1 ELSE 0 END) AS available_beds,
    SUM(CASE WHEN bs.occupancy_status = 'Blocked' THEN 1 ELSE 0 END) AS blocked_beds,
    SUM(CASE WHEN bs.occupancy_status = 'Cleaning' THEN 1 ELSE 0 END) AS cleaning_beds,
    CASE WHEN SUM(u.staffed_bed_count) > 0
        THEN ROUND(100.0 * SUM(CASE WHEN bs.occupancy_status = 'Occupied' THEN 1 ELSE 0 END) / NULLIF(SUM(u.staffed_bed_count), 0), 1)
        ELSE 0 END AS occupancy_pct,
    (SELECT COUNT(*) FROM dbo.admissions a WHERE a.hospital_id = h.hospital_id AND a.discharge_datetime IS NULL) AS active_patients,
    (SELECT COUNT(*) FROM dbo.admissions a JOIN dbo.encounters e ON a.encounter_id = e.encounter_id
        WHERE a.hospital_id = h.hospital_id AND a.discharge_datetime IS NULL AND e.encounter_type = 'Emergency') AS ed_patients,
    (SELECT COUNT(*) FROM dbo.admissions a WHERE a.hospital_id = h.hospital_id AND CAST(a.admit_datetime AS DATE) = CAST(SYSUTCDATETIME() AS DATE)) AS admissions_today,
    (SELECT COUNT(*) FROM dbo.admissions a WHERE a.hospital_id = h.hospital_id AND CAST(a.discharge_datetime AS DATE) = CAST(SYSUTCDATETIME() AS DATE)) AS discharges_today,
    (SELECT COUNT(*) FROM dbo.ops_patient_movement pm WHERE pm.hospital_id = h.hospital_id AND pm.movement_status IN ('Requested', 'Accepted', 'InProgress')) AS transfers_in_progress,
    (SELECT COUNT(*) FROM dbo.ops_discharge_readiness dr JOIN dbo.admissions a ON dr.encounter_id = a.encounter_id
        WHERE a.hospital_id = h.hospital_id AND a.discharge_datetime IS NULL AND dr.readiness_status <> 'Ready') AS pending_discharges,
    (SELECT AVG(CAST(DATEDIFF(HOUR, a.admit_datetime, ISNULL(a.discharge_datetime, SYSUTCDATETIME())) AS DECIMAL(10,2)) / 24.0)
        FROM dbo.admissions a WHERE a.hospital_id = h.hospital_id) AS average_length_of_stay_days,
    ss_agg.staffing_coverage_pct,
    eq_agg.equipment_available_pct,
    (SELECT COUNT(*) FROM dbo.ops_operational_alert oa WHERE oa.hospital_id = h.hospital_id AND oa.status <> 'Resolved') AS active_alert_count,
    (SELECT COUNT(*) FROM dbo.ops_operational_alert oa WHERE oa.hospital_id = h.hospital_id AND oa.status <> 'Resolved' AND oa.severity = 'Critical') AS critical_alert_count,
    CASE WHEN (SELECT COUNT(*) FROM dbo.ops_operational_alert oa WHERE oa.hospital_id = h.hospital_id AND oa.status <> 'Resolved' AND oa.severity = 'Critical') > 0 THEN 'Critical'
         WHEN (SELECT COUNT(*) FROM dbo.ops_operational_alert oa WHERE oa.hospital_id = h.hospital_id AND oa.status <> 'Resolved') > 0 THEN 'Warning'
         ELSE 'Normal' END AS operational_status,
    SYSUTCDATETIME() AS last_refresh_datetime
FROM dbo.hospitals h
LEFT JOIN dbo.ops_unit u ON h.hospital_id = u.hospital_id
LEFT JOIN dbo.beds bd ON bd.hospital_id = h.hospital_id AND bd.floor_number = u.source_floor_number
LEFT JOIN dbo.ops_bed_state bs ON bd.bed_id = bs.bed_id
OUTER APPLY (
    SELECT AVG(ss.staffing_coverage_pct) AS staffing_coverage_pct
    FROM dbo.ops_staffing_state ss JOIN dbo.ops_unit u2 ON ss.unit_id = u2.unit_id
    WHERE u2.hospital_id = h.hospital_id
) ss_agg
OUTER APPLY (
    SELECT CASE WHEN COUNT(*) = 0 THEN 100.0 ELSE
        ROUND(100.0 * SUM(CASE WHEN ISNULL(es.availability_status, 'Available') = 'Available' THEN 1 ELSE 0 END) / COUNT(*), 1) END AS equipment_available_pct
    FROM dbo.ops_equipment eq LEFT JOIN dbo.ops_equipment_state es ON eq.equipment_id = es.equipment_id
    WHERE eq.hospital_id = h.hospital_id
) eq_agg
GROUP BY h.hospital_id, h.name, h.specialty, h.bed_count, ss_agg.staffing_coverage_pct, eq_agg.equipment_available_pct;
GO

CREATE OR ALTER VIEW dbo.vw_ops_health_system_snapshot AS
SELECT
    COUNT(*) AS hospital_count,
    SUM(licensed_beds) AS licensed_bed_count,
    SUM(staffed_beds) AS staffed_bed_count,
    SUM(occupied_beds) AS occupied_bed_count,
    SUM(available_beds) AS available_bed_count,
    CASE WHEN SUM(staffed_beds) > 0 THEN ROUND(100.0 * SUM(occupied_beds) / NULLIF(SUM(staffed_beds), 0), 1) ELSE 0 END AS occupancy_pct,
    SUM(active_patients) AS active_encounter_count,
    SUM(admissions_today) AS admissions_today,
    SUM(discharges_today) AS discharges_today,
    SUM(pending_discharges) AS pending_discharges,
    SUM(ed_patients) AS ed_census,
    (SELECT COUNT(*) FROM dbo.ops_bed_state bs JOIN dbo.ops_unit u ON bs.bed_id IN (SELECT bed_id FROM dbo.beds b WHERE b.floor_number = u.source_floor_number AND b.hospital_id = u.hospital_id)
        WHERE u.unit_type = 'ICU' AND bs.occupancy_status = 'Occupied') AS icu_census,
    SUM(active_alert_count) AS open_alert_count,
    SUM(critical_alert_count) AS critical_alert_count,
    AVG(staffing_coverage_pct) AS staffing_coverage_pct,
    AVG(equipment_available_pct) AS equipment_available_pct,
    SYSUTCDATETIME() AS last_refresh_datetime
FROM dbo.vw_ops_hospital_snapshot;
GO

CREATE OR ALTER VIEW dbo.vw_ops_patient_operations_snapshot AS
SELECT
    p.patient_id, e.encounter_id, a.admission_id,
    h.hospital_id, h.name AS hospital_name,
    u.building_id, ob.building_name,
    u.source_floor_number AS floor_number, u.unit_id, u.unit_name,
    r.room_id, r.room_number, b.bed_id, b.bed_position,
    a.admit_datetime,
    DATEDIFF(HOUR, a.admit_datetime, SYSUTCDATETIME()) / 24.0 AS length_of_stay_days,
    dr.expected_discharge_datetime, dr.readiness_status AS discharge_readiness,
    (SELECT TOP 1 pm.movement_status FROM dbo.ops_patient_movement pm WHERE pm.encounter_id = e.encounter_id
        ORDER BY pm.requested_datetime DESC) AS pending_movement,
    doc.first_name + ' ' + doc.last_name AS assigned_attending_provider,
    rn_staff.display_name AS assigned_primary_rn,
    'Simulated' AS operational_acuity_category_label,
    CASE WHEN pba.los_days IS NOT NULL AND pba.los_days > 10 THEN 'Elevated (simulated)' ELSE 'Routine (simulated)' END AS synthetic_operational_risk_indicator,
    (SELECT COUNT(*) FROM dbo.ops_operational_alert oa WHERE oa.encounter_id = e.encounter_id AND oa.status <> 'Resolved') AS current_alert_count,
    SYSUTCDATETIME() AS last_refresh_datetime
FROM dbo.admissions a
JOIN dbo.encounters e ON a.encounter_id = e.encounter_id
JOIN dbo.patients p ON a.patient_id = p.patient_id
JOIN dbo.hospitals h ON a.hospital_id = h.hospital_id
LEFT JOIN dbo.doctors doc ON e.provider_id = doc.provider_id
LEFT JOIN dbo.ops_bed_state bs ON bs.admission_id = a.admission_id
LEFT JOIN dbo.beds b ON bs.bed_id = b.bed_id
LEFT JOIN dbo.rooms r ON b.room_id = r.room_id
LEFT JOIN dbo.ops_unit u ON u.hospital_id = b.hospital_id AND u.source_floor_number = b.floor_number
LEFT JOIN dbo.ops_building ob ON u.building_id = ob.building_id
LEFT JOIN dbo.ops_discharge_readiness dr ON dr.encounter_id = e.encounter_id
LEFT JOIN dbo.patient_bed_assignments pba ON pba.bed_id = b.bed_id AND pba.discharged_datetime IS NULL
LEFT JOIN dbo.ops_staff_assignment sa ON sa.bed_id = b.bed_id AND sa.status = 'Active' AND sa.assignment_role = 'Registered Nurse'
LEFT JOIN dbo.ops_staff rn_staff ON sa.staff_id = rn_staff.staff_id
WHERE a.discharge_datetime IS NULL;
GO

CREATE OR ALTER VIEW dbo.vw_ops_active_alerts AS
SELECT
    alert_id, alert_key, hospital_id, building_id, floor_number, unit_id, room_id, bed_id, equipment_id, encounter_id,
    alert_category, alert_type, severity, title, description, status, opened_datetime, acknowledged_datetime,
    source_metric, source_value, threshold_value, simulation_run_id,
    DATEDIFF(MINUTE, opened_datetime, SYSUTCDATETIME()) AS open_duration_minutes
FROM dbo.ops_operational_alert
WHERE status <> 'Resolved';
GO

CREATE OR ALTER VIEW dbo.vw_ops_equipment_availability AS
SELECT
    eq.equipment_id, eq.hospital_id, eq.unit_id, u.unit_name, eq.room_id, eq.equipment_type, eq.manufacturer, eq.model,
    eq.criticality, ISNULL(es.status, 'Available') AS status, ISNULL(es.availability_status, 'Available') AS availability_status,
    ISNULL(es.utilization_status, 'Idle') AS utilization_status, es.battery_pct, es.error_code, es.maintenance_due_date,
    es.last_seen_datetime, es.simulation_run_id
FROM dbo.ops_equipment eq
LEFT JOIN dbo.ops_equipment_state es ON eq.equipment_id = es.equipment_id
LEFT JOIN dbo.ops_unit u ON eq.unit_id = u.unit_id
WHERE eq.active_flag = 1;
GO

CREATE OR ALTER VIEW dbo.vw_ops_staffing_coverage AS
SELECT
    u.unit_id, u.hospital_id, h.name AS hospital_name, u.unit_name, u.clinical_specialty,
    ss.snapshot_datetime, ss.scheduled_rn_count, ss.present_rn_count, ss.required_rn_count,
    ss.scheduled_pct_count, ss.present_pct_count, ss.open_shift_count,
    staff_charge.display_name AS charge_nurse_display_name,
    ss.staffing_coverage_pct, ss.staffing_status, ss.simulation_run_id
FROM dbo.ops_unit u
JOIN dbo.hospitals h ON u.hospital_id = h.hospital_id
LEFT JOIN dbo.ops_staffing_state ss ON u.unit_id = ss.unit_id
LEFT JOIN dbo.ops_staff staff_charge ON ss.charge_nurse_staff_id = staff_charge.staff_id;
GO

CREATE OR ALTER VIEW dbo.vw_ops_patient_flow AS
SELECT
    pm.movement_id, pm.encounter_id, pm.patient_id, pm.hospital_id,
    pm.from_unit_id, fu.unit_name AS from_unit_name, pm.from_room_id, pm.from_bed_id,
    pm.to_unit_id, tu.unit_name AS to_unit_name, pm.to_room_id, pm.to_bed_id,
    pm.requested_datetime, pm.accepted_datetime, pm.started_datetime, pm.completed_datetime,
    pm.movement_type, pm.movement_status, pm.priority, pm.delay_reason, pm.simulation_run_id,
    DATEDIFF(MINUTE, pm.requested_datetime, ISNULL(pm.completed_datetime, SYSUTCDATETIME())) AS elapsed_minutes
FROM dbo.ops_patient_movement pm
LEFT JOIN dbo.ops_unit fu ON pm.from_unit_id = fu.unit_id
LEFT JOIN dbo.ops_unit tu ON pm.to_unit_id = tu.unit_id;
GO

CREATE OR ALTER VIEW dbo.vw_ops_floor_plan AS
SELECT
    h.hospital_id, h.name AS hospital_name, u.building_id, ob.building_name,
    u.source_floor_number AS floor_number, u.unit_id, u.unit_name, u.clinical_specialty,
    r.room_id, r.room_number, ra.floor_x, ra.floor_y, ra.width, ra.height,
    ISNULL(rs.operational_status, 'Available') AS room_operational_status,
    b.bed_id, b.bed_position, ISNULL(bs.occupancy_status, 'Available') AS bed_occupancy_status,
    bs.patient_id,
    (SELECT COUNT(*) FROM dbo.ops_operational_alert oa WHERE oa.room_id = r.room_id AND oa.status <> 'Resolved') AS room_active_alert_count
FROM dbo.ops_unit u
JOIN dbo.hospitals h ON u.hospital_id = h.hospital_id
LEFT JOIN dbo.ops_building ob ON u.building_id = ob.building_id
LEFT JOIN dbo.rooms r ON r.hospital_id = u.hospital_id AND r.floor_number = u.source_floor_number
LEFT JOIN dbo.ops_room_attribute ra ON r.room_id = ra.room_id
LEFT JOIN dbo.ops_room_state rs ON r.room_id = rs.room_id
LEFT JOIN dbo.beds b ON b.room_id = r.room_id
LEFT JOIN dbo.ops_bed_state bs ON b.bed_id = bs.bed_id;
GO
