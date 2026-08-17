# Patient Location & Floor Management System

## Overview
This system provides real-time patient location tracking, floor plan visualization, and clinical status monitoring across all hospital facilities.

## Database Schema

### New Tables

#### `floors`
Represents each floor/unit in a hospital
- `hospital_id`: FK to hospitals
- `floor_number`: Sequential floor identifier (1, 2, 3, etc.)
- `department`: Department/unit name (e.g., "Emergency Department", "Cardiac ICU", "Pediatric Ward 1")
- `bed_type`: Category (Emergency, Critical Care, Medical/Surgical, Rehabilitation, etc.)
- `capacity`: Total bed count on this floor

**Example:**
```sql
SELECT * FROM floors WHERE hospital_id = 1
-- Floor 1: Emergency Department, 45 beds
-- Floor 2: Intensive Care Unit, 30 beds
-- Floor 3: Medical/Surgical Unit 1, 75 beds
```

#### `rooms`
Individual rooms on each floor
- `room_id`: Unique identifier
- `hospital_id`: FK to hospitals
- `floor_number`: FK to floors
- `room_number`: Sequential number within floor
- `bed_count`: How many beds in this room (1, 2, or 4)
- `room_type`: Single, Double, Quad

**Layout:**
- Critical Care floors: 90% single rooms, 10% double
- Rehab/Recovery: 60% single, 40% double
- Medical/Surgical: 30% single, 70% shared (60% double, 40% quad)

#### `beds`
Individual bed tracking
- `bed_id`: Unique identifier
- `room_id`: FK to rooms
- `hospital_id`: FK to hospitals
- `floor_number`: FK to floors
- `bed_position`: Position within room (1, 2, 3, or 4)
- `bed_type`: Inherited from floor (Emergency, Critical Care, Medical, etc.)
- `status`: Available | Occupied | Maintenance | Closed

#### `patient_bed_assignments`
Current patient location and clinical status
- `assignment_id`: Unique identifier
- `admission_id`: FK to admissions
- `patient_id`: FK to patients
- `hospital_id`: FK to hospitals
- `bed_id`: FK to beds
- `floor_number`: Current floor
- `room_number`: Current room
- `bed_position`: Current bed position
- `assigned_datetime`: When patient was assigned to bed
- `discharged_datetime`: When patient left bed (NULL = still admitted)
- `patient_status`: Clinical status (Critical, Unstable, Improving, Stable, Post-Op, Recovering)
- `diagnosis_code`: Primary diagnosis ICD code
- `los_days`: Length of stay in days

## Floor Organization by Hospital Specialty

### General Hospitals
- **Floor 1**: Emergency Department (6% capacity)
- **Floor 2**: Intensive Care Unit (8% capacity)
- **Floors 3-4+**: Medical/Surgical Units (40% capacity across 2-3 floors)
- **Floor 5**: Specialty Services (remaining capacity)

### Cardiac Specialty Hospital
- **Floor 1**: Cardiac ICU (25% capacity - high acuity)
- **Floors 2-3**: Cardiology Units (60% capacity)
- **Floor 4**: Cath Lab Recovery (remaining)

### Pediatric Hospital
- **Floor 1**: Pediatric Emergency (8% capacity)
- **Floor 2**: Pediatric Intensive Care (12% capacity)
- **Floors 3-4**: Pediatric Wards (remaining capacity)

### Cancer Center
- **Floor 1**: Oncology ICU (20% capacity)
- **Floors 2-3**: Oncology Units (70% capacity)
- **Floor 4**: Bone Marrow Transplant (remaining)

### Rehabilitation Center
- **Floor 1**: Intensive Rehabilitation (40% capacity)
- **Floor 2**: Post-Surgical Rehabilitation (30% capacity)
- **Floor 3**: Specialty Rehabilitation (remaining)

## Patient Status Determination

Clinical status is calculated based on:
1. **Diagnosis severity**: Critical diagnoses (ACS, sepsis, stroke, acute leukemia) → Critical/Unstable
2. **Length of stay**: Progression from Unstable → Improving → Stable as LOS increases
3. **Hospital specialty**: Cardiac and cancer patients default to higher acuity levels
4. **Age factors**: Very elderly (80+) or very young (5-) may indicate higher acuity

**Status Types:**
- **Critical**: Severe diagnosis, early admission period (≤2 days)
- **Unstable**: Moderate severity or post-operative period (≤1 day post-op)
- **Post-Op**: Immediate post-operative (≤1 day)
- **Recovering**: Early post-op recovery (1-3 days post-op)
- **Improving**: Stabilizing, progressing well (3-7 days)
- **Stable**: Stable condition, ready for discharge planning (7+ days)

## SQL Views

### `vw_floor_plan`
Complete floor plan visualization with bed-level detail
- Shows every bed, room, floor
- Indicates occupancy status (Available/Occupied)
- Shows patient name, diagnosis, clinical status
- Includes floor occupancy percentage

**Use Case:** Hospital operations, real-time bed management, capacity planning

```sql
SELECT * FROM vw_floor_plan WHERE hospital_id = 1 AND floor_number = 2
-- Shows all beds on ICU, who occupies each, their status
```

### `vw_patient_location`
Patient-centric view - where is each patient and their full clinical picture
- Patient demographics (age, name)
- Current location (hospital, floor, room, bed)
- Clinical status and diagnosis
- Chief complaint, medications, doctor, payer
- Length of stay

**Use Case:** Nurse stations, patient lookups, care coordination

```sql
SELECT patient_name, clinical_status, department, doctor_name 
FROM vw_patient_location 
WHERE hospital_id = 6 AND clinical_status IN ('Critical', 'Unstable')
-- Find all critical patients at Cardiac Hospital with their doctors
```

### `vw_floor_occupancy`
Floor-level summary dashboard
- Bed counts by status (occupied, available)
- Occupancy percentage
- Patient count by clinical status (Critical, Unstable, Improving, Stable)

**Use Case:** Floor managers, bed coordinators, census reports

```sql
SELECT * FROM vw_floor_occupancy WHERE occupancy_pct > '80%'
-- Find overcrowded floors
```

### `vw_hospital_status`
Hospital-wide operational dashboard
- Total occupancy across facility
- Count of patients by clinical status (Critical, Unstable, Improving, Stable)
- Bed capacity vs. actual utilization

**Use Case:** Hospital executives, operations leaders, capacity planning

```sql
SELECT * FROM vw_hospital_status
-- Hospital-wide view: occupancy, acuity mix, staffing needs
```

## Bed Assignment Algorithm

When a patient is admitted:

1. **Determine bed type preference** based on:
   - Primary diagnosis severity
   - Age (very young/old = higher acuity)
   - Estimated length of stay
   - Hospital specialty context

2. **Select appropriate floor**:
   - Critical patients → ICU/Critical Care floors
   - Post-op patients → Recovery floors
   - General admissions → Medical/Surgical floors
   - Specialty patients → Specialty floors (Cardiology, Oncology, etc.)

3. **Room preference**:
   - Critical care patients → Single rooms (isolation, monitoring)
   - Rehab patients → Single or double rooms
   - General patients → Shared rooms (cost efficient)

4. **Assign first available bed** matching criteria

## Integration with Encounters & Admissions

When an encounter results in an admission:
1. Create admission record (`admissions` table)
2. Select appropriate bed using algorithm above
3. Create patient_bed_assignment record
4. Update bed status to "Occupied"
5. Calculate initial clinical status

When a patient is discharged:
1. Set `discharge_datetime` on admission
2. Set `discharged_datetime` on patient_bed_assignment
3. Update bed status to "Available"

## Queries for Common Use Cases

### Find available beds on a specific floor
```sql
SELECT * FROM beds 
WHERE hospital_id = 1 AND floor_number = 3 AND status = 'Available'
ORDER BY room_id, bed_position
```

### Get floor occupancy report
```sql
SELECT * FROM vw_floor_occupancy 
WHERE hospital_id = 1 
ORDER BY floor_number
```

### Find all critical patients
```sql
SELECT 
    patient_name, 
    department, 
    clinical_status, 
    diagnosis_name, 
    doctor_name 
FROM vw_patient_location 
WHERE clinical_status = 'Critical'
ORDER BY hospital_id, los_days DESC
```

### Patient location lookup
```sql
SELECT 
    patient_name, 
    hospital_name, 
    department, 
    room_number, 
    bed_position,
    clinical_status,
    los_days
FROM vw_patient_location 
WHERE patient_name LIKE '%Smith%'
```

### Floor census by status
```sql
SELECT 
    hospital_name,
    floor_number,
    department,
    critical_count,
    unstable_count,
    improving_count,
    stable_count,
    CAST(occupancy_pct AS FLOAT) AS occupancy_pct
FROM vw_floor_occupancy
WHERE hospital_id = 2
ORDER BY floor_number
```

## Performance Considerations

- **Indexes**: Patient_bed_assignments should be indexed on (discharged_datetime, hospital_id, floor_number) for fast filtering of active admissions
- **Partitioning**: For very large hospitals, consider partitioning beds by hospital_id for faster queries
- **Caching**: Floor plans change slowly (only on admission/discharge), suitable for caching at application layer

## Future Enhancements

1. **Bed maintenance tracking**: Schedule preventive maintenance, track bed cleaning times
2. **Admission requests**: Queue of patients waiting for specific bed types (ICU vs. general)
3. **Transfer history**: Track patient movement between floors/rooms during stay
4. **Bed turnover time**: Calculate time between discharge and next admission (cleaning time)
5. **Capacity forecasting**: Predict bed needs based on admission patterns, seasonality
6. **Patient preferences**: Track patient room preferences (single vs. shared, floor location, etc.)
