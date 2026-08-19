-- ============================================================================
-- 007_create_validation_queries.sql
-- Hospital Operations - reference validation queries (read-only).
-- These mirror the checks implemented programmatically in
-- src/hospital_operations/validation.py and can be run manually (e.g. in
-- SSMS / Fabric SQL query editor) to spot-check the operations schema.
-- Every query is safe to run at any time (SELECT only, no side effects).
-- ============================================================================

-- 1. Hierarchy referential integrity -----------------------------------------
-- Every building references a valid hospital.
SELECT b.building_id, b.hospital_id FROM dbo.ops_building b
LEFT JOIN dbo.hospitals h ON b.hospital_id = h.hospital_id WHERE h.hospital_id IS NULL;

-- Every unit references a valid building, hospital, and an existing floors row.
SELECT u.unit_id, u.hospital_id, u.building_id, u.source_floor_number FROM dbo.ops_unit u
LEFT JOIN dbo.ops_building b ON u.building_id = b.building_id
LEFT JOIN dbo.hospitals h ON u.hospital_id = h.hospital_id
LEFT JOIN dbo.floors f ON f.hospital_id = u.hospital_id AND f.floor_number = u.source_floor_number
WHERE b.building_id IS NULL OR h.hospital_id IS NULL OR f.floor_number IS NULL;

-- Every ops_room_attribute references a valid room and unit.
SELECT ra.room_id, ra.unit_id FROM dbo.ops_room_attribute ra
LEFT JOIN dbo.rooms r ON ra.room_id = r.room_id
LEFT JOIN dbo.ops_unit u ON ra.unit_id = u.unit_id
WHERE r.room_id IS NULL OR u.unit_id IS NULL;

-- Every ops_bed_state references a valid bed.
SELECT bs.bed_id FROM dbo.ops_bed_state bs
LEFT JOIN dbo.beds b ON bs.bed_id = b.bed_id WHERE b.bed_id IS NULL;

-- 2. Unit bed-count reconciliation -------------------------------------------
-- Unit staffed_bed_count vs actual beds present on that floor/hospital.
SELECT u.unit_id, u.unit_name, u.staffed_bed_count AS declared,
    (SELECT COUNT(*) FROM dbo.beds b WHERE b.hospital_id = u.hospital_id AND b.floor_number = u.source_floor_number) AS actual_bed_count
FROM dbo.ops_unit u
HAVING u.staffed_bed_count <> (SELECT COUNT(*) FROM dbo.beds b WHERE b.hospital_id = u.hospital_id AND b.floor_number = u.source_floor_number);

-- Hospital ops_unit.staffed_bed_count sum vs latest hospital_department_beds.beds_allocated sum (informational, not enforced -- see analysis doc section 8).
SELECT h.hospital_id, h.name,
    (SELECT SUM(staffed_bed_count) FROM dbo.ops_unit WHERE hospital_id = h.hospital_id) AS ops_unit_bed_sum,
    (SELECT SUM(hdb.beds_allocated) FROM dbo.hospital_department_beds hdb
        WHERE hdb.hospital_id = h.hospital_id AND hdb.date = (SELECT MAX(date) FROM dbo.hospital_department_beds)) AS latest_department_bed_sum
FROM dbo.hospitals h;

-- 3. Bed/encounter consistency ------------------------------------------------
-- No bed has more than one active (non-resolved) encounter.
SELECT bed_id, COUNT(*) AS active_rows FROM dbo.ops_bed_state
WHERE occupancy_status = 'Occupied' GROUP BY bed_id HAVING COUNT(*) > 1;

-- No encounter occupies more than one bed at a time.
SELECT encounter_id, COUNT(DISTINCT bed_id) AS distinct_beds FROM dbo.ops_bed_state
WHERE occupancy_status = 'Occupied' AND encounter_id IS NOT NULL GROUP BY encounter_id HAVING COUNT(DISTINCT bed_id) > 1;

-- Occupied beds must have an encounter and patient; available/cleaning beds must not.
SELECT bed_id, occupancy_status, encounter_id, patient_id FROM dbo.ops_bed_state
WHERE (occupancy_status = 'Occupied' AND (encounter_id IS NULL OR patient_id IS NULL))
   OR (occupancy_status IN ('Available', 'Cleaning') AND encounter_id IS NOT NULL);

-- 4. Staffing / equipment / alert validity ------------------------------------
-- Charge nurses are assigned to valid units.
SELECT ss.unit_id, ss.charge_nurse_staff_id FROM dbo.ops_staffing_state ss
LEFT JOIN dbo.ops_staff s ON ss.charge_nurse_staff_id = s.staff_id
WHERE ss.charge_nurse_staff_id IS NOT NULL AND s.staff_id IS NULL;

-- Equipment locations are valid (unit + optional room match hospital).
SELECT eq.equipment_id FROM dbo.ops_equipment eq
LEFT JOIN dbo.ops_unit u ON eq.unit_id = u.unit_id
WHERE u.unit_id IS NULL OR u.hospital_id <> eq.hospital_id;

-- Active alerts reference valid entities (hospital always required).
SELECT alert_id FROM dbo.ops_operational_alert oa
LEFT JOIN dbo.hospitals h ON oa.hospital_id = h.hospital_id
WHERE oa.status <> 'Resolved' AND h.hospital_id IS NULL;

-- 5. Snapshot reconciliation ---------------------------------------------------
-- Hospital snapshot occupancy = occupied staffed beds / staffed beds (spot check).
SELECT hospital_id, hospital_name, staffed_beds, occupied_beds, occupancy_pct,
    CASE WHEN staffed_beds > 0 THEN ROUND(100.0 * occupied_beds / staffed_beds, 1) ELSE 0 END AS recomputed_occupancy_pct
FROM dbo.vw_ops_hospital_snapshot
WHERE ABS(occupancy_pct - CASE WHEN staffed_beds > 0 THEN ROUND(100.0 * occupied_beds / staffed_beds, 1) ELSE 0 END) > 0.1;
