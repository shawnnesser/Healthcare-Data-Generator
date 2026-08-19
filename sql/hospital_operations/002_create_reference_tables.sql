-- ============================================================================
-- 002_create_reference_tables.sql
-- Hospital Operations - hierarchy, staffing, and equipment reference tables
-- Idempotent: safe to run multiple times (IF NOT EXISTS guards).
-- Does NOT touch any existing clinical table (hospitals, departments, floors,
-- rooms, beds, etc.) - only reads/references their existing primary keys.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- ops_building: NEW physical entity (no building concept exists upstream).
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_building' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_building (
        building_id         INT NOT NULL PRIMARY KEY,
        hospital_id         INT NOT NULL,               -- FK -> hospitals.hospital_id
        building_code        VARCHAR(20) NOT NULL,
        building_name        VARCHAR(100) NOT NULL,
        building_type        VARCHAR(50) NOT NULL,
        campus_label         VARCHAR(100) NULL,
        latitude             DECIMAL(9,6) NULL,          -- synthetic map coordinate
        longitude            DECIMAL(9,6) NULL,          -- synthetic map coordinate
        floor_count           INT NOT NULL DEFAULT 0,
        active_flag           BIT NOT NULL DEFAULT 1,
        created_datetime     DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_datetime     DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX ix_ops_building_hospital ON dbo.ops_building (hospital_id);
END
GO

-- ---------------------------------------------------------------------------
-- ops_unit: NEW operational-hierarchy entity. Maps 1:1 to an existing
-- `floors` row via the natural key (hospital_id, floor_number) since `floors`
-- has no surrogate key. UNIQUE constraint prevents duplicate units on re-run.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_unit' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_unit (
        unit_id               INT NOT NULL PRIMARY KEY,
        hospital_id           INT NOT NULL,              -- FK -> hospitals.hospital_id
        building_id           INT NOT NULL,              -- FK -> ops_building.building_id
        source_floor_number   INT NOT NULL,              -- FK (natural) -> floors.floor_number
        source_department     VARCHAR(100) NULL,          -- denormalized from floors.department
        department_id         INT NULL,                  -- FK -> departments.department_id (nullable, best-effort match)
        unit_code             VARCHAR(20) NOT NULL,
        unit_name             VARCHAR(100) NOT NULL,
        unit_type             VARCHAR(50) NOT NULL,
        clinical_specialty    VARCHAR(100) NULL,
        licensed_bed_count    INT NOT NULL DEFAULT 0,
        staffed_bed_count     INT NOT NULL DEFAULT 0,
        nurse_ratio_target    DECIMAL(5,2) NOT NULL DEFAULT 4.0,
        active_flag           BIT NOT NULL DEFAULT 1,
        created_datetime      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_datetime      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT uq_ops_unit_hospital_floor UNIQUE (hospital_id, source_floor_number)
    );
    CREATE INDEX ix_ops_unit_hospital ON dbo.ops_unit (hospital_id);
    CREATE INDEX ix_ops_unit_building ON dbo.ops_unit (building_id);
END
GO

-- ---------------------------------------------------------------------------
-- ops_room_attribute: 1:1 extension of the EXISTING `rooms` table (no
-- duplicate room inventory). Adds floor-plan coordinates + capability flags.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_room_attribute' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_room_attribute (
        room_id                     INT NOT NULL PRIMARY KEY,   -- FK -> rooms.room_id (1:1)
        unit_id                     INT NOT NULL,               -- FK -> ops_unit.unit_id
        room_name                   VARCHAR(100) NULL,
        isolation_capable_flag      BIT NOT NULL DEFAULT 0,
        negative_pressure_flag      BIT NOT NULL DEFAULT 0,
        telemetry_capable_flag      BIT NOT NULL DEFAULT 0,
        private_room_flag           BIT NOT NULL DEFAULT 0,
        floor_x                     DECIMAL(9,3) NOT NULL DEFAULT 0,
        floor_y                     DECIMAL(9,3) NOT NULL DEFAULT 0,
        width                       DECIMAL(9,3) NOT NULL DEFAULT 1,
        height                      DECIMAL(9,3) NOT NULL DEFAULT 1,
        active_flag                 BIT NOT NULL DEFAULT 1,
        created_datetime            DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_datetime            DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX ix_ops_room_attribute_unit ON dbo.ops_room_attribute (unit_id);
END
GO

-- ---------------------------------------------------------------------------
-- ops_shift: NEW reference table of configurable day/evening/night shifts.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_shift' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_shift (
        shift_id              INT NOT NULL PRIMARY KEY,
        shift_code            VARCHAR(10) NOT NULL UNIQUE,
        shift_name            VARCHAR(50) NOT NULL,
        start_time            TIME NOT NULL,
        end_time              TIME NOT NULL,
        crosses_midnight_flag BIT NOT NULL DEFAULT 0
    );
END
GO

-- ---------------------------------------------------------------------------
-- ops_staff: synthetic operational staff. Physician roles reuse a real
-- doctors.provider_id via existing_provider_id; non-physician roles are
-- synthetic-only (existing_provider_id IS NULL).
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_staff' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_staff (
        staff_id              INT NOT NULL PRIMARY KEY,
        existing_provider_id  INT NULL,                  -- FK -> doctors.provider_id (physician roles only)
        synthetic_staff_number VARCHAR(20) NOT NULL UNIQUE,
        display_name           VARCHAR(100) NOT NULL,
        role_code               VARCHAR(20) NOT NULL,
        role_name               VARCHAR(50) NOT NULL,
        credential              VARCHAR(20) NULL,
        primary_hospital_id     INT NOT NULL,            -- FK -> hospitals.hospital_id
        primary_unit_id         INT NULL,                -- FK -> ops_unit.unit_id
        active_flag             BIT NOT NULL DEFAULT 1,
        created_datetime        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_datetime        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX ix_ops_staff_hospital ON dbo.ops_staff (primary_hospital_id);
    CREATE INDEX ix_ops_staff_unit ON dbo.ops_staff (primary_unit_id);
END
GO

-- ---------------------------------------------------------------------------
-- ops_staff_assignment: scheduled/actual staff assignments to a unit/room/
-- bed/encounter for a given shift.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_staff_assignment' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_staff_assignment (
        staff_assignment_id     INT NOT NULL PRIMARY KEY,
        staff_id                INT NOT NULL,            -- FK -> ops_staff.staff_id
        hospital_id             INT NOT NULL,            -- FK -> hospitals.hospital_id
        unit_id                 INT NOT NULL,            -- FK -> ops_unit.unit_id
        room_id                 INT NULL,                -- FK -> rooms.room_id
        bed_id                  INT NULL,                -- FK -> beds.bed_id
        encounter_id            INT NULL,                -- FK -> encounters.encounter_id
        shift_id                INT NOT NULL,            -- FK -> ops_shift.shift_id
        assignment_start_datetime DATETIME2 NOT NULL,
        assignment_end_datetime   DATETIME2 NULL,
        assignment_role          VARCHAR(50) NOT NULL,
        patient_load             INT NOT NULL DEFAULT 0,
        status                   VARCHAR(20) NOT NULL DEFAULT 'Scheduled',
        source_run_id            INT NULL,                -- FK -> ops_simulation_run.simulation_run_id
        created_datetime         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_datetime         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX ix_ops_staff_assignment_unit ON dbo.ops_staff_assignment (unit_id);
    CREATE INDEX ix_ops_staff_assignment_staff ON dbo.ops_staff_assignment (staff_id);
    CREATE INDEX ix_ops_staff_assignment_status ON dbo.ops_staff_assignment (status);
END
GO

-- ---------------------------------------------------------------------------
-- ops_equipment: synthetic equipment inventory located at unit/room level.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ops_equipment' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ops_equipment (
        equipment_id             INT NOT NULL PRIMARY KEY,
        hospital_id              INT NOT NULL,           -- FK -> hospitals.hospital_id
        building_id              INT NOT NULL,            -- FK -> ops_building.building_id
        floor_number              INT NOT NULL,            -- denormalized -> floors.floor_number
        unit_id                   INT NOT NULL,            -- FK -> ops_unit.unit_id
        room_id                   INT NULL,                -- FK -> rooms.room_id
        equipment_type            VARCHAR(50) NOT NULL,
        manufacturer               VARCHAR(50) NULL,
        model                       VARCHAR(50) NULL,
        synthetic_serial_number    VARCHAR(30) NOT NULL UNIQUE,
        criticality                 VARCHAR(20) NOT NULL DEFAULT 'Standard',
        installation_date           DATE NULL,
        maintenance_interval_days   INT NOT NULL DEFAULT 180,
        active_flag                 BIT NOT NULL DEFAULT 1,
        created_datetime            DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_datetime            DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX ix_ops_equipment_unit ON dbo.ops_equipment (unit_id);
    CREATE INDEX ix_ops_equipment_hospital ON dbo.ops_equipment (hospital_id);
END
GO
