# Patient Location System - Quick Start Guide

## What Was Created

### 4 New Database Tables
1. **`floors`** - Hospital floors/units with capacity and department info
2. **`rooms`** - Individual rooms on each floor (single, double, quad)
3. **`beds`** - Individual bed tracking with occupancy status
4. **`patient_bed_assignments`** - Current patient locations with clinical status

### 4 New SQL Views
1. **`vw_floor_plan`** - Complete floor visualization with occupancy
2. **`vw_patient_location`** - Patient-centric view with full clinical info
3. **`vw_floor_occupancy`** - Floor summary (beds, occupancy %, patient counts)
4. **`vw_hospital_status`** - Hospital-wide occupancy dashboard

### Floor Organization Logic
- **General hospitals**: ED + ICU + Med/Surg + Specialty
- **Cardiac hospitals**: Cardiac ICU + Cardiology units + Cath recovery
- **Pediatric hospitals**: Ped ED + PICU + Pediatric wards
- **Cancer centers**: Onc ICU + Oncology units + BMT
- **Rehab centers**: Intensive rehab + Post-surgical + Specialty

### Room Mix
- **Critical Care**: 90% single rooms, 10% double (monitoring)
- **Rehab**: 60% single, 40% double
- **Medical/Surgical**: 30% single, 70% shared (cost efficient)

### Patient Status Tracking
Automatically determined based on:
- Diagnosis severity (Critical codes: ACS, sepsis, stroke, etc.)
- Length of stay progression
- Hospital specialty context
- Age factors

**Status Types**: `Critical | Unstable | Post-Op | Recovering | Improving | Stable`

## Quick SQL Queries

### See All Patients Currently in Hospital
```sql
SELECT 
    patient_name, 
    hospital_name, 
    department, 
    room_number, 
    bed_position,
    clinical_status,
    diagnosis_name,
    doctor_name,
    los_days
FROM vw_patient_location
ORDER BY hospital_name, department
```

### Find Available Beds on a Specific Floor
```sql
SELECT 
    hospital_name,
    floor_number,
    room_number,
    bed_position
FROM vw_floor_plan 
WHERE hospital_id = 1 AND floor_number = 2 AND bed_status = 'Available'
```

### Get Floor Occupancy Report
```sql
SELECT 
    hospital_name,
    floor_number,
    department,
    occupancy_pct,
    critical_patients,
    unstable_patients,
    improving_patients,
    stable_patients
FROM vw_floor_occupancy
ORDER BY hospital_name, floor_number
```

### Find All Critical Patients
```sql
SELECT 
    patient_name, 
    hospital_name,
    department, 
    clinical_status, 
    diagnosis_name, 
    doctor_name,
    los_days
FROM vw_patient_location 
WHERE clinical_status = 'Critical'
ORDER BY hospital_name
```

### Hospital-Wide Occupancy Dashboard
```sql
SELECT * FROM vw_hospital_status
```

### Patient Lookup by Name
```sql
SELECT 
    patient_name,
    age,
    hospital_name,
    department,
    room_number,
    bed_position,
    clinical_status,
    los_days,
    doctor_name,
    payer_type
FROM vw_patient_location
WHERE patient_name LIKE '%Smith%'
```

### Find Overcrowded Floors
```sql
SELECT 
    hospital_name,
    floor_number,
    department,
    occupancy_pct,
    occupied_beds,
    capacity
FROM vw_floor_occupancy
WHERE CAST(REPLACE(occupancy_pct, '%', '') AS FLOAT) > 80
ORDER BY occupancy_pct DESC
```

## Data Visible for Each Patient

When you query `vw_patient_location`, you get:

**Demographics**
- Patient ID, Name, DOB, Age
- Hospital, Floor, Room, Bed

**Clinical**
- Diagnosis code and description
- Chief complaint
- Clinical status (Critical/Stable/etc.)
- Length of stay
- Admission datetime

**Provider Info**
- Doctor name and specialty
- Payer type and insurance plan

## Next Steps to Integrate

To fully integrate this into your data generation pipeline, you'll need to:

1. **Run floor setup** (one-time per hospital):
   ```bash
   python -c "from floor_management import *; from src.main import get_engine; from src.config import HOSPITALS; setup_floors(get_engine(), HOSPITALS)"
   ```

2. **When admitting a patient**, assign them to a bed:
   - Query available beds in hospital
   - Use clinical criteria to select appropriate floor/room type
   - Create patient_bed_assignment record
   - Update bed status to 'Occupied'

3. **When discharging a patient**:
   - Set discharge_datetime
   - Update bed status to 'Available'

4. **Dashboard integration**:
   - Build dashboards on top of the views
   - Use vw_hospital_status for high-level occupancy
   - Use vw_floor_occupancy for floor managers
   - Use vw_patient_location for nurse stations

## Example: Daily Workflow

**Morning Nurse Station Check:**
```sql
-- What's the status on my floor?
SELECT * FROM vw_floor_occupancy WHERE floor_number = 3

-- Who are my critical patients?
SELECT * FROM vw_patient_location 
WHERE floor_number = 3 AND clinical_status IN ('Critical', 'Unstable')

-- Who's being discharged today?
SELECT patient_name, discharge_datetime FROM vw_patient_location
WHERE floor_number = 3 AND los_days > 5
```

**Bed Coordinator Check:**
```sql
-- Where are my available beds?
SELECT * FROM vw_floor_plan WHERE bed_status = 'Available'

-- What's our occupancy?
SELECT * FROM vw_hospital_status

-- Which floors have capacity?
SELECT * FROM vw_floor_occupancy WHERE available_beds > 0
```

**Executive Dashboard:**
```sql
-- Hospital-wide view
SELECT * FROM vw_hospital_status

-- Acuity breakdown
SELECT hospital_name, critical_count, unstable_count, improving_count, stable_count 
FROM vw_hospital_status

-- Trends
-- (can be extended with daily snapshots for trend analysis)
```

## Files Created

- **PATIENT_LOCATION_SYSTEM.md** - Detailed technical documentation
- **floor_management.py** - All floor/bed management functions
- **hospital_generation_helpers.py** - Extended with floor/bed helper functions

## Questions?

See PATIENT_LOCATION_SYSTEM.md for detailed documentation including:
- Complete schema descriptions
- Bed assignment algorithm details
- Performance considerations
- Future enhancement ideas
