-- ============================================================================
-- 005_create_indexes.sql
-- Hospital Operations - supplemental indexes for the query patterns the
-- future Fabric App / Rayfin UI will poll frequently (health-system summary,
-- hospital summary, floor/room drill-down, active alerts, staffing coverage,
-- equipment availability, recent event history). Most per-table indexes were
-- already created inline in 002/003/004; this script adds the remaining
-- cross-table lookup indexes. Idempotent (guarded by sys.indexes checks).
-- Deliberately NOT over-indexing append-only event tables beyond what's
-- needed for entity/timestamp/simulation_run_id lookups.
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ops_equipment_state_status' AND object_id = OBJECT_ID('dbo.ops_equipment_state'))
    CREATE INDEX ix_ops_equipment_state_status ON dbo.ops_equipment_state (status, availability_status);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ops_room_state_status' AND object_id = OBJECT_ID('dbo.ops_room_state'))
    CREATE INDEX ix_ops_room_state_status ON dbo.ops_room_state (operational_status);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ops_discharge_readiness_status' AND object_id = OBJECT_ID('dbo.ops_discharge_readiness'))
    CREATE INDEX ix_ops_discharge_readiness_status ON dbo.ops_discharge_readiness (readiness_status);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ops_alert_severity' AND object_id = OBJECT_ID('dbo.ops_operational_alert'))
    CREATE INDEX ix_ops_alert_severity ON dbo.ops_operational_alert (severity, status);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ops_equipment_type' AND object_id = OBJECT_ID('dbo.ops_equipment'))
    CREATE INDEX ix_ops_equipment_type ON dbo.ops_equipment (equipment_type, hospital_id);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ops_staff_assignment_bed' AND object_id = OBJECT_ID('dbo.ops_staff_assignment'))
    CREATE INDEX ix_ops_staff_assignment_bed ON dbo.ops_staff_assignment (bed_id) WHERE bed_id IS NOT NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ops_patient_movement_run' AND object_id = OBJECT_ID('dbo.ops_patient_movement'))
    CREATE INDEX ix_ops_patient_movement_run ON dbo.ops_patient_movement (simulation_run_id);
GO
