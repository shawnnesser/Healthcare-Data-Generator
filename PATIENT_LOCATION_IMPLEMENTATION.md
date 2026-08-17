# Patient Location System - Implementation Summary

## What Was Created

You now have a complete **Patient Location & Floor Management System** that provides real-time patient tracking with clinical status and comprehensive floor plans for your healthcare data generator.

## 📦 New Components

### 1. **New Helper Functions** (`hospital_generation_helpers.py`)
Added 5 major helper functions:

- **`get_floors_for_hospital()`** - Creates hospital-specific floor configurations
  - General hospitals: ED + ICU + Med/Surg + Specialty
  - Specialty hospitals: Department-specific floors (Cardiac, Pediatric, Oncology, Rehab)
  - Automatically sized based on hospital bed count

- **`get_room_types_by_floor()`** - Determines room mix (single/double/quad beds)
  - Critical care: 90% single rooms (monitoring)
  - Rehab: 60% single, 40% double
  - Medical/Surgical: 30% single, 70% shared (cost efficient)

- **`get_patient_clinical_status()`** - Calculates patient status based on:
  - Diagnosis severity
  - Length of stay progression  
  - Hospital specialty
  - Age factors
  - Returns: Critical | Unstable | Post-Op | Recovering | Improving | Stable

- **`assign_patient_to_bed()`** - Smart bed selection algorithm
  - Critical patients → Critical care beds
  - Post-op patients → Recovery beds
  - General patients → Medical/Surgical beds
  - Age/acuity considerations

### 2. **Floor Management Module** (`floor_management.py`)
New Python module with complete floor/bed infrastructure:

- **`create_floors_for_hospitals()`** - One-time setup: creates all floors for all hospitals
- **`create_rooms_and_beds()`** - Generates rooms and individual bed records
- **`assign_patient_to_hospital_bed()`** - Selects appropriate bed for a patient
- **`create_patient_bed_assignments_table()`** - Creates tracking table structure
- **`create_floor_views()`** - Creates 4 SQL views for operations

### 3. **Four New Database Tables**

#### `floors` 
```
hospital_id, floor_number, department, bed_type, capacity
Example: Hospital 1, Floor 2, "Intensive Care Unit", "Critical Care", 30 beds
```

#### `rooms`
```
room_id, hospital_id, floor_number, room_number, bed_count, room_type
Example: Room 201 has 2 beds, ICU, Double suite
```

#### `beds`
```
bed_id, room_id, hospital_id, floor_number, bed_position, bed_type, status
Example: Bed 1001, Room 201, Position 1, Critical Care, Occupied
```

#### `patient_bed_assignments`
```
assignment_id, admission_id, patient_id, hospital_id, bed_id, 
floor_number, room_number, bed_position, 
assigned_datetime, discharged_datetime, 
patient_status, diagnosis_code, los_days
```

### 4. **Four New SQL Views**

#### `vw_floor_plan` - Floor visualization
```sql
SELECT * FROM vw_floor_plan WHERE hospital_id = 1 AND floor_number = 2
-- Shows: every bed, occupancy status, patient name, diagnosis, clinical status
-- Result: Visual floor plan with bed-level detail
```

#### `vw_patient_location` - Patient lookup
```sql
SELECT * FROM vw_patient_location WHERE clinical_status = 'Critical'
-- Shows: patient location + demographics + clinical info + doctor + payer
-- Result: Comprehensive patient view for care coordination
```

#### `vw_floor_occupancy` - Floor summary
```sql
SELECT * FROM vw_floor_occupancy WHERE occupancy_pct > '85%'
-- Shows: beds occupied/available, occupancy %, patient counts by status
-- Result: Floor-level operational metrics
```

#### `vw_hospital_status` - Hospital dashboard
```sql
SELECT * FROM vw_hospital_status
-- Shows: hospital-wide occupancy, bed availability, acuity mix
-- Result: Executive-level occupancy overview
```

## 📚 Documentation Files Created

1. **PATIENT_LOCATION_SYSTEM.md** (6+ pages)
   - Complete technical documentation
   - Schema descriptions with examples
   - Bed assignment algorithm details
   - 20+ sample SQL queries
   - Performance considerations
   - Future enhancement ideas

2. **PATIENT_LOCATION_QUICKSTART.md** 
   - Quick reference guide
   - Essential SQL queries
   - Common use cases
   - Workflow examples (morning check, executive dashboard)

## 🔌 How to Integrate

### Option 1: One-Time Setup (Recommended for Existing Data)
```python
# After your initial data generation, run this once:
from floor_management import create_floors_for_hospitals, create_rooms_and_beds, create_floor_views
from src.main import get_engine, HOSPITALS

engine = get_engine()

# Create floor structure
hospital_floors = create_floors_for_hospitals(engine, HOSPITALS)

# Create rooms and beds
available_beds_df = create_rooms_and_beds(engine, hospital_floors)

# Create views for queries
create_floor_views(engine)
```

### Option 2: Integrate Into Main Generation (Future Approach)
In `main.py`, during rebuild:
```python
# After creating hospitals table:
hospital_floors = create_floors_for_hospitals(engine, HOSPITALS)
beds_df = create_rooms_and_beds(engine, hospital_floors)

# When creating admissions:
bed_assignment = assign_patient_to_hospital_bed(
    diagnosis_code=diagnosis_code,
    patient_age=patient_age,
    los_days=los_days,
    hospital_specialty=hospital_specialty,
    hospital_id=hospital_id,
    available_beds_df=beds_df
)

if bed_assignment:
    bed_id, floor_num, room_num, bed_pos = bed_assignment
    # Create patient_bed_assignment record
    # Update bed status to 'Occupied'
```

## 🎯 Key Design Decisions

### 1. **Hybrid Floor Organization**
- Floors identified by **floor_number + department** (not just number)
- Allows realistic floor names: "ICU Floor 2", "Cardiac Unit 3", "Pediatric Ward 1"
- Makes querying and visualization more intuitive

### 2. **Room-Based Bed Structure**
- Rooms contain 1, 2, or 4 beds (realistic hospital layouts)
- Single beds: critical care, isolation needs
- Double beds: step-down care, standard care with privacy
- Quad beds: general medical/surgical units (cost efficient)

### 3. **Clinical Status Calculation**
- **Automatic**: Based on diagnosis + LOS, not manual entry
- **Progressive**: Unstable → Improving → Stable as days increase
- **Context-aware**: Cardiac/cancer patients start higher acuity
- **Evidence-based**: Critical diagnoses from real ICD codes

### 4. **Smart Bed Assignment**
- **Specialty-matched**: General hospitals have all types; specialty hospitals have specialized beds
- **Age-aware**: Very young/old patients → higher monitoring
- **Acuity-driven**: Critical diagnoses → critical beds
- **Fallback logic**: Uses any available bed if preferred type full

## 📊 Data Visible for Each Patient

When you query `vw_patient_location`, you can see:

**Patient Info**
- Name, Age, DOB
- Insurance, Payer type

**Location**
- Hospital name
- Floor number + Department name
- Room number
- Bed position

**Clinical**
- Primary diagnosis (ICD code + name)
- Chief complaint
- Clinical status
- Length of stay (days)

**Care Team**
- Attending doctor name & specialty
- Insurance plan

**Timeline**
- Admission datetime
- (Discharge datetime once discharged)

## 🚀 Getting Started

### Step 1: Review Documentation
- Read [PATIENT_LOCATION_SYSTEM.md](PATIENT_LOCATION_SYSTEM.md) for technical details
- Read [PATIENT_LOCATION_QUICKSTART.md](PATIENT_LOCATION_QUICKSTART.md) for quick reference

### Step 2: Try Sample Queries
```sql
-- View your hospital network structure
SELECT hospital_name, floor_number, department, bed_type, capacity 
FROM floors
ORDER BY hospital_name, floor_number

-- See all current patients
SELECT * FROM vw_patient_location

-- Get occupancy report
SELECT * FROM vw_floor_occupancy

-- Hospital dashboard
SELECT * FROM vw_hospital_status
```

### Step 3: Build Dashboards
With the views available, you can now build:
- **Nurse station displays** (vw_patient_location)
- **Bed coordinator tools** (vw_floor_plan)
- **Operations dashboards** (vw_floor_occupancy)
- **Executive reports** (vw_hospital_status)

## ⚙️ Configuration Options

The system automatically configures floors based on hospital specialty:

| Specialty | Floor 1 | Floor 2 | Floor 3 | Floor 4+ |
|-----------|---------|---------|---------|----------|
| **General** | ED (6%) | ICU (8%) | Med/Surg | Specialty |
| **Cardiac** | Cardiac ICU | Cardiology | Cardiology | Cath Lab |
| **Pediatric** | Ped ED (8%) | PICU (12%) | Ped Ward | Ped Ward |
| **Cancer** | Onc ICU (20%) | Oncology | Oncology | BMT |
| **Rehab** | Intensive | Post-Surg | Specialty | - |

## 🔍 Example Use Cases

### 1. **Morning Nurse Shift**
```sql
-- Who are my patients on Floor 3 today?
SELECT patient_name, room_number, bed_position, clinical_status 
FROM vw_patient_location 
WHERE floor_number = 3 
ORDER BY clinical_status DESC, room_number
```

### 2. **Bed Coordinator**
```sql
-- Where are my available beds?
SELECT hospital_name, floor_number, room_number, bed_position 
FROM vw_floor_plan 
WHERE bed_status = 'Available'
LIMIT 20
```

### 3. **Operations Leader**
```sql
-- Hospital-wide occupancy
SELECT * FROM vw_hospital_status
-- Check: occupancy %, critical patient count, capacity alerts
```

### 4. **Quality Improvement**
```sql
-- Patients staying >7 days
SELECT patient_name, los_days, clinical_status, hospital_name, diagnosis_name
FROM vw_patient_location
WHERE los_days > 7
ORDER BY los_days DESC
```

## 📈 Future Integration Opportunities

1. **Patient Transfers**: Add `patient_transfers` table to track movement between beds/floors
2. **Bed Maintenance**: Track cleaning time, maintenance, status changes
3. **Admission Queue**: Track patients waiting for specific bed types
4. **Forecasting**: Predict bed demand based on admission patterns + seasonality
5. **KPI Dashboards**: Build on views for occupancy trending, LOS analysis, acuity mix reporting

## ❓ Questions?

See documentation files:
- **Technical details**: PATIENT_LOCATION_SYSTEM.md
- **Quick reference**: PATIENT_LOCATION_QUICKSTART.md
- **Integration**: This file (PATIENT_LOCATION_IMPLEMENTATION.md)
