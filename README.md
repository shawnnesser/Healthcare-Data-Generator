# Healthcare Data Generator (Microsoft Fabric)

A synthetic healthcare data generation system that produces realistic hospital
encounter, admission, and operational data — hospital specialization, weather-driven
diagnosis patterns, ER/bed occupancy modeling, and full patient-location tracking.
Designed for testing analytics pipelines, healthcare dashboards, and data
engineering workflows without requiring real patient data.

**This project runs entirely as Microsoft Fabric notebooks.** There is no local
Python application to install or run — the notebooks are the product. A small
set of `scripts/` exist only to build, deploy, run, and validate those notebooks
from your machine (or CI).

---

## Architecture

| Component | What it is | Where |
|---|---|---|
| **Healthcare_Data_Generator** | Production Fabric notebook. Generates/backfills all clinical & operational data, idempotent daily catch-up. | [notebooks/healthcare_data_generator_fabric_inlined.ipynb](notebooks/healthcare_data_generator_fabric_inlined.ipynb) |
| **Healthcare_Data_Validation** | Fabric notebook that runs a SQL data-quality check suite (row counts, gap detection, referential integrity, duplicates, NULLs, views) and prints a PASS/FAIL summary. | [notebooks/healthcare_data_validation.ipynb](notebooks/healthcare_data_validation.ipynb) |
| Build scripts | Regenerate the two notebooks above from Python source (so logic lives in version-controlled `.py`, not hand-edited `.ipynb` JSON). | [scripts/build_fabric_notebook.py](scripts/build_fabric_notebook.py), [scripts/build_validation_notebook.py](scripts/build_validation_notebook.py) |
| Deploy/run/check scripts | Create-or-update a notebook in your Fabric workspace, trigger an on-demand run via the Jobs API, and check job status — all non-interactively (AAD token via `az` CLI, no browser popups). | [scripts/deploy_notebook.py](scripts/deploy_notebook.py), [scripts/run_fabric_notebook.py](scripts/run_fabric_notebook.py), [scripts/check_job_status.py](scripts/check_job_status.py) |
| Local validation helper | Fast non-interactive SQL sanity check you can run from a terminal (same checks as the Validation Notebook), useful while iterating. | [scripts/validate_fabric_data.py](scripts/validate_fabric_data.py) |

Both notebooks connect to the Fabric SQL endpoint **without any interactive
login**: when running inside Fabric they detect it (`import notebookutils`) and
fetch a non-interactive AAD access token (`notebookutils.credentials.getToken('pbi')`),
which is required for the notebook to be triggered headlessly (via the Jobs API
or a schedule) with no human present to click through a browser sign-in.

---

## Quick Start (for LLMs and Automated Agents)

```bash
# 0. Prerequisites: az CLI installed and logged in with access to the Fabric
#    workspace (`az login`). Python only needed locally to run scripts/ (not
#    to generate data — that happens inside Fabric).
pip install -r requirements.txt

# 1. Edit generation logic in scripts/build_fabric_notebook.py (never edit the
#    .ipynb directly), then regenerate the notebook:
python scripts/build_fabric_notebook.py

# 2. Deploy (create-or-update) it in your Fabric workspace:
python scripts/deploy_notebook.py --notebook-path notebooks/healthcare_data_generator_fabric_inlined.ipynb --notebook-name Healthcare_Data_Generator

# 3. Trigger a run and wait for completion:
python scripts/run_fabric_notebook.py --notebook-name Healthcare_Data_Generator --poll-interval 20 --timeout 10800

# 4. Validate the result (same pattern for the validation notebook):
python scripts/build_validation_notebook.py
python scripts/deploy_notebook.py --notebook-path notebooks/healthcare_data_validation.ipynb --notebook-name Healthcare_Data_Validation
python scripts/run_fabric_notebook.py --notebook-name Healthcare_Data_Validation --poll-interval 15 --timeout 600

# ...or just run the local Python validation helper (no Fabric job needed):
python scripts/validate_fabric_data.py
```

**Key files an agent needs to know about:**

| File | Purpose |
|---|---|
| `scripts/build_fabric_notebook.py` | Source of truth for the generator notebook's logic — edit this, then rebuild |
| `scripts/build_validation_notebook.py` | Source of truth for the validation notebook's SQL checks |
| `scripts/deploy_notebook.py` | Create-or-update any notebook in the Fabric workspace by name |
| `scripts/run_fabric_notebook.py` | Trigger + poll an on-demand notebook run via the Fabric Jobs API |
| `scripts/check_job_status.py` | Check a specific job-instance ID's status |
| `scripts/validate_fabric_data.py` | Local, non-interactive SQL validation (row counts, gaps, integrity, views) |
| `notebooks/healthcare_data_generator_fabric_inlined.ipynb` | Deployed generator notebook (generated file — don't hand-edit) |
| `notebooks/healthcare_data_validation.ipynb` | Deployed validation notebook (generated file — don't hand-edit) |

**Never edit the `.ipynb` files directly.** They're generated artifacts; edit the
corresponding `build_*.py` script and re-run it, then redeploy.

---

## Overview

The Healthcare Data Generator produces multi-table healthcare datasets covering:

- **Patient Demographics & Insurance**: Patient records with synthetic personal identifiers and payer information
- **Hospital Operations**: Hospital bed inventory, department-level bed allocation (including ER surge capacity based on hospital size)
- **Clinical Encounters**: ED encounters, visits, and admissions with realistic temporal patterns
- **Admissions & Occupancy**: Full admission/discharge tracking for precise bed occupancy calculations
- **Clinical Data**: Procedures, diagnoses, medications, labs, and billing records
- **Temporal Dimensions**: Date dimension table with full gregorian and fiscal calendars
- **Environmental Context**: Weather integration from historical data, affecting disease patterns (flu, falls)
- **Hospital Specialization**: Multi-specialty hospital system with realistic admission rates, diagnosis routing, and seasonality variance by hospital type
- **Patient Location & Floor Management**: Real-time floor/room/bed tracking with clinical status

### Key Features

#### 🏥 Hospital Specialization System
Realistic hospital types with specialty-specific behaviors:

- **General Hospitals** (5 hospitals): Full-service ED, 20% admission rate, blended seasonal patterns
  - Specialties: Trauma, internal medicine, general surgery, psychiatry, OB/GYN
  - Seasonal variance: Jan/Dec peaks (+12% to +18%), Jul trough (-10%)

- **Cardiac Specialty Institute** (1 hospital): Cardiology-focused, 72% admission rate
  - Dominant diagnoses: Acute coronary syndrome (28%), heart failure (22%), arrhythmia (18%)
  - **Winter ACS surge** (Jan +38% vs. Jul); admission timing: early morning peaks (35% 6–10am)
  - **NO Emergency Department** — emergencies route through general hospital then transfer
  - Payer mix: Medicare 45%, Commercial 40% (older cardiac patient population)

- **Pediatric Children's Hospital** (1 hospital): Pediatric specialty, 12% admission rate
  - Dominant diagnoses: URI (22%), otitis media (18%), asthma (12%), fractures (15%)
  - Seasonal pattern: Winter respiratory peaks (Jan +35% vs. Jul)
  - Payer mix: Medicaid 52%, Commercial 35%

- **Cancer Center** (1 hospital): Oncology/hematology, 96% admission rate (highest)
  - Dominant diagnoses: Febrile neutropenia (22%), infection/sepsis (20%), acute leukemia (18%)
  - Seasonal pattern: stable ±6% (scheduled treatments dominate); avg LOS 7.4 days (longest of acute types)
  - **NO Emergency Department** — direct admissions from oncology practices

- **Rehabilitation Center** (1 hospital): Post-acute care, 85% admission rate
  - Patient mix: Orthopedic post-op (35%), stroke recovery (25%), cardiac rehab (15%)
  - Seasonal pattern: Spring/fall peaks (Mar/Apr/Oct +10%, Jul -8%); avg LOS 21 days (longest overall)
  - **NOT AN ED** — physician referrals only, 7am–5pm admission hours

- **Specialty Diagnostic Center** (1 hospital): Imaging/labs only, business hours only, no ED, no admissions

**Hospital-Specific Monthly Seasonality:**

| Month | Pediatric | Cardiac | Cancer | General | Rehab |
|---|---|---|---|---|---|
| **Jan** | **+35%** | **+38%** | 5% | +12% | 4% |
| **Feb** | **+28%** | **+32%** | 3% | +8% | 2% |
| **Jul** | **-25%** | **-27%** | -6% | -10% | **-8%** |
| **Oct** | -1% | -2% | 2% | 0% | **+12%** ⬆ Peak |
| **Dec** | **+26%** | **+28%** | 6% | **+18%** | 0% |

Full monthly variance tables, admission-timing distributions, and operational
recommendations are in [HOSPITAL_SEASONALITY_AND_OCCUPANCY_ANALYSIS.md](HOSPITAL_SEASONALITY_AND_OCCUPANCY_ANALYSIS.md).

#### 📊 ER Bed Occupancy Stress Modeling
- **Hourly baseline**: 38% occupancy at 4am (minimum) → 89% at 2pm (peak)
- **Friday 2–6pm: 93–95% occupancy** (weekend elective surge, trauma spike) — approaches bypass thresholds
- Early morning (midnight–6am): ~50% empty beds — ideal window for transfers/admissions

#### 🌡️ Weather Integration
- Historical weather from the **Open-Meteo API** (free, no key required), cached in-memory + on disk
- Rain/snow/fog increase flu and fall-related diagnoses; per-date weather applied during generation

#### 🛏️ Patient Location & Floor Management
Real-time floor/room/bed tracking with clinical status:
- Floors organized by department specialty (Emergency, ICU, Med/Surg, specialty units)
- Smart bed placement based on diagnosis severity, age, LOS, and hospital specialty
- Clinical status (`Critical | Unstable | Post-Op | Recovering | Improving | Stable`) evolves with LOS
- Views: `vw_floor_plan`, `vw_patient_location`, `vw_floor_occupancy`, `vw_hospital_status`

See [PATIENT_LOCATION_SYSTEM.md](PATIENT_LOCATION_SYSTEM.md) and [PATIENT_LOCATION_QUICKSTART.md](PATIENT_LOCATION_QUICKSTART.md) for details.

#### 📚 Clinical & Payer Realism
- 39 ICD-10 codes with full clinical descriptions and realistic chief complaints
- Diagnoses linked to plausible labs/medications (sepsis, pneumonia, COPD, cellulitis, stroke, etc.)
- Payer mix reflects US market share (Medicare ~36%, Commercial ~35%, Medicaid ~20%, Uninsured ~5%, Other ~4%), adjusted by age and hospital specialty
- Procedure volumes weighted by specialty and seasonality (e.g. more cardiac catheterizations in cardiac hospitals, appendectomies trend up in summer)

---

## What Runs Inside the Generator Notebook

`Healthcare_Data_Generator` is a single self-contained notebook (12 code cells +
1 markdown cell, no `src/` imports) that:

1. **Cell 1** — Loads configuration/env vars, auto-installs any missing packages (`faker`, `pyodbc`, `python-dotenv`, `sqlalchemy`)
2. **Cell 2** — Validates the Python environment & ODBC drivers
3. **Cell 3** — Opens a single persistent DB connection (`SingletonThreadPool`). Inside Fabric this uses a non-interactive AAD access token; outside Fabric it falls back to `Authentication=ActiveDirectoryInteractive`
4. **Cell 4** — Computes the catch-up range: `MAX(encounter_date)` in `encounters` → today (empty DB → `DEFAULT_HISTORY_START_DATE`)
5. **Cells 5–9** — Static reference data, hospital-specific helper functions, weather functions, core generators, floor/room/bed management
6. **Cell 10** — Orchestrator: loops day-by-day over the catch-up range generating patients/doctors/encounters/diagnoses/procedures/medications/labs/insurance/billing/admissions with real, collision-free IDs, appending to each table
7. **Cell 11** — Recomputes `patient_bed_assignments` and refreshes all views once after the full day-loop, then logs the run
8. **Cell 12** — Validation & final report (row counts, date range)

**Catch-up is idempotent** — safe to run any time; it only ever generates the
days between the last loaded date and today. An optional `MAX_CATCHUP_DAYS` env
var caps how many days a single run will backfill (re-running continues where
it left off).

### Configuration (environment variables, all optional)

| Variable | Default | Purpose |
|---|---|---|
| `PATIENT_LOAD_MULTIPLIER` | `4.0` | Scales daily patient/encounter volume |
| `HOSPITAL_BED_SCALE` | `0.35` | Scales hospital bed counts (occupancy realism) |
| `MIN_HOSPITAL_BEDS` | `40` | Floor on bed count per hospital |
| `MAX_CATCHUP_DAYS` | `0` (unlimited) | Caps days backfilled in a single run |
| `DEFAULT_HISTORY_START_DATE` | `2025-01-01` | Start date used only when the DB is empty |
| `WEATHER_LATITUDE` / `WEATHER_LONGITUDE` | NYC | Location used for weather-driven diagnosis patterns |
| `FABRIC_SERVER` / `FABRIC_DB` | (hardcoded to the deployed endpoint) | Override the target Fabric SQL endpoint/database |
| `FABRIC_POOL_RECYCLE_SECONDS` | `43200` (12h) | Connection pool recycle interval |
| `CONNECTION_STRING` / `FABRIC_CONNECTION_STRING` | — | Full override, e.g. for local (non-Fabric) testing |

Set these as Fabric notebook/environment variables, or via `.env` when running
a notebook locally outside Fabric.

---

## What Runs Inside the Validation Notebook

`Healthcare_Data_Validation` runs read-only checks and prints a final
`PASS`/`FAIL` summary:

1. Table inventory & row counts
2. Encounter date-range & gap check (every calendar day should have data)
3. Daily volume sanity (last 10 days)
4. Referential integrity — orphan FK checks (diagnoses/procedures/medications/labs/billing/insurance/admissions → their parent tables)
5. Duplicate primary-key checks
6. NULL checks on key columns
7. Reference data presence (hospitals/departments/date_dim)
8. View queryability (`vw_current_er_beds`, `vw_current_patient_beds`, `vw_floor_plan`, `vw_patient_location`, `vw_floor_occupancy`, `vw_hospital_status`)

Run it after every generator run (manually, or chained in a Fabric pipeline/schedule).

---

## Deploying & Scheduling

1. Make sure you're authenticated: `az login` (needs access to the target Fabric workspace)
2. Build + deploy + run each notebook using the Quick Start commands above
3. In the Fabric portal, open the notebook → **Schedule** → set a daily recurrence (2 AM recommended) so it self-catches-up automatically
4. Optionally chain the validation notebook to run right after, via a Fabric Data Pipeline

---

## Database Schema

**Core Tables:**

| Table | Purpose | Key Columns |
|---|---|---|
| `date_dim` | Temporal reference | date, yyyy, mm, dd, day_of_week, is_weekend, fiscal_month, iso_week |
| `hospitals` | Hospital master data | hospital_id, name, bed_count, city, state |
| `departments` | Operational units | department_id, department_name, hospital_id, specialty_type |
| `hospital_department_beds` | Bed allocation | hospital_id, department_id, bed_count |
| `patients` | Patient demographics | patient_id, first_name, last_name, date_of_birth, age, gender, address, primary_payer |
| `doctors` | Clinical staff | provider_id, first_name, last_name, specialty |
| `encounters` | ED visits/admissions | encounter_id, patient_id, hospital_id, department_id, provider_id, encounter_date, payer_type, chief_complaint |
| `admissions` | Admission records | admission_id, encounter_id, hospital_id, patient_id, admit_datetime, discharge_datetime |
| `procedures` | Surgical/clinical procedures | procedure_id, hospital_id, encounter_id, procedure_name, procedure_date |
| `diagnoses` | ICD codes linked to encounters | diagnosis_id, encounter_id, icd_code, description |
| `medications` | Prescriptions | medication_id, encounter_id, medication_name, dosage |
| `labs` | Lab results | lab_id, encounter_id, lab_name, result, normal_range |
| `insurance` | Insurance master data | insurance_id, patient_id, company_name, plan_name, copay |
| `billing` | Charges & billing records | billing_id, encounter_id, patient_id, total_charges, paid_amount, balance, claim_status |
| `run_logs` | Audit trail of generator runs | run_timestamp, start_date, end_date, days_generated |

**Patient Location & Floor Management Tables:**

| Table | Purpose | Key Columns |
|---|---|---|
| `floors` | Hospital floors/units by specialty | hospital_id, floor_number, department, bed_type, capacity |
| `rooms` | Individual rooms on each floor | room_id, floor_id, room_number, bed_count, room_type |
| `beds` | Individual bed tracking | bed_id, room_id, hospital_id, bed_type, status |
| `patient_bed_assignments` | Current patient locations & clinical status | admission_id, patient_id, bed_id, assigned_datetime, patient_status, diagnosis_code, los_days |

**Views:**

| View | Purpose |
|---|---|
| `vw_current_er_beds` | Real-time ER bed availability by hospital |
| `vw_current_patient_beds` | Real-time patient occupancy across all beds |
| `vw_floor_plan` | Every bed/room/floor with occupancy and patient info |
| `vw_patient_location` | Patient-centric view: location + demographics + clinical picture |
| `vw_floor_occupancy` | Floor-level occupancy dashboard |
| `vw_hospital_status` | Hospital-wide occupancy and acuity summary |

---

## Sample Queries

```sql
-- Find all critical patients across hospitals
SELECT patient_name, hospital_name, department, clinical_status, doctor_name
FROM vw_patient_location WHERE clinical_status = 'Critical';

-- Procedure volume by month (expect cardiac cath peaks in Jan/Feb/Dec)
SELECT d.mm_name AS month, p.procedure_name, COUNT(*) AS procedure_count
FROM procedures p
JOIN date_dim d ON CAST(p.procedure_date AS DATE) = d.date
GROUP BY d.mm_name, p.procedure_name
ORDER BY procedure_count DESC;

-- ED occupancy by hospital (last 7 days)
SELECT h.hospital_name, COUNT(DISTINCT a.admission_id) AS current_admissions, h.bed_count,
       ROUND(100.0 * COUNT(DISTINCT a.admission_id) / h.bed_count, 1) AS occupancy_pct
FROM hospitals h
LEFT JOIN admissions a ON h.hospital_id = a.hospital_id
    AND a.admit_datetime >= DATEADD(DAY, -7, GETDATE())
    AND (a.discharge_datetime IS NULL OR a.discharge_datetime > GETDATE())
GROUP BY h.hospital_id, h.hospital_name, h.bed_count
ORDER BY occupancy_pct DESC;
```

More examples (referential-integrity/data-quality queries) are in
[scripts/build_validation_notebook.py](scripts/build_validation_notebook.py).

---

## Troubleshooting

Issues actually encountered deploying/running this in Fabric, and their fixes
(all already applied in the current `build_fabric_notebook.py`):

| Symptom | Cause | Fix |
|---|---|---|
| Jobs API returns `Not supported language: .` | Notebook's `metadata.language_info.name` was empty | Set `kernelspec`/`language_info` in the build script before `nbf.write()` |
| Job fails fast with missing-package error | `faker`/`pyodbc` aren't preinstalled in Fabric's default runtime | Auto-install missing packages at the top of Cell 1 |
| Job reports `Completed` in ~1 minute but **zero new rows** | `Authentication=ActiveDirectoryInteractive` can't complete without a human clicking a browser popup — the exception is silently caught | Detect Fabric (`import notebookutils`) and use a non-interactive AAD token instead |
| `notebookutils.credentials.getToken()` fails for arbitrary resource URLs | Only `storage`/`pbi`/`keyvault`/`kusto` audiences are supported | Use audience `'pbi'` — Fabric SQL endpoints accept it |
| `Invalid argument(s) 'max_overflow'` from `create_engine()` | `SingletonThreadPool` doesn't accept `max_overflow` (a `QueuePool`-only concept), only surfaces with a `creator=` engine | Remove `max_overflow`/`pool_size` from `create_engine()` calls |
| Can't tell what actually happened in a headless run | The Jobs API (`GET .../jobs/instances/{id}`) never returns cell output or tracebacks, only a generic `failureReason` | Write breadcrumbs to a `notebook_diagnostics` table from a best-effort, independent connection at key checkpoints |

If you need to debug a run this way again, add a `_write_diagnostic(message)`
helper (see git history of `build_fabric_notebook.py`) and query the
`notebook_diagnostics` table afterward.

---

## Project Structure

```
Healthcare Data Generator/
├── notebooks/
│   ├── healthcare_data_generator_fabric_inlined.ipynb   # deployed generator notebook (generated)
│   └── healthcare_data_validation.ipynb                 # deployed validation notebook (generated)
├── scripts/
│   ├── build_fabric_notebook.py       # source of truth: generator notebook logic
│   ├── build_validation_notebook.py   # source of truth: validation notebook logic
│   ├── deploy_notebook.py             # create-or-update a notebook in Fabric
│   ├── run_fabric_notebook.py         # trigger + poll an on-demand notebook run
│   ├── check_job_status.py            # check a job-instance ID's status
│   └── validate_fabric_data.py        # local non-interactive SQL validation helper
├── EPIC_COMPARISON_AND_GAP_ANALYSIS.md
├── FABRIC_DATA_AGENT_INSTRUCTIONS.md
├── HOSPITAL_SEASONALITY_AND_OCCUPANCY_ANALYSIS.md
├── IMPLEMENTATION_SUMMARY.md
├── PATIENT_LOCATION_IMPLEMENTATION.md
├── PATIENT_LOCATION_QUICKSTART.md
├── PATIENT_LOCATION_SYSTEM.md
├── requirements.txt   # deps needed to run scripts/ locally (nbformat, pyodbc, sqlalchemy, ...)
├── .env.example        # only needed for local/manual notebook testing outside Fabric
└── README.md
```

## Development

1. Edit generation/validation logic in `scripts/build_fabric_notebook.py` or `scripts/build_validation_notebook.py` — never hand-edit the `.ipynb` files
2. Re-run the corresponding build script to regenerate the notebook
3. Redeploy with `scripts/deploy_notebook.py`
4. Test with `scripts/run_fabric_notebook.py`, then confirm with `scripts/validate_fabric_data.py` or the validation notebook

> Inside the `r"""..."""`-delimited cell-source strings in the build scripts,
> never use `"""` for inner docstrings/SQL blocks — it collides with the outer
> raw-string delimiter and silently corrupts later cells. Use `'''`/`f'''` or
> plain `#` comments instead.

---

## References & Citations

- **NHS A&E Attendance Patterns** — ED volume by hour/day/month
- **CDC NHAMCS** — US hospital ambulatory care patterns
- **CDC Influenza Season Tracking** — Oct–May peak
- **PMC surgical seasonality studies** — procedure volume variation
- **Open-Meteo Archive API** — free historical weather data
- **ICD-10-CM** / **CPT** — diagnosis and procedure code standards

## Secrets & Configuration 🔒

- **Do NOT commit credentials** (connection strings, passwords, tokens) to the repo.
- The deployed Fabric notebooks need no secrets at all — they authenticate via
  a Fabric-provided non-interactive AAD token.
- `CONNECTION_STRING` in `.env` is only for local/manual notebook testing outside Fabric; `.env` is gitignored.
- All `scripts/` authenticate via the `az` CLI (`az login`) — no secrets stored anywhere in this repo.

## License

MIT License - See LICENSE file for details.
