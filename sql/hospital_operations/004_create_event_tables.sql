-- ============================================================================
-- 004_create_event_tables.sql
-- Hospital Operations - append-only historical/event tables.
-- These tables are ONLY ever inserted into, never updated or truncated by the
-- real-time simulator (Principle: "Do not use delete-and-reload behavior").
-- Idempotent: safe to run multiple times (IF NOT EXISTS guards).
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_equipment_event' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_equipment_event (
        equipment_event_id      BIGINT NOT NULL PRIMARY KEY,
        equipment_id              INT NOT NULL,              -- FK -> ops_equipment.equipment_id
        event_datetime              DATETIME2 NOT NULL,
        event_type                    VARCHAR(50) NOT NULL,
        severity                        VARCHAR(20) NOT NULL DEFAULT 'Info',
        metric_name                       VARCHAR(50) NULL,
        metric_value                        DECIMAL(10,2) NULL,
        metric_unit                          VARCHAR(20) NULL,
        status_before                          VARCHAR(20) NULL,
        status_after                             VARCHAR(20) NULL,
        description                                VARCHAR(500) NULL,
        simulation_run_id                            INT NULL
    );
    CREATE INDEX ix_ops_equipment_event_equip ON dbo.ops_equipment_event (equipment_id, event_datetime);
    CREATE INDEX ix_ops_equipment_event_run ON dbo.ops_equipment_event (simulation_run_id);
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_bed_state_event' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_bed_state_event (
        bed_state_event_id         BIGINT NOT NULL PRIMARY KEY,
        bed_id                       INT NOT NULL,             -- FK -> beds.bed_id
        event_datetime                 DATETIME2 NOT NULL,
        event_type                       VARCHAR(50) NOT NULL,
        status_before                      VARCHAR(20) NULL,
        status_after                         VARCHAR(20) NULL,
        encounter_id                           INT NULL,
        patient_id                               INT NULL,
        reason                                     VARCHAR(200) NULL,
        simulation_run_id                            INT NULL
    );
    CREATE INDEX ix_ops_bed_state_event_bed ON dbo.ops_bed_state_event (bed_id, event_datetime);
    CREATE INDEX ix_ops_bed_state_event_run ON dbo.ops_bed_state_event (simulation_run_id);
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_patient_movement' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_patient_movement (
        movement_id                BIGINT NOT NULL PRIMARY KEY,
        encounter_id                  INT NOT NULL,           -- FK -> encounters.encounter_id
        patient_id                      INT NOT NULL,         -- FK -> patients.patient_id
        hospital_id                       INT NOT NULL,       -- FK -> hospitals.hospital_id
        from_unit_id                       INT NULL,
        from_room_id                         INT NULL,
        from_bed_id                            INT NULL,
        to_unit_id                               INT NULL,
        to_room_id                                 INT NULL,
        to_bed_id                                    INT NULL,
        requested_datetime                             DATETIME2 NOT NULL,
        accepted_datetime                                DATETIME2 NULL,
        started_datetime                                   DATETIME2 NULL,
        completed_datetime                                   DATETIME2 NULL,
        movement_type                                          VARCHAR(30) NOT NULL,
        movement_status                                          VARCHAR(20) NOT NULL DEFAULT 'Requested',
        priority                                                   VARCHAR(20) NOT NULL DEFAULT 'Routine',
        delay_reason                                                 VARCHAR(200) NULL,
        simulation_run_id                                              INT NULL
    );
    CREATE INDEX ix_ops_patient_movement_encounter ON dbo.ops_patient_movement (encounter_id);
    CREATE INDEX ix_ops_patient_movement_hospital ON dbo.ops_patient_movement (hospital_id, requested_datetime);
    CREATE INDEX ix_ops_patient_movement_status ON dbo.ops_patient_movement (movement_status);
END
GO

IF OBJECT_ID('dbo.ops_simulated_episode', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ops_simulated_episode (
        encounter_id       INT NOT NULL PRIMARY KEY,
        admission_id       INT NOT NULL,
        patient_id         INT NOT NULL,
        simulation_run_id  INT NOT NULL,
        created_datetime   DATETIME2 NOT NULL
    );
END
GO

-- Length-of-stay planning columns. Added separately and idempotently so an
-- operations schema deployed before benchmark-driven length of stay upgrades
-- in place, without re-running the full setup notebook.
IF COL_LENGTH('dbo.ops_simulated_episode', 'icd_family') IS NULL
    ALTER TABLE dbo.ops_simulated_episode ADD icd_family VARCHAR(40) NULL;
GO
IF COL_LENGTH('dbo.ops_simulated_episode', 'target_los_hours') IS NULL
    ALTER TABLE dbo.ops_simulated_episode ADD target_los_hours DECIMAL(9, 2) NULL;
GO
IF COL_LENGTH('dbo.ops_simulated_episode', 'ed_dwell_hours') IS NULL
    ALTER TABLE dbo.ops_simulated_episode ADD ed_dwell_hours DECIMAL(9, 2) NULL;
GO
IF COL_LENGTH('dbo.ops_simulated_episode', 'icu_expected_flag') IS NULL
    ALTER TABLE dbo.ops_simulated_episode ADD icu_expected_flag BIT NULL;
GO
IF COL_LENGTH('dbo.ops_simulated_episode', 'expected_discharge_datetime') IS NULL
    ALTER TABLE dbo.ops_simulated_episode ADD expected_discharge_datetime DATETIME2 NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_alert_event' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_alert_event (
        alert_event_id           BIGINT NOT NULL PRIMARY KEY,
        alert_id                    INT NOT NULL,             -- FK -> ops_operational_alert.alert_id
        event_datetime                 DATETIME2 NOT NULL,
        event_type                       VARCHAR(30) NOT NULL,
        status_before                       VARCHAR(20) NULL,
        status_after                          VARCHAR(20) NULL,
        description                             VARCHAR(500) NULL,
        simulation_run_id                         INT NULL
    );
    CREATE INDEX ix_ops_alert_event_alert ON dbo.ops_alert_event (alert_id, event_datetime);
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_simulation_event_log' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_simulation_event_log (
        simulation_event_log_id    BIGINT NOT NULL PRIMARY KEY,
        simulation_run_id             INT NOT NULL,           -- FK -> ops_simulation_run.simulation_run_id
        iteration_number                 INT NOT NULL,
        event_datetime                     DATETIME2 NOT NULL,
        event_category                       VARCHAR(30) NOT NULL,
        entity_type                            VARCHAR(30) NULL,
        entity_id                                VARCHAR(50) NULL,
        action                                      VARCHAR(50) NOT NULL,
        status                                        VARCHAR(20) NOT NULL DEFAULT 'OK',
        message                                          VARCHAR(1000) NULL,
        diagnostic_json                                    NVARCHAR(MAX) NULL
    );
    CREATE INDEX ix_ops_sim_event_log_run ON dbo.ops_simulation_event_log (simulation_run_id, iteration_number);
END
GO
