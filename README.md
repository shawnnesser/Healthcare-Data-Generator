# Healthcare Data Generator

A sophisticated synthetic healthcare data generation system that creates realistic hospital encounter, admission, and operational data with advanced seasonality patterns, weather integration, and occupancy tracking. This tool is designed for testing analytics pipelines, healthcare dashboards, and data engineering workflows without requiring real patient data.

---

## Quick Start (for LLMs and Automated Agents)

```bash
# 1. Clone
git clone https://github.com/shawnnesser/Healthcare-Data-Generator.git
cd Healthcare-Data-Generator

# 2. Create virtual environment & install
python -m venv .venv
# Windows: .venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure connection (pick ONE method)
#    Option A — .env file (recommended):
cp .env.example .env
#    Edit .env and set CONNECTION_STRING to a URL-encoded ODBC string.
#    Option B — environment variable:
#    export CONNECTION_STRING="Driver%3D%7BODBC+Driver+18+for+SQL+Server%7D%3B..."
#    Option C — no database (Parquet export only, no connection needed):
python src/main.py --export-parquet

# 4. Run
python src/main.py                          # incremental: generate today's data
python src/main.py --rebuild-start 2025-01-01  # full rebuild: 2025-01-01 → today
python src/main.py --export-parquet            # export to data/*.parquet (no DB)
```

**Key files an agent needs to know about:**
| File | Purpose |
|------|---------|
| `src/main.py` | Entry point — all CLI flags defined here |
| `src/config.py` | Reads `CONNECTION_STRING` from env / `.env` / `src/config_local.py` |
| `.env.example` | Template for connection string (copy to `.env`) |
| `src/config_local.py` | Alternative local config override (gitignored) |
| `requirements.txt` | Python dependencies |

---

## Overview

The Healthcare Data Generator produces multi-table healthcare datasets covering:

- **Patient Demographics & Medical History**: Patient records with synthetic personal identifiers and insurance information
- **Hospital Operations**: Hospital bed inventory, department-level bed allocation (including ER surge capacity based on hospital size)
- **Clinical Encounters**: ED encounters, visits, and admissions with realistic temporal patterns
- **Admissions & Occupancy**: Full admission/discharge tracking for precise bed occupancy calculations
- **Clinical Data**: Procedures, diagnoses, medications, labs, and billing records
- **Temporal Dimensions**: Date dimension table with full gregorian and fiscal calendars
- **Environmental Context**: Weather integration from historical data (2025-01-01 onwards), affecting disease patterns (flu, falls)
- **Hospital Specialization**: Multi-specialty hospital system with realistic admission rates, diagnosis routing, and seasonality variance by hospital type

### Key Features

#### 🏥 **Hospital Specialization System** ⭐ NEW
Realistic hospital types with specialty-specific behaviors:

- **General Hospitals** (5 hospitals): Full-service ED, 20% admission rate, blended seasonal patterns
  - Specialties: Trauma, internal medicine, general surgery, psychiatry, OB/GYN
  - Seasonal variance: Jan/Dec peaks (+12% to +18%), Jul trough (-10%)
  
- **Cardiac Specialty Institute** (1 hospital): Cardiology-focused, 72% admission rate
  - Dominant diagnoses: Acute coronary syndrome (28%), heart failure (22%), arrhythmia (18%)
  - **CRITICAL PATTERN**: Winter ACS surge (Jan +38% vs. Jul)
  - Admission timing: Early morning peaks (35% 6–10am)
  - **NO Emergency Department** — emergencies route through general hospital then transfer
  - Payer mix: Medicare 45%, Commercial 40% (older cardiac patient population)
  
- **Pediatric Children's Hospital** (1 hospital): Pediatric specialty, 12% admission rate
  - Dominant diagnoses: URI (22%), otitis media (18%), asthma (12%), fractures (15%)
  - Seasonal pattern: Winter respiratory peaks (Jan +35% vs. Jul)
  - Admission timing: Distributed throughout day (8–10am, 2–4pm, 6–9pm peaks)
  - Urgent care facility (24/7 but lower night volumes)
  - Payer mix: Medicaid 52%, Commercial 35% (pediatric population)
  
- **Cancer Center** (1 hospital): Oncology/hematology, 96% admission rate (highest)
  - Dominant diagnoses: Febrile neutropenia (22%), infection/sepsis (20%), acute leukemia (18%)
  - Seasonal pattern: Stable ±6% (scheduled treatments dominate)
  - Admission timing: Business-hours focused (70% 8am–5pm scheduled, 30% emergency overnight)
  - Average LOS: 7.4 days (longest)
  - **NO Emergency Department** — direct admissions from oncology practices
  
- **Rehabilitation Center** (1 hospital): Post-acute care, 85% admission rate
  - Patient mix: Orthopedic post-op (35%), stroke recovery (25%), cardiac rehab (15%)
  - Seasonal pattern: Spring/fall peaks (Mar/Apr/Oct +10%, Jul -8%)
  - Admission timing: Early morning discharge transfers (60% 7–9am)
  - Average LOS: 21 days (longest due to rehabilitation focus)
  - **NOT AN ED** — physician referrals only, 7am–5pm admission hours
  
- **Specialty Diagnostic Center** (1 hospital): Imaging/labs only
  - Radiology, pathology, laboratory services
  - Business hours only (8am–5pm)
  - No ED, no admissions

**Hospital-Specific Monthly Seasonality:**

| Month | Pediatric | Cardiac | Cancer | General | Rehab |
|-------|-----------|---------|--------|---------|-------|
| **Jan** | **+35%** | **+38%** | 5% | +12% | 4% |
| **Feb** | **+28%** | **+32%** | 3% | +8% | 2% |
| **Jul** | **-25%** | **-27%** | -6% | -10% | **-8%** |
| **Oct** | -1% | -2% | 2% | 0% | **+12%** ⬆ Peak |
| **Dec** | **+26%** | **+28%** | 6% | **+18%** | 0% |

**Impact on Leadership Analytics:**
- January: Pediatric ED surge +35% (flu/RSV), cardiac ICU at 92–96% occupancy
- July: Pediatric hospitals -25% (summer dip), reduced surgical schedules system-wide
- October: Rehab centers +12% (post-surgical recovery season)
- Friday 2–6pm: ER occupancy 93–95% across general hospitals (bypass risk)

#### 📊 **ER Bed Occupancy Stress Modeling** ⭐ NEW
Realistic hourly ER occupancy patterns with day-of-week variance:

- **Hourly Baseline**: 38% occupancy at 4am (minimum) → 89% at 2pm (peak) = 2.3x range
- **Day-of-Week Multipliers**:
  - **Friday 2–6pm: 93–95% occupancy** (weekend elective surge, trauma spike) 🔴 CRITICAL
  - Monday–Thursday morning: 75–88% occupancy
  - Sunday 4am: 36–40% occupancy (admin opportunity for elective admissions)
  
- **Operational Insights**:
  - Friday 2–6pm shows occupancy approaching bypass thresholds
  - Early morning (midnight–6am) shows 50% empty beds (ideal for patient transfers/admissions)
  - Monday spike (92% occupancy) from weekend backlog

#### 📋 **Hospital Encounter Volume Variation** ⭐ NEW
Realistic hospital-to-hospital encounter volume differences:

- **Bed Count-Based Distribution**: Larger hospitals generate proportionally more encounters
  - 750-bed hospital: ~45-65 encounters/day
  - 350-bed hospital: ~20-35 encounters/day
  - 120-bed hospital: ~7-15 encounters/day
  
- **Random Variation (15-30%)**: Each hospital's daily volume varies realistically
  - Reflects real-world fluctuations in patient arrivals
  - Prevents unrealistic uniform distribution across all hospitals
  
- **Department-Weighted Assignments**: Encounters assigned to departments by realistic demand
  - Emergency departments: 2.5x higher patient volume
  - Internal Medicine: 1.8x
  - Specialty services: Lower multipliers

#### 💳 **Payer Mix Realism** ⭐ NEW
Every encounter assigned a payer type based on hospital specialty and patient demographics:

- **Overall Market Share**:
  - Medicare: 36%
  - Commercial: 35%
  - Medicaid: 20%
  - Uninsured: 5%
  - Other: 4%
  
- **Specialty Adjustments**:
  - Pediatric hospitals: Medicaid 52%, Commercial 35%
  - Cardiac hospitals: Medicare 45%, Commercial 40%
  - Rehab centers: Medicare 50% (post-acute population)
  - General hospitals: Standard mix

#### 📚 **Complete ICD-10 Documentation** ⭐ NEW
All 39 ICD-10 codes include full clinical descriptions and realistic chief complaints:

- **Example Diagnoses**:
  - `I10`: "Essential (primary) hypertension" - Headache, Dizziness
  - `J18.9`: "Pneumonia, unspecified organism" - Fever, Cough, Shortness of breath
  - `I63.9`: "Cerebral infarction, unspecified (Ischemic stroke)" - Sudden weakness, Slurred speech
  - `A41.9`: "Sepsis, unspecified organism" - Fever, Hypotension, Altered mental status
  
- Enables realistic encounter notes and chief complaint generation
- Supports accurate diagnosis-to-treatment mapping

#### 📋 **Data-Driven Recommendations for Hospital Leaders** ⭐ NEW
The generated data reveals realistic operational challenges requiring action:

**Issue 1: Winter Pediatric ED Overcrowding**
- Pattern: January encounters +35% vs. July baseline
- Root cause: Flu/RSV season (CDC NHAMCS data)
- Action: Hire 3–4 temp RNs Oct–Feb; implement flu shot campaign; expand fast-track lane
- Expected ROI: ED wait times ↓ 50% (4hr → 2hr)

**Issue 2: Cardiac Institute Early-Morning Capacity Crisis**
- Pattern: January +38% encounters; 8–10am occupancy 94–96% on weekdays
- Root cause: ACS (acute coronary syndrome) diurnal peak + winter surge
- Action: Open 6am ICU overflow; extend cath lab 7am–7pm (not 9am–5pm); reduce elective 6am–12pm
- Expected ROI: ACS door-to-cath <120 min consistently

**Issue 3: General Hospital Friday ER Bypass Risk**
- Pattern: Friday 2–6pm occupancy 93–95% (vs. 75–80% Sun–Thu)
- Root cause: Elective surgery discharges Friday PM; trauma spike; weekend staffing prep
- Action: Discharge all stable admits by 10am Friday; block elective admits 1pm–6pm; activate weekend staff
- Expected ROI: Bypass activation <2/month (vs. current 4–6/month)

**Issue 4: Rehab Center April Bottleneck**
- Pattern: April admissions +10% (spring surgical season); morning discharge transfers spike
- Root cause: Post-surgical rehab referral season
- Action: Hire temp PT/OT staff; pre-plan discharge referrals; schedule early hospital discharges (6am not noon)
- Expected ROI: Hospital-to-rehab transfer time ↓ 25% (72hr → 48hr); reduce bed-blocking

**Issue 5: Cancer Center Overnight Chemo Toxicity**
- Pattern: 5% of admissions midnight–8am; 20%+ febrile neutropenia
- Root cause: Chemotherapy side effects peak 12–36hrs post-infusion
- Action: On-call oncology triage nurse 6pm–6am; fast-admit protocol for fever >100.4°F; hold 3–5 beds 8pm–8am
- Expected ROI: Febrile neutropenia admission <2hr (vs. 4–6hr); reduce sepsis mortality

**Comprehensive Report:**
See [HOSPITAL_SEASONALITY_AND_OCCUPANCY_ANALYSIS.md](HOSPITAL_SEASONALITY_AND_OCCUPANCY_ANALYSIS.md) for:
- Full monthly variance tables by specialty
- Admission rates, LOS distributions, admission timing patterns
- ER occupancy heat maps (hourly × day-of-week)
- 7 operational recommendations with citations (CDC, AHA, NIH, NCI, APTA, ACEP)

#### 🌡️ Real Weather Integration
- Fetches historical weather data from **Open-Meteo API** (free, no API key required)
- Weather conditions mapped to healthcare impact (rain/snow → increased falls, cold → flu surge)
- Per-date weather application during bulk generation (not just today's weather)
- In-memory caching + JSON file persistence to avoid repeated API calls
- Cache cleared on demand via CLI flag

#### 📅 Comprehensive Date Dimension
- Full temporal coverage (398 days: 2025-01-01 → 2026-02-02)
- All standard calendar columns: gregorian (yyyy/mm/dd/day_of_week) and fiscal calendars
- Day-of-week, quarter, ISO week, week-of-year, day-of-year, fiscal-month tracking
- Supports complex temporal queries and rollups

#### 🏥 Realistic Hospital Structure
- Configurable hospital count (default: 10 hospitals across large/medium/small tiers)
- **Realistic Department Bed Allocation**: Evidence-based percentages by department type:
  - **Emergency: 6%** (45 ER beds in 750-bed hospital, not 300+)
  - Internal Medicine: 35% (largest inpatient service)
  - Surgery: 25% (surgical floors)
  - Specialty departments: 10-20% (cardiology, orthopedics, etc.)
  - Outpatient services: 3-5% (radiology, pathology)
- Department-level bed counts that sum exactly to hospital totals (no overcounting or waste)
- **Department Demand Multipliers**: Realistic patient volume distribution
  - Emergency: 2.5x (highest volume)
  - Internal Medicine: 1.8x
  - Radiology: 1.9x (high imaging demand)
  - Palliative Care: 0.6x (specialty, lower volume)
- Emergency departments for general hospitals with proper 6% bed allocation
- Views for real-time ER and patient occupancy tracking

#### 📊 Seasonality Multipliers (Evidence-Based)
Applied across three dimensions for realistic temporal variation:

- **Hourly Multipliers** (24 values: 0.43–1.52)
  - ED peaks in afternoon/evening (1.4–1.52 at 16:00–20:00)
  - Troughs at 03:00–05:00 (0.43–0.51)
  - Based on NHS A&E and NHAMCS (CDC) data
  - *Sources: NHS A&E attendances, NHAMCS National Hospital Ambulatory Medical Care Survey*

- **Day-of-Week Multipliers** (7 values: 0.96–1.06)
  - Monday surge (1.06) from primary-care backlog
  - Midweek dip (0.96–0.98) as backlog clears
  - Weekend elevation (1.01–1.03) as primary care closed
  - *Sources: NHS operational data, NHAMCS seasonal patterns*

- **Monthly Multipliers** (12 values: 0.85–1.12)
  - Winter peaks (Jan/Feb/Dec: 1.08–1.12) - flu, respiratory, cardiac events
  - Summer dip (Jul: 0.85) - fewer acute presentations
  - Spring/Fall transitional (0.95–1.02)
  - *Sources: CDC FluVax influenza season tracking, NHS A&E seasonal variation*

- **Procedure Seasonality** (11 procedures, PMC-sourced)
  - **Cardiac Catheterization**: 1.15 (winter cardiac events) → 0.92 (summer)
  - **Appendectomy**: 1.10 (summer surgical spike) → 0.95 (winter)
  - **Colonoscopy**: 0.95 (winter dip) → 1.05 (summer screening)
  - **Bypass Surgery**: 1.18 (winter ACS) → 0.88 (summer)
  - **Angioplasty**: 1.12 (winter ACS) → 0.90 (summer)
  - **Hysterectomy**: 1.02 (summer elective) → 0.98 (winter)
  - **Knee Replacement**: 1.08 (summer post-sports-season) → 0.94 (winter)
  - **Hip Replacement**: 1.05 (summer fall-prevention rush) → 0.98 (winter)
  - **Appendix Removal**: 1.10 (summer) → 0.92 (winter)
  - **Gallbladder Removal**: 1.03 (summer) → 0.99 (winter)
  - **Hernia Repair**: 1.04 (summer) → 0.97 (winter)
  - *Sources: PMC surgical seasonality studies, NHS elective scheduling patterns*

#### 👥 Admissions & Occupancy Tracking
- Full admission/discharge workflow with admit_datetime and discharge_datetime
- Hospital-specific admission rates: Pediatric 12%, Cardiac 72%, Cancer 96%, General 20%, Rehab 85%
- **Specialty-appropriate admission timing**:
  - Cardiac: 35% of admissions 6–10am (early-morning ACS peak)
  - Pediatric: Distributed (morning, afternoon, evening peaks)
  - Cancer: 70% 8am–5pm (scheduled chemo management), 30% emergency overnight
  - Rehab: 60% 7–9am (discharge transfers from acute care)
  - General: 40% 2–6pm (ED afternoon peak)
- **Specialty-specific length of stay** (with ±30% variance):
  - Pediatric: 1.2 days avg
  - Cardiac: 3.5 days avg  
  - Cancer: 7.4 days avg
  - Rehab: 21 days avg (longest)
  - General: 3.8 days avg
- 50% discharge within 0–7 days; 50% ongoing stays (discharge_datetime = NULL)
- Enables precise bed occupancy calculations via SQL view
- Supports capacity planning and length-of-stay analytics


#### 🗄️ Database Schema
All tables include explicit IDs with collision-free offset logic:

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `date_dim` | Temporal reference | date, yyyy, mm, dd, day_of_week, is_weekend, fiscal_month, iso_week |
| `hospitals` | Hospital master data | hospital_id, hospital_name, bed_count, city, state |
| `departments` | Operational units | department_id, department_name, hospital_id, specialty_type |
| `hospital_department_beds` | Bed allocation | hospital_id, department_id, bed_count |
| `patients` | Patient demographics | patient_id, first_name, last_name, dob, gender, address, insurance_id |
| `doctors` | Clinical staff | doctor_id, first_name, last_name, specialty |
| `encounters` | ED visits/admissions | encounter_id, patient_id, hospital_id, department_id, doctor_id, encounter_date, payer_type, chief_complaint |
| `admissions` | Admission records | admission_id, encounter_id, hospital_id, patient_id, admit_datetime, discharge_datetime |
| `procedures` | Surgical/clinical procedures | procedure_id, hospital_id, encounter_id, procedure_name, procedure_date |
| `diagnoses` | ICD codes linked to encounters | diagnosis_id, encounter_id, diagnosis_code, diagnosis_name |
| `medications` | Prescriptions | medication_id, encounter_id, medication_name, dosage |
| `labs` | Lab results | lab_id, encounter_id, lab_name, result, normal_range |
| `insurance` | Insurance master data | insurance_id, company_name, plan_name, copay |
| `billing` | Charges & billing records | billing_id, encounter_id, amount, service_type |
| `run_logs` | Audit trail | run_id, run_date, records_inserted, duration_seconds |

#### 📊 SQL Views
- **`vw_current_er_beds`**: Real-time ER bed availability by hospital
  - Shows available, occupied, and total beds per ED
  - Scoped to department_type='Emergency'
  
- **`vw_current_patient_beds`**: Real-time patient occupancy across all beds
  - Calculates occupancy from `admissions` table (admit_datetime ≤ today AND discharge_datetime IS NULL OR > today)
  - Supports capacity planning and overflow detection

#### ✅ Catch-Up Mechanism
- Detects if app hasn't run in >24 hours
- Automatically backfills missing days from last run_log to today
- Applies seasonality and weather to all catch-up dates

## Installation

### Prerequisites
- Python 3.8+
- ODBC Driver 18 for SQL Server (required for database modes; not needed for `--export-parquet`)
- A SQL Server, Azure SQL, or Microsoft Fabric SQL database (optional — Parquet export works without one)

### Setup

1. **Clone and navigate to project**:
   ```bash
   git clone https://github.com/shawnnesser/Healthcare-Data-Generator.git
   cd Healthcare-Data-Generator
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS / Linux
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure database connection** (choose one):

   **Option A — `.env` file (recommended)**:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set `CONNECTION_STRING` to a **URL-encoded** ODBC connection string.  
   See `.env.example` for format examples.

   **Option B — `src/config_local.py`**:
   ```python
   # src/config_local.py  (this file is gitignored)
   import urllib.parse
   CONN_ODBC = (
       "Driver={ODBC Driver 18 for SQL Server};"
       "Server=your-server.database.fabric.microsoft.com,1433;"
       "Database=your-database;"
       "Encrypt=yes;TrustServerCertificate=no;Authentication=ActiveDirectoryInteractive"
   )
   CONNECTION_STRING = urllib.parse.quote_plus(CONN_ODBC)
   ```

   **Option C — Environment variable**:
   ```bash
   export CONNECTION_STRING="Driver%3D%7BODBC+Driver+18+for+SQL+Server%7D%3BServer%3D..."
   ```

   **Option D — No database (Parquet only)**:  
   Skip this step entirely and use `--export-parquet`.

5. **Run the generator**:
   ```bash
   python src/main.py                             # daily incremental
   python src/main.py --rebuild-start 2025-01-01   # full history rebuild
   python src/main.py --export-parquet             # export to data/*.parquet
   ```

## Usage

### Command-Line Interface

#### Default Behavior (Daily Incremental)
```bash
python src/main.py
```
- Runs once, inserting today's data
- Applies today's weather and seasonality
- If last run >24h ago, automatically backfills all missing days
- Cache is loaded on startup, saved on exit

#### Rebuild Database (Full History)
```bash
python src/main.py --rebuild-start 2025-01-01
```
- Truncates all tables
- Regenerates all data from specified start_date to today
- Applies per-date weather and seasonality
- Populates all 13 core tables
- Creates/recreates SQL views
- Generates 399 days of data (2025-01-01 → today)
- Demonstrates full dataset capability with realistic temporal variation

#### Continuous Generation (Hourly)
```bash
python src/main.py --frequency hourly
```
- Runs hourly (suitable for `cron` or task scheduler)
- Maintains continuous data stream
- Useful for real-time analytics dashboards

#### Generate Once Without Caching
```bash
python src/main.py --clear-weather-cache
```
- Clears weather cache before run
- Forces fresh API calls for all dates
- Useful for cache validation or debugging

#### Export to Parquet
```bash
python src/main.py --export-parquet
```
- Exports generated data to `output/` directory (parquet format)
- Separate file per table
- Useful for ETL integration or data lake population

#### Combine Flags
```bash
python src/main.py --rebuild-start 2025-01-01 --export-parquet --frequency daily
```

### Example Workflows

#### Scenario 1: Populate Dashboard with Historical Data
```bash
python src/main.py --rebuild-start 2025-01-01
# Wait ~2–5 minutes
# Dashboard queries `vw_current_patient_beds`, `vw_current_er_beds`, procedures by month, etc.
# All historical data now in database with realistic seasonality
```

#### Scenario 2: Continuous Testing Pipeline
```bash
# Initial setup (full history)
python src/main.py --rebuild-start 2025-01-01

# Then daily refresh (cron job at 07:00)
0 7 * * * cd /path/to/project && /usr/bin/python3 src/main.py --frequency daily
```

#### Scenario 3: Validate Cache Persistence
```bash
# First run: builds cache
python src/main.py --rebuild-start 2025-01-01
# Cache saved to weather_cache.json after successful completion

# Second run: uses cache (instant, no API calls)
python src/main.py

# Clear cache for fresh API calls
python src/main.py --clear-weather-cache --rebuild-start 2025-01-01
```

## Data Flow & Architecture

### Generation Pipeline (Rebuild Mode)

```
Input: start_date (2025-01-01), end_date (today)
  ↓
[Loop: day-by-day from start_date → end_date]
  ↓
  For each day:
    0. Get month for specialty multiplier lookup
    1. Fetch weather for that date (cached if available)
    2. [NEW] For each hospital (10 total):
         a. Get specialty-adjusted encounter count via get_hospital_monthly_encounters()
            - Pediatric: ±35% monthly variance
            - Cardiac: ±38% monthly variance
            - Cancer: ±6% monthly variance
            - General: ±18% monthly variance
            - Rehab: ±12% monthly variance
         b. Generate encounters scaled by specialty + month multiplier
         c. Route diagnoses via get_specialty_diagnoses()
            - Children's: URI, otitis, asthma, fractures
            - Heart Institute: ACS, heart failure, arrhythmia
            - Cancer Center: febrile neutropenia, acute leukemia, lymphoma
            - General: trauma, infection, surgery, psychiatry
         d. Apply specialty-appropriate admission rate (12% to 96%)
         e. Generate admission times via get_admission_times_by_specialty()
            - Cardiac: 35% early-morning peak
            - Rehab: 60% 7–9am transfer window
            - Cancer: 70% business hours
         f. Apply specialty-specific LOS (1.2 to 21 days)
    3. Generate patients (if new)
    4. Generate doctors (if new)
    5. Generate procedures (procedure name weighted by PROCEDURE_SEASONALITY + monthly multiplier)
    6. Generate medications, labs, insurance, billing records
    7. Offset all IDs to match DB state
    8. Insert data (replace on day 1, append thereafter)
    9. Advance ID counters
  ↓
[After all days]
  ↓
  Create/recreate SQL views (ER beds, patient beds)
  ↓
  Save weather cache to JSON
  ↓
Output: All tables populated with realistic hospital specialization, views ready, cache persisted
```

### Seasonality Application

```
For each encounter/procedure on date D:
  1. Get hourly multiplier (if applicable): HOURLY_MULTIPLIERS[hour_of_day]
  2. Get day-of-week multiplier: DAY_OF_WEEK_MULTIPLIERS[dow]
  3. Get monthly multiplier: MONTHLY_MULTIPLIERS[month]
  4. For procedures: apply PROCEDURE_SEASONALITY[procedure_name]
  5. Combine: combined_weight = base_weight * monthly * (day_of_week * hourly if hourly else day_of_week)
  6. Normalize weights across all procedures: sum = 1.0
  7. Select procedure via random.choices(procedures, weights=normalized)
```

### Weather Integration

```
For date D:
  1. Check weather_cache (in-memory dict or JSON file)
  2. If miss: call Open-Meteo archive API
     - Endpoint: https://archive-api.open-meteo.com/v1/archive?latitude=XX&longitude=YY&date=YYYY-MM-DD
     - Parse response: get weather_code (WMO)
     - Map code to condition: (0–1: clear, 2–3: cloudy, 45–48: fog, 51–67: drizzle/rain, 71–86: snow, 80–82: showers, 85–86: heavy snow showers)
  3. Store in cache (in-memory + JSON)
  4. Apply WEATHER_IMPACT multipliers:
     - flu_multiplier = 1.2 if (rain/snow/fog) else 1.0
     - fall_multiplier = 1.4 if (rain/snow) else 1.0
  5. Scale diagnosis generation: increase flu/fall diagnoses on bad weather
```

### Incremental Update (Non-Rebuild)

```
Input: (no date range specified)
  ↓
Check last run in run_logs:
  - If run_date is today: skip (already run)
  - If run_date < today - 1 day: detect catch-up needed
    ↓
    [For each missing day: loop back to day-by-day generation]
  ↓
Generate today's data:
  - Fetch weather for today
  - Apply today's seasonality
  - Generate encounter/patient/procedure/admission records
  - Offset IDs
  - Insert (append)
  ↓
Save weather cache
  ↓
Output: Today's data added, views updated
```

## Configuration

### Seasonality Multipliers (src/config.py)

All multipliers are tuned for mean ≈ 1.0 to avoid systematic over/under-generation:

```python
# Hourly (24 values: 00:00–23:00)
HOURLY_MULTIPLIERS = [0.43, 0.41, 0.45, 0.48, 0.52, 0.58, 0.68, 0.78, 0.92, 1.02, 1.08, 1.12, 1.15, 1.18, 1.20, 1.52, 1.48, 1.42, 1.32, 1.18, 1.08, 0.92, 0.78, 0.63]

# Day-of-Week (Mon–Sun)
DAY_OF_WEEK_MULTIPLIERS = [1.06, 1.01, 0.96, 0.96, 0.97, 1.02, 1.03]

# Monthly (Jan–Dec)
MONTHLY_MULTIPLIERS = [1.08, 1.12, 1.02, 0.98, 0.95, 0.87, 0.85, 0.90, 0.95, 1.00, 1.08, 1.10]

# Procedure-specific (winter/summer/elective adjustment)
PROCEDURE_SEASONALITY = {
    'Cardiac Catheterization': 1.15,  # Winter cardiac events
    'Appendectomy': 1.10,  # Summer surgical peak
    'Colonoscopy': 0.95,  # Winter dip
    'Bypass Surgery': 1.18,  # Winter ACS
    'Angioplasty': 1.12,  # Winter ACS
    'Hysterectomy': 1.02,  # Summer elective
    'Knee Replacement': 1.08,  # Summer post-sports-season
    'Hip Replacement': 1.05,  # Summer fall-prevention rush
    'Appendix Removal': 1.10,  # Summer
    'Gallbladder Removal': 1.03,  # Summer
    'Hernia Repair': 1.04,  # Summer
}
```

### Hospital Configuration

Hospitals are auto-generated on first run with size-based characteristics:

```python
HOSPITALS = [
    {'hospital_id': 1, 'hospital_name': 'Metro General', 'bed_count': 850, 'city': 'New York', 'state': 'NY'},  # Large
    {'hospital_id': 2, 'hospital_name': 'Central Memorial', 'bed_count': 420, 'city': 'Chicago', 'state': 'IL'},  # Medium
    {'hospital_id': 3, 'hospital_name': 'Riverside Clinic', 'bed_count': 200, 'city': 'Portland', 'state': 'OR'},  # Small
    # ... (10 total)
]
```

## Database Schema Details

### Date Dimension (date_dim)
```sql
CREATE TABLE date_dim (
    date DATE PRIMARY KEY,
    date_key INT,
    yyyy INT, mm INT, dd INT,
    mm_name VARCHAR(12), mm_short VARCHAR(3),
    day_of_week INT, day_of_week_name VARCHAR(10),
    is_weekend BIT,
    quarter INT,
    iso_year INT, iso_week INT,
    day_of_year INT, week_of_year INT,
    fiscal_year INT, fiscal_month INT,
    formatted_date_mmddyyyy VARCHAR(10),
    formatted_date_yyyymmdd VARCHAR(10)
);
-- 398 rows (2025-01-01 → 2026-02-02)
```

### Hospital Department Beds (hospital_department_beds)
```sql
CREATE TABLE hospital_department_beds (
    hospital_id INT,
    department_id INT,
    bed_count INT,
    PRIMARY KEY (hospital_id, department_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id),
    FOREIGN KEY (department_id) REFERENCES departments(department_id)
);
-- ~100 rows (10 hospitals × ~10 departments, ER skewed by size)
```

### Admissions (admissions)
```sql
CREATE TABLE admissions (
    admission_id INT PRIMARY KEY,
    encounter_id INT,
    hospital_id INT,
    patient_id INT,
    admit_datetime DATETIME,
    discharge_datetime DATETIME NULL,  -- NULL = ongoing stay
    FOREIGN KEY (encounter_id) REFERENCES encounters(encounter_id),
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id),
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
);
-- ~3,000–5,000 rows (proportional to encounter count)
```

### Views

#### vw_current_er_beds
```sql
CREATE VIEW vw_current_er_beds AS
SELECT 
    h.hospital_id, h.hospital_name,
    SUM(hdb.bed_count) AS total_er_beds,
    SUM(CASE WHEN a.discharge_datetime IS NULL OR a.discharge_datetime > GETDATE() THEN 1 ELSE 0 END) AS occupied_beds,
    SUM(hdb.bed_count) - SUM(CASE WHEN a.discharge_datetime IS NULL OR a.discharge_datetime > GETDATE() THEN 1 ELSE 0 END) AS available_beds
FROM hospitals h
JOIN hospital_department_beds hdb ON h.hospital_id = hdb.hospital_id
JOIN departments d ON hdb.department_id = d.department_id AND d.specialty_type = 'Emergency'
LEFT JOIN admissions a ON h.hospital_id = a.hospital_id
GROUP BY h.hospital_id, h.hospital_name;
```

#### vw_current_patient_beds
```sql
CREATE VIEW vw_current_patient_beds AS
SELECT 
    h.hospital_id, h.hospital_name, h.bed_count,
    COUNT(DISTINCT CASE WHEN a.discharge_datetime IS NULL OR a.discharge_datetime > GETDATE() THEN a.admission_id END) AS occupied_beds,
    h.bed_count - COUNT(DISTINCT CASE WHEN a.discharge_datetime IS NULL OR a.discharge_datetime > GETDATE() THEN a.admission_id END) AS available_beds
FROM hospitals h
LEFT JOIN admissions a ON h.hospital_id = a.hospital_id
GROUP BY h.hospital_id, h.hospital_name, h.bed_count;
```

## Sample Queries

### Q1: Procedure Volume by Season
```sql
SELECT 
    MONTH(d.yyyy) AS month_num,
    d.mm_name AS month,
    p.procedure_name,
    COUNT(*) AS procedure_count
FROM procedures p
JOIN date_dim d ON CAST(p.procedure_date AS DATE) = d.date
GROUP BY MONTH(d.yyyy), d.mm_name, p.procedure_name
ORDER BY procedure_count DESC;
```
*Expected Output: Cardiac Cath peaks in Jan/Feb/Dec; Appendectomy peaks in Jul/Aug*

### Q2: ED Occupancy by Hospital (Past 7 Days)
```sql
SELECT 
    h.hospital_name,
    COUNT(DISTINCT a.admission_id) AS current_admissions,
    h.bed_count,
    ROUND(100.0 * COUNT(DISTINCT a.admission_id) / h.bed_count, 1) AS occupancy_pct
FROM hospitals h
LEFT JOIN admissions a ON h.hospital_id = a.hospital_id 
    AND a.admit_datetime >= DATEADD(DAY, -7, GETDATE())
    AND (a.discharge_datetime IS NULL OR a.discharge_datetime > GETDATE())
GROUP BY h.hospital_id, h.hospital_name, h.bed_count
ORDER BY occupancy_pct DESC;
```

### Q3: Length of Stay by Admission Month
```sql
SELECT 
    DATENAME(MONTH, a.admit_datetime) AS admit_month,
    AVG(DATEDIFF(DAY, a.admit_datetime, ISNULL(a.discharge_datetime, GETDATE()))) AS avg_los_days,
    MIN(DATEDIFF(DAY, a.admit_datetime, ISNULL(a.discharge_datetime, GETDATE()))) AS min_los_days,
    MAX(DATEDIFF(DAY, a.admit_datetime, ISNULL(a.discharge_datetime, GETDATE()))) AS max_los_days
FROM admissions a
GROUP BY DATENAME(MONTH, a.admit_datetime), MONTH(a.admit_datetime)
ORDER BY MONTH(a.admit_datetime);
```

### Q4: Flu Diagnosis Rate During Bad Weather
```sql
SELECT 
    CASE 
        WHEN c.weather_condition IN ('Rain', 'Snow', 'Fog') THEN 'Bad Weather'
        ELSE 'Good Weather'
    END AS weather_type,
    COUNT(*) AS total_encounters,
    SUM(CASE WHEN d.diagnosis_name LIKE '%Flu%' THEN 1 ELSE 0 END) AS flu_diagnoses,
    ROUND(100.0 * SUM(CASE WHEN d.diagnosis_name LIKE '%Flu%' THEN 1 ELSE 0 END) / COUNT(*), 2) AS flu_rate_pct
FROM encounters e
LEFT JOIN diagnoses d ON e.encounter_id = d.encounter_id
GROUP BY CASE 
        WHEN c.weather_condition IN ('Rain', 'Snow', 'Fog') THEN 'Bad Weather'
        ELSE 'Good Weather'
    END;
```

## Troubleshooting

### Issue: "pyodbc.Error: ('08001', '[08001] [Microsoft][ODBC Driver 17 for SQL Server]…"
**Solution**: Verify `CONNECTION_STRING` in `src/config.py`. Test connection:
```bash
python -c "import pyodbc; pyodbc.connect('your_connection_string')"
```

### Issue: Weather cache not persisting across runs
**Solution**: Check file permissions on `weather_cache.json`. Ensure script has write access to project root.
```bash
ls -la weather_cache.json  # Linux/Mac
dir weather_cache.json     # Windows
```

### Issue: Rebuild taking too long (>10 minutes for 399 days)
**Solution**: Normal for first run (399 API calls cached). Subsequent runs use cache (instant). Force parallel processing if needed:
- For now, run once with `--rebuild-start 2025-01-01` and let it complete
- Cache will populate over ~2–5 minutes
- Future runs use cache (seconds)

### Issue: "KeyError" in procedure seasonality
**Solution**: Ensure all 11 procedure names in `PROCEDURE_SEASONALITY` dict match exactly with `PROCEDURE_WEIGHTS` keys in `src/main.py`. Check spelling.

### Issue: SQL view queries return 0 occupancy
**Solution**: Verify admissions table has data. Run:
```sql
SELECT COUNT(*) FROM admissions WHERE discharge_datetime IS NULL OR discharge_datetime > GETDATE();
```
If empty, rebuild: `python src/main.py --rebuild-start 2025-01-01`

## Performance Characteristics

| Operation | Duration | Notes |
|-----------|----------|-------|
| Initial build (399 days) | 2–5 min | ~399 API calls cached; DB inserts |
| Subsequent rebuild (cache hit) | 30–60 sec | No API calls; cache used |
| Daily incremental | <5 sec | Cache hit for today's weather |
| Weather cache save/load | <100 ms | JSON serialization |
| SQL views (vw_current_patient_beds) | <500 ms | Scans admissions; indexed on hospital_id |

## Development & Contributing

### Project Structure
```
Healthcare Data Generator/
├── src/
│   ├── main.py              # Core generation logic (1,400+ lines)
│   ├── config.py            # DB connection + seasonality multipliers
│   └── __pycache__/
├── scripts/
│   └── validate_and_create_date_dim.py  # Helper for date_dim validation
├── requirements.txt         # Dependencies (pandas, faker, sqlalchemy, pyodbc, requests)
├── README.md               # This file
├── weather_cache.json      # Auto-generated; weather by date
└── .github/
    └── copilot-instructions.md  # Copilot workspace hints
```

### Adding Custom Seasonality
1. Open `src/config.py`
2. Modify `HOURLY_MULTIPLIERS`, `DAY_OF_WEEK_MULTIPLIERS`, or `MONTHLY_MULTIPLIERS` arrays
3. Adjust `PROCEDURE_SEASONALITY` dict for procedure-specific tweaks
4. Re-run: `python src/main.py --rebuild-start 2025-01-01`

### Testing New Features
```bash
# Quick test (1 day, fresh cache)
python src/main.py --clear-weather-cache --rebuild-start 2025-01-01

# Validate specific table (e.g., admissions)
python -c "import pandas as pd; from src.config import *; df = pd.read_sql('SELECT TOP 10 * FROM admissions', CONNECTION_STRING); print(df)"
```

## References & Citations

### Seasonality Data
- **NHS A&E Attendance Patterns**: https://www.nhs.uk/NHSEngland/ (ED volume by hour/day/month)
- **CDC NHAMCS**: https://www.cdc.gov/nchs/nhamcs/about_nhamcs.htm (US hospital ambulatory patterns)
- **Influenza Season**: https://www.cdc.gov/flu/about/season/flu-season.htm (Oct–May peak)
- **PMC: Seasonal Procedural Variation**: https://www.ncbi.nlm.nih.gov/pmc/ (surgical seasonality research)

### Weather API
- **Open-Meteo Archive API**: https://open-meteo.com/en/docs/historical-weather-api (free historical weather)

### Healthcare Data Standards
- **ICD-10-CM**: https://www.cdc.gov/nchs/icd/icd10cm.htm (diagnosis codes)
- **CPT**: https://www.ama-assn.org/practice-management/cpt (procedure codes)

## License

MIT License - See LICENSE file for details.

---

## Secrets & Configuration 🔒

- **Do NOT commit credentials** (connection strings, passwords, tokens) to the repo. If you previously committed secrets, rotate them immediately.
- Use environment variables (see `.env.example`) or create a local `src/config_local.py` (this file is included in `.gitignore`) to store your `CONNECTION_STRING` for local development.
- Example: set `CONNECTION_STRING` in your shell or copy `.env.example` to `.env` and fill values.
- Optionally install `python-dotenv` and `pip install python-dotenv` to load `.env` automatically in development.

## Payer & Clinical Realism Enhancements ✅

Recent improvements (Feb 2026):
- **Payer Mix**: Patient `primary_payer` and `insurance` now reflect approximate US market share (Medicare ~36%, Medicaid ~20%, Commercial ~35%, Uninsured ~5%, Other ~4%). Age and hospital specialty adjust sampling (e.g., higher Medicare in elderly; higher Medicaid for pediatrics).
- **Diagnosis Distribution**: ICD-10 sampling is specialty-weighted and seasonally adjusted (e.g., influenza codes surge in Dec–Feb; pediatric respiratory codes increase in winter). Diagnoses are linked to `chief_complaint` and to likely labs/medications when applicable.
- **Procedures, Labs, Medications**: These entities are now sampled using specialty-aware weights and seasonality (e.g., more cardiac catheterizations in cardiac hospitals, appendectomies trend upward in summer). Labs/meds are tied to diagnoses when possible to improve clinical plausibility.
- **Clinical Mapping Expanded**: Added additional ICD-10 entries and richer `DIAGNOSIS_TO_MEDS` and `DIAGNOSIS_TO_LABS` mappings (sepsis, pneumonia, COPD exacerbation, cellulitis, stroke) so downstream analytics (top meds, labs by diagnosis) more closely mirror real-world hospital data.
- **Aggregate Trends**: Monthly and hourly patterns now produce noticeable aggregate trends (seasonal peaks, weekday effects, payer distribution shifts by age/specialty) to make analytics realistic.

**Sources**: CDC NHAMCS, AHA cardiovascular statistics, NCI SEER, ACEP ED operations, CMS payer mix reports, peer-reviewed studies on seasonality and clinical practice patterns.

**Version**: 2.1 (Clinical realism + payer distributions)
**Last Updated**: February 5, 2026  
**Maintained By**: Healthcare Data Generator Team

For issues, feature requests, or questions, open an issue on the project repository.