-- ============================================================================
-- 003_create_current_state_tables.sql
-- Hospital Operations - current-state tables (upserted, never truncated).
-- Idempotent: safe to run multiple times (IF NOT EXISTS guards).
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_staffing_state' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_staffing_state (
        unit_id                  INT NOT NULL PRIMARY KEY,   -- FK -> ops_unit.unit_id
        snapshot_datetime        DATETIME2 NOT NULL,
        scheduled_rn_count       INT NOT NULL DEFAULT 0,
        present_rn_count         INT NOT NULL DEFAULT 0,
        required_rn_count        INT NOT NULL DEFAULT 0,
        scheduled_pct_count       INT NOT NULL DEFAULT 0,
        present_pct_count         INT NOT NULL DEFAULT 0,
        open_shift_count           INT NOT NULL DEFAULT 0,
        charge_nurse_staff_id      INT NULL,                -- FK -> ops_staff.staff_id
        staffing_coverage_pct       DECIMAL(5,2) NOT NULL DEFAULT 100.00,
        staffing_status              VARCHAR(20) NOT NULL DEFAULT 'Normal',
        simulation_run_id             INT NULL
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_equipment_state' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_equipment_state (
        equipment_id            INT NOT NULL PRIMARY KEY,   -- FK -> ops_equipment.equipment_id
        status                   VARCHAR(20) NOT NULL DEFAULT 'Available',
        availability_status        VARCHAR(20) NOT NULL DEFAULT 'Available',
        utilization_status         VARCHAR(20) NOT NULL DEFAULT 'Idle',
        battery_pct                 DECIMAL(5,2) NULL,
        temperature                 DECIMAL(6,2) NULL,
        pressure                    DECIMAL(6,2) NULL,
        error_code                  VARCHAR(20) NULL,
        maintenance_due_date         DATE NULL,
        last_seen_datetime            DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_datetime               DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        simulation_run_id               INT NULL
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_room_state' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_room_state (
        room_id                       INT NOT NULL PRIMARY KEY,  -- FK -> rooms.room_id
        operational_status             VARCHAR(20) NOT NULL DEFAULT 'Available',
        isolation_status                 VARCHAR(20) NOT NULL DEFAULT 'None',
        cleaning_status                   VARCHAR(20) NOT NULL DEFAULT 'Clean',
        maintenance_status                 VARCHAR(20) NOT NULL DEFAULT 'None',
        current_patient_count               INT NOT NULL DEFAULT 0,
        available_bed_count                  INT NOT NULL DEFAULT 0,
        last_cleaned_datetime                  DATETIME2 NULL,
        next_expected_available_datetime         DATETIME2 NULL,
        updated_datetime                           DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        simulation_run_id                           INT NULL
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_bed_state' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_bed_state (
        bed_id                        INT NOT NULL PRIMARY KEY,  -- FK -> beds.bed_id
        operational_status              VARCHAR(20) NOT NULL DEFAULT 'Available',
        occupancy_status                  VARCHAR(20) NOT NULL DEFAULT 'Available',
        encounter_id                       INT NULL,             -- FK -> encounters.encounter_id
        patient_id                          INT NULL,            -- FK -> patients.patient_id
        admission_id                         INT NULL,           -- FK -> admissions.admission_id
        assigned_datetime                      DATETIME2 NULL,
        expected_release_datetime                DATETIME2 NULL,
        cleaning_required_flag                     BIT NOT NULL DEFAULT 0,
        updated_datetime                             DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        simulation_run_id                             INT NULL
    );
    CREATE INDEX ix_ops_bed_state_occupancy ON dbo.ops_bed_state (occupancy_status);
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_discharge_readiness' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_discharge_readiness (
        encounter_id                 INT NOT NULL PRIMARY KEY,   -- FK -> encounters.encounter_id
        patient_id                    INT NOT NULL,               -- FK -> patients.patient_id
        expected_discharge_datetime     DATETIME2 NULL,
        readiness_status                  VARCHAR(20) NOT NULL DEFAULT 'Not Ready',
        clinical_ready_flag                 BIT NOT NULL DEFAULT 0,
        medication_ready_flag                 BIT NOT NULL DEFAULT 0,
        transport_ready_flag                   BIT NOT NULL DEFAULT 0,
        destination_ready_flag                   BIT NOT NULL DEFAULT 0,
        education_complete_flag                    BIT NOT NULL DEFAULT 0,
        outstanding_barrier_count                    INT NOT NULL DEFAULT 0,
        primary_barrier                                VARCHAR(50) NULL,
        updated_datetime                                 DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        simulation_run_id                                 INT NULL
    );
END
GO

-- ---------------------------------------------------------------------------
-- ops_operational_alert: mutable `status` field (Open/Acknowledged/Resolved)
-- but rows are NEVER deleted -- resolved alerts remain for history/reporting.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_operational_alert' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_operational_alert (
        alert_id             INT NOT NULL PRIMARY KEY,
        alert_key             VARCHAR(200) NOT NULL,       -- stable dedup key, e.g. 'CAPACITY:ICU:unit=12'
        hospital_id            INT NOT NULL,               -- FK -> hospitals.hospital_id
        building_id             INT NULL,
        floor_number              INT NULL,
        unit_id                    INT NULL,
        room_id                     INT NULL,
        bed_id                       INT NULL,
        equipment_id                  INT NULL,
        encounter_id                   INT NULL,
        alert_category                  VARCHAR(30) NOT NULL,
        alert_type                        VARCHAR(50) NOT NULL,
        severity                            VARCHAR(20) NOT NULL,
        title                                 VARCHAR(200) NOT NULL,
        description                            VARCHAR(1000) NULL,
        status                                   VARCHAR(20) NOT NULL DEFAULT 'Open',
        opened_datetime                            DATETIME2 NOT NULL,
        acknowledged_datetime                        DATETIME2 NULL,
        resolved_datetime                              DATETIME2 NULL,
        source_metric                                    VARCHAR(50) NULL,
        source_value                                       DECIMAL(10,2) NULL,
        threshold_value                                      DECIMAL(10,2) NULL,
        simulation_run_id                                     INT NULL,
        created_datetime                                        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_datetime                                          DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX ix_ops_alert_status ON dbo.ops_operational_alert (status);
    CREATE INDEX ix_ops_alert_key ON dbo.ops_operational_alert (alert_key);
    CREATE INDEX ix_ops_alert_hospital ON dbo.ops_operational_alert (hospital_id);
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_simulation_control' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_simulation_control (
        control_id                 INT NOT NULL PRIMARY KEY,
        simulator_name               VARCHAR(100) NOT NULL UNIQUE,
        requested_state                VARCHAR(10) NOT NULL DEFAULT 'RUN',   -- RUN | PAUSE | STOP
        update_interval_seconds          INT NOT NULL DEFAULT 10,
        speed_multiplier                   DECIMAL(9,2) NOT NULL DEFAULT 60.0,
        random_seed                          INT NULL,
        scenario_name                          VARCHAR(50) NOT NULL DEFAULT 'NORMAL_OPERATIONS',
        selected_hospital_id                     INT NULL,
        last_updated_datetime                      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_by                                   VARCHAR(100) NULL
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_simulation_run' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_simulation_run (
        simulation_run_id                  INT NOT NULL PRIMARY KEY,
        simulator_name                        VARCHAR(100) NOT NULL,
        scenario_name                            VARCHAR(50) NOT NULL,
        random_seed                                INT NULL,
        started_datetime                             DATETIME2 NOT NULL,
        ended_datetime                                 DATETIME2 NULL,
        current_status                                   VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
        iteration_count                                    INT NOT NULL DEFAULT 0,
        last_successful_iteration_datetime                   DATETIME2 NULL,
        error_count                                            INT NOT NULL DEFAULT 0,
        hostname                                                 VARCHAR(200) NULL,
        configuration_json                                         NVARCHAR(MAX) NULL
    );
    CREATE INDEX ix_ops_simulation_run_status ON dbo.ops_simulation_run (current_status);
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_simulation_checkpoint' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_simulation_checkpoint (
        simulator_name                 VARCHAR(100) NOT NULL,
        simulation_run_id                 INT NOT NULL,
        last_completed_iteration            INT NOT NULL DEFAULT 0,
        simulated_datetime                    DATETIME2 NULL,
        random_state                            NVARCHAR(MAX) NULL,
        checkpoint_datetime                       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        checkpoint_json                             NVARCHAR(MAX) NULL,
        CONSTRAINT pk_ops_simulation_checkpoint PRIMARY KEY (simulator_name, simulation_run_id)
    );
END
GO
