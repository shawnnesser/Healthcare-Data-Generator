-- ============================================================================
-- 008_drop_operations_objects.sql
-- Hospital Operations - full teardown. Removes ONLY ops_*/vw_ops_* objects.
-- Does NOT touch any existing clinical table, view, or the generator's own
-- floors/rooms/beds/patient_bed_assignments tables.
-- Safe to run multiple times (IF EXISTS guards). Views dropped before tables;
-- tables dropped in reverse dependency order.
-- ============================================================================

-- Views first (they reference the tables below).
IF OBJECT_ID('dbo.vw_ops_health_system_snapshot', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_health_system_snapshot;
IF OBJECT_ID('dbo.vw_ops_hospital_snapshot', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_hospital_snapshot;
IF OBJECT_ID('dbo.vw_ops_building_snapshot', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_building_snapshot;
IF OBJECT_ID('dbo.vw_ops_floor_snapshot', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_floor_snapshot;
IF OBJECT_ID('dbo.vw_ops_unit_snapshot', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_unit_snapshot;
IF OBJECT_ID('dbo.vw_ops_room_snapshot', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_room_snapshot;
IF OBJECT_ID('dbo.vw_ops_bed_snapshot', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_bed_snapshot;
IF OBJECT_ID('dbo.vw_ops_patient_operations_snapshot', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_patient_operations_snapshot;
IF OBJECT_ID('dbo.vw_ops_active_alerts', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_active_alerts;
IF OBJECT_ID('dbo.vw_ops_equipment_availability', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_equipment_availability;
IF OBJECT_ID('dbo.vw_ops_staffing_coverage', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_staffing_coverage;
IF OBJECT_ID('dbo.vw_ops_patient_flow', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_patient_flow;
IF OBJECT_ID('dbo.vw_ops_floor_plan', 'V') IS NOT NULL DROP VIEW dbo.vw_ops_floor_plan;
GO

-- Event/history tables (no dependents).
IF OBJECT_ID('dbo.ops_simulation_event_log', 'U') IS NOT NULL DROP TABLE dbo.ops_simulation_event_log;
IF OBJECT_ID('dbo.ops_alert_event', 'U') IS NOT NULL DROP TABLE dbo.ops_alert_event;
IF OBJECT_ID('dbo.ops_patient_movement', 'U') IS NOT NULL DROP TABLE dbo.ops_patient_movement;
IF OBJECT_ID('dbo.ops_bed_state_event', 'U') IS NOT NULL DROP TABLE dbo.ops_bed_state_event;
IF OBJECT_ID('dbo.ops_equipment_event', 'U') IS NOT NULL DROP TABLE dbo.ops_equipment_event;
GO

-- Simulation control/audit tables.
IF OBJECT_ID('dbo.ops_simulation_checkpoint', 'U') IS NOT NULL DROP TABLE dbo.ops_simulation_checkpoint;
IF OBJECT_ID('dbo.ops_simulation_run', 'U') IS NOT NULL DROP TABLE dbo.ops_simulation_run;
IF OBJECT_ID('dbo.ops_simulation_control', 'U') IS NOT NULL DROP TABLE dbo.ops_simulation_control;
GO

-- Current-state tables.
IF OBJECT_ID('dbo.ops_operational_alert', 'U') IS NOT NULL DROP TABLE dbo.ops_operational_alert;
IF OBJECT_ID('dbo.ops_discharge_readiness', 'U') IS NOT NULL DROP TABLE dbo.ops_discharge_readiness;
IF OBJECT_ID('dbo.ops_bed_state', 'U') IS NOT NULL DROP TABLE dbo.ops_bed_state;
IF OBJECT_ID('dbo.ops_room_state', 'U') IS NOT NULL DROP TABLE dbo.ops_room_state;
IF OBJECT_ID('dbo.ops_equipment_state', 'U') IS NOT NULL DROP TABLE dbo.ops_equipment_state;
IF OBJECT_ID('dbo.ops_staffing_state', 'U') IS NOT NULL DROP TABLE dbo.ops_staffing_state;
GO

-- Operational/reference tables (staff_assignment before staff/shift; equipment
-- before unit; room_attribute before unit; unit before building).
IF OBJECT_ID('dbo.ops_equipment', 'U') IS NOT NULL DROP TABLE dbo.ops_equipment;
IF OBJECT_ID('dbo.ops_staff_assignment', 'U') IS NOT NULL DROP TABLE dbo.ops_staff_assignment;
IF OBJECT_ID('dbo.ops_staff', 'U') IS NOT NULL DROP TABLE dbo.ops_staff;
IF OBJECT_ID('dbo.ops_shift', 'U') IS NOT NULL DROP TABLE dbo.ops_shift;
IF OBJECT_ID('dbo.ops_room_attribute', 'U') IS NOT NULL DROP TABLE dbo.ops_room_attribute;
IF OBJECT_ID('dbo.ops_unit', 'U') IS NOT NULL DROP TABLE dbo.ops_unit;
IF OBJECT_ID('dbo.ops_building', 'U') IS NOT NULL DROP TABLE dbo.ops_building;
GO

SELECT 'Hospital Operations objects dropped (clinical tables untouched).' AS result;
