# Fabric Data Agent Instructions - Healthcare Data Generator

**Dataset**: Healthcare Data Generator (Synthetic Hospital Network)  
**Generated**: January 1, 2025 – February 4, 2026 (400 days)  
**Database**: Microsoft Fabric SQL  
**Purpose**: Operational analytics for hospital network (10 hospitals, 6 specializations)

---

## 1. Dataset Overview

You are working with a **synthetic healthcare dataset** representing a network of 10 hospitals with realistic operational patterns, seasonality, and patient routing. The data is NOT real patient data but is structured and populated to reflect real-world hospital operations.

**Key Characteristics:**
- **10 hospitals** across 6 specialization types (5 general, 1 cardiac, 1 pediatric, 1 cancer, 1 rehab, 1 diagnostic)
- **400 days of data** spanning full seasonal cycles (winter peaks, summer valleys)
- **Hospital-specific seasonality**: Pediatric varies ±35%, Cardiac ±38%, Cancer ±6%
- **Realistic admission patterns**: Specialty-specific admission rates (12% pediatric → 96% cancer)
- **ER occupancy stress**: Intra-day variation from 38% (4am) to 89% (2pm), day-of-week peaks
- **Admission timing patterns**: Specialty-dependent (cardiac peaks 6–10am, rehab 7–9am)

---

## 2. Schema Overview

### Core Tables

#### **HOSPITALS** (10 rows)
- `HOSPITAL_ID` (PK)
- `HOSPITAL_NAME`
- `SPECIALTY_TYPE`: 'General', 'Cardiac', 'Pediatric', 'Cancer', 'Rehabilitation', 'Diagnostic'
- `CITY`, `STATE`
- `TOTAL_BEDS`, `ED_BEDS`, `ICU_BEDS`

#### **DEPARTMENTS** (50 rows, 5 per hospital)
- `DEPARTMENT_ID` (PK)
- `DEPARTMENT_NAME`: Emergency Department, ICU, Medical/Surgical, Pediatrics, Cardiac Care, etc.
- `HOSPITAL_ID` (FK)
- `BED_COUNT`
- `DEPARTMENT_TYPE`: 'ED', 'Inpatient', 'Specialty', 'ICU'
- `BUSINESS_HOURS_ONLY`: Boolean (diagnostic centers have restricted hours)

#### **PATIENTS** (900k+ rows)
- `PATIENT_ID` (PK)
- `MRN` (Medical Record Number)
- `DATE_OF_BIRTH`, `AGE` (calculated at encounter time)
- `GENDER`: M/F
- `CITY`, `STATE`
- `PRIMARY_HOSPITAL_ID`: Patient's home hospital (determines specialty exposure)

#### **ENCOUNTERS** (1.8M+ rows)
- `ENCOUNTER_ID` (PK)
- `PATIENT_ID` (FK)
- `HOSPITAL_ID` (FK)
- `DEPARTMENT_ID` (FK)
- `ENCOUNTER_DATE`
- `ADMISSION_TYPE`: 'Emergency', 'Urgent', 'Inpatient'
- `ADMISSION_TIME`, `DISCHARGE_TIME` (hour of day for ER, precise for inpatients)
- `LOS` (Length of Stay in hours)
- `TOTAL_CHARGES` (calculated from DRG-like multipliers)

#### **DIAGNOSES** (2.4M+ rows)
- `DIAGNOSIS_ID` (PK)
- `ENCOUNTER_ID` (FK)
- `ICD10_CODE`: Standard ICD-10 diagnosis codes (specialty-weighted)
- `DIAGNOSIS_DESC`
- `IS_PRIMARY`: Boolean (primary vs. secondary diagnoses)
- `DIAGNOSIS_WEIGHT`: ICD-10 diagnosis weight for DRG calculation

#### **ADMISSIONS** (300k+ rows)
- `ADMISSION_ID` (PK)
- `ENCOUNTER_ID` (FK)
- `PATIENT_ID` (FK)
- `HOSPITAL_ID` (FK)
- `ADMISSION_DATE`
- `DISCHARGE_DATE`
- `ADMISSION_HOUR`: Hour of day admission occurred (0–23)
- `DISCHARGE_HOUR`: Hour of day discharge occurred
- `LOS` (Length of Stay in days)
- `ADMISSION_RATE_APPLIED`: Specialty-specific admission probability (0.12–0.96)

#### **WEATHER** (400 rows, one per day)
- `WEATHER_DATE`
- `TEMPERATURE_HIGH`, `TEMPERATURE_LOW`, `PRECIPITATION_MM`
- `WEATHER_CONDITION`: 'Clear', 'Cloudy', 'Rainy', 'Snowy'
- Used for context on seasonal variation

---

## 3. Hospital Specialization & Routing Logic

### Hospital Types & Characteristics

| Specialty | Hospital Count | Admission Rate | Avg LOS (days) | Key Diagnosis Types | Seasonal Peak | Peak Month |
|-----------|---|---|---|---|---|---|
| **General** | 5 | 20% | 2.5 | Pneumonia, UTI, Chest Pain, Abdominal Pain | Moderate | Jan (1.12×) |
| **Cardiac** | 1 | 72% | 3.5 | AMI, Heart Failure, Arrhythmia | High | Jan (1.38×) |
| **Pediatric** | 1 | 12% | 1.2 | Bronchiolitis, Otitis, Asthma, RSV | Very High | Jan (1.35×) |
| **Cancer** | 1 | 96% | 7.4 | Leukemia, Lymphoma, Solid Tumors | Low (stable) | Jan (1.05×) |
| **Rehabilitation** | 1 | 85% | 21.0 | Post-stroke, Post-surgery, Joint replacement | Moderate | Mar/Apr/Oct |
| **Diagnostic** | 1 | 15% | 0.3 | Imaging only (no ED, business hours 7am–6pm) | Low | Stable |

### Patient Routing
- **Patients are affiliated with a "Primary Hospital"** (assigned by ZIP code logic in generation)
- When a patient visits, they go to their primary hospital or specialty-appropriate facility
- Diagnosis specialty routing ensures realistic distribution (e.g., cardiac patients 70% to Cardiac Hospital, 20% to General, 10% other)
- Pediatric encounters concentrate at Pediatric Hospital (85%) vs. General (15%)

---

## 4. Seasonality & Temporal Patterns

### Monthly Seasonality Multipliers
Applied to base encounter count. **Example**: Pediatric Hospital in January sees 1.35× encounters vs. July baseline.

**Pediatric Multipliers (by month)**: [1.35, 1.30, 1.28, 1.08, 0.92, 0.88, 0.85, 0.89, 1.05, 1.20, 1.28, 1.32]
- **Peak**: December–February (flu, RSV, cold/cough season)
- **Low**: July–August (summer break, fewer infections)

**Cardiac Multipliers**: [1.38, 1.35, 1.22, 1.10, 0.92, 0.87, 0.87, 0.89, 1.05, 1.15, 1.28, 1.35]
- **Peak**: December–February (cold weather, ACS surge)
- **Low**: July–August (summer improvement)

**Cancer Multipliers**: [1.05, 1.04, 1.04, 1.02, 0.99, 0.94, 0.94, 0.95, 0.98, 1.02, 1.04, 1.05]
- **Stable** (±6% throughout year, driven by scheduled treatments not seasonality)

**General Hospital Multipliers**: [1.12, 1.10, 1.08, 1.00, 0.92, 0.88, 0.90, 0.91, 1.02, 1.10, 1.12, 1.13]
- **Blended** (moderate winter peak, summer low)

**Rehabilitation Multipliers**: [0.98, 0.99, 1.10, 1.12, 1.08, 0.92, 0.88, 0.90, 0.95, 1.10, 1.08, 1.02]
- **Bimodal**: Spring (Mar/Apr) and Fall (Oct) peaks (post-holiday rehab needs, post-summer accident recovery)

### Hourly ER Occupancy Pattern
ER occupancy varies dramatically by hour (not uniformly distributed):
- **Low**: 4am (38% occupancy, discharge zone)
- **Morning Rise**: 6am–10am (40%→65%, walk-ins, scheduled admissions)
- **Midday**: 10am–2pm (80%→89%, peak occupancy)
- **Afternoon**: 2pm–6pm (93%→95%, highest stress, Friday peak)
- **Evening/Night**: 6pm–4am (70%→38%, gradual decline)

**Day-of-Week Multiplier**:
- Friday: 1.04× (busiest day)
- Monday–Thursday: 1.00×
- Saturday: 0.99×
- Sunday: 0.96× (lowest)

---

## 5. Key Metrics & Calculations

### Admission-Related
- **Admission Rate**: Probability a patient is admitted vs. discharged from ED (specialty-dependent: 12%–96%)
- **LOS (Length of Stay)**: Average time in hospital (1.2 days pediatric → 21 days rehab) ± 30% variance
- **Admission Hour**: Time of day admission occurred (concentrated in morning 6–10am for cardiac; spread for others)
- **Discharge Hour**: Time of day discharge occurred (morning bias for all specialties)

### Occupancy & Capacity
- **ER Occupancy %**: Calculated as (admissions in hour window / ED beds) × 100
- **Occupancy Stress**: Periods >90% occupancy indicate operational stress
- **Surge Capacity**: Weekend & off-hours occupancy typically 10–15% lower

### Diagnostic Volume
- **Diagnoses per Encounter**: 2–8 diagnoses (primary + secondary)
- **Diagnosis Specialty Routing**: ICD-10 codes weighted by hospital type (e.g., cardiac hospital sees 60% cardiac diagnoses vs. 10% for general hospital)
- **DRG Calculation**: Diagnosis + LOS + age → simulated charge amount (E&M multiplier: $150–$5,000)

---

## 6. Data Quality Notes

### What This Data Represents
✅ **Realistic**: Monthly seasonality, hourly stress patterns, specialty-specific admission rates, diagnosis routing  
✅ **Synthetic**: Generated via statistical models based on CDC/AHA/NIH real-world data  
✅ **Complete**: No missing values, no nulls in critical fields  
✅ **Consistent**: Referential integrity maintained across all tables  

### What This Data Does NOT Represent
❌ **Real Patients**: No actual medical histories, no clinical context beyond diagnosis codes  
❌ **Outcomes**: No mortality, no readmissions, no quality flags  
❌ **Clinical Workflows**: No nursing notes, vitals, imaging results, pharmacy orders  
❌ **Financial**: No claims processing, no payer information, no insurance verification  
❌ **Staffing**: No nurse/physician schedules, no care team assignments  

### Data Generation Assumptions
- **Uniform patient age distribution** within specialty (pediatric 0–18, adult 18–89)
- **Geographic distribution** based on primary hospital ZIP codes
- **Diagnosis codes** are specialty-weighted random samples (not causally related)
- **Admission timing** follows specialty-specific hour distributions (not individual-level logic)
- **Charges** are DRG-estimated, not actual billing

---

## 7. Common Analytical Questions & Approaches

### Operational Analytics (Supported)
✅ **"How many ER visits do we have on Friday 2–6pm?"**
```
Filter: ENCOUNTER_DATE.dayofweek = Friday AND ADMISSION_TIME IN (14–18)
Query: SUM(1) grouped by HOSPITAL_ID
Expected: Highest occupancy period, ~90%+ capacity stress
```

✅ **"Which hospital had the most admissions in January?"**
```
Filter: MONTH(ENCOUNTER_DATE) = 1
Query: SUM(1) grouped by HOSPITAL_ID, SPECIALTY_TYPE
Expected: Pediatric & Cardiac peaks (1.35× and 1.38×)
```

✅ **"What's the average LOS by hospital specialty?"**
```
Query: AVG(ADMISSIONS.LOS) grouped by HOSPITALS.SPECIALTY_TYPE
Expected: Pediatric 1.2d, Cardiac 3.5d, Cancer 7.4d, Rehab 21d
```

✅ **"How many cancer patients are admitted vs. ED-only?"**
```
Filter: Diagnoses contain cancer ICD-10 codes (C00–C97)
Query: COUNT(ADMISSIONS) / COUNT(ENCOUNTERS) by specialty
Expected: Cancer ~96% admission rate
```

✅ **"Top 10 diagnoses by hospital type?"**
```
Query: SUM(1) for diagnoses, grouped by SPECIALTY_TYPE, ORDER BY count DESC
Expected: Cardiac hospital: MI, HF, Arrhythmia; Pediatric: RSV, Otitis, Asthma
```

### Seasonal Analysis (Supported)
✅ **"Show monthly encounter trends for 2025"**
```
Query: SUM(encounters) grouped by MONTH(ENCOUNTER_DATE), SPECIALTY_TYPE
Expected: Winter peaks (Jan 1.3–1.4×), summer dips (Jul 0.85–0.94×)
```

✅ **"When is our ER most crowded?"**
```
Query: Calculate occupancy % by ADMISSION_HOUR, DayOfWeek
Expected: Friday 2–6pm peaks at 93–95%; Sunday 4am low ~38%
```

### Clinical Analytics (NOT Supported – Limited Data)
❌ **"What's our readmission rate?"** (No readmission tracking)  
❌ **"How many patients have sepsis complications?"** (No outcomes/complications)  
❌ **"What medications did we prescribe?"** (No pharmacy data)  
❌ **"Show patient vital signs over time"** (No vitals data)  

---

## 8. Query Patterns & Best Practices

### Standard Joins
```sql
-- Encounter with hospital & department info
SELECT 
  e.ENCOUNTER_ID, e.ENCOUNTER_DATE, e.ADMISSION_TIME,
  h.HOSPITAL_NAME, h.SPECIALTY_TYPE,
  d.DEPARTMENT_NAME
FROM ENCOUNTERS e
  JOIN HOSPITALS h ON e.HOSPITAL_ID = h.HOSPITAL_ID
  JOIN DEPARTMENTS d ON e.DEPARTMENT_ID = d.DEPARTMENT_ID
```

```sql
-- Admission with diagnosis
SELECT 
  a.ADMISSION_ID, a.LOS,
  dg.ICD10_CODE, dg.DIAGNOSIS_DESC
FROM ADMISSIONS a
  JOIN DIAGNOSES dg ON a.ENCOUNTER_ID = dg.ENCOUNTER_ID
WHERE dg.IS_PRIMARY = 1
```

### Performance Tips
- **Filter by date range first** (400 days total, index on ENCOUNTER_DATE)
- **Group by SPECIALTY_TYPE or HOSPITAL_ID** for aggregations
- **Use DAY(ENCOUNTER_DATE), MONTH(), YEAR()** for temporal analysis
- **ADMISSION_HOUR** (0–23) for intra-day patterns

### Aggregation Examples
```sql
-- ER occupancy by hour
SELECT 
  DATEPART(HOUR, ADMISSION_TIME) AS HOUR,
  COUNT(*) AS VISIT_COUNT,
  AVG(LOS) AS AVG_LOS_HOURS
FROM ENCOUNTERS
WHERE DEPARTMENT_ID IN (SELECT DEPARTMENT_ID FROM DEPARTMENTS WHERE DEPARTMENT_TYPE = 'ED')
GROUP BY DATEPART(HOUR, ADMISSION_TIME)
ORDER BY HOUR
```

```sql
-- Admission rate by specialty (admission vs. ED discharge)
SELECT 
  h.SPECIALTY_TYPE,
  COUNT(DISTINCT a.ADMISSION_ID) AS ADMITTED,
  COUNT(DISTINCT e.ENCOUNTER_ID) AS TOTAL_VISITS,
  CAST(COUNT(DISTINCT a.ADMISSION_ID) AS FLOAT) / COUNT(DISTINCT e.ENCOUNTER_ID) AS ADMISSION_RATE
FROM ENCOUNTERS e
  LEFT JOIN ADMISSIONS a ON e.ENCOUNTER_ID = a.ENCOUNTER_ID
  JOIN HOSPITALS h ON e.HOSPITAL_ID = h.HOSPITAL_ID
GROUP BY h.SPECIALTY_TYPE
```

---

## 9. Dataset Generation Methodology

For context on data reliability:

- **Data Source**: Synthetic, generated via Python with real-world statistical parameters
- **Parameters Sourced From**: CDC NHAMCS, American Hospital Association (AHA), NIH, NCI SEER, APTA, ACEP
- **Monthly Seasonality**: ICD-10 diagnosis code weights multiplied by month factors
- **Admission Rates**: Specialty-specific probabilities applied probabilistically
- **Admission Timing**: Hour distributions derived from real-world ED arrival patterns by specialty
- **ER Occupancy**: Modeled as sine curve (low 4am, peak 2–6pm) with day-of-week adjustment
- **Patient Distribution**: Uniform age within specialty, geographically distributed by hospital ZIP code

**See also**: `HOSPITAL_SEASONALITY_AND_OCCUPANCY_ANALYSIS.md` and `IMPLEMENTATION_SUMMARY.md` for detailed methodology documentation.

---

## 10. Fabric Data Agent – Recommended Behaviors

When answering questions, consider:

1. **Acknowledge Seasonality**: "In January, this hospital typically experiences a 1.35× seasonal surge"
2. **Flag Operational Stress**: "Friday 2–6pm shows 93–95% ER occupancy – operational stress zone"
3. **Clarify Data Limitations**: "This is synthetic data; diagnosis codes are not causally linked to real clinical outcomes"
4. **Suggest Comparable Metrics**: "We don't have readmission data, but we can analyze LOS variance and admission patterns"
5. **Provide Context**: "Pediatric hospital admission rate of 12% reflects observation-dominant pediatric ED visits"

---

## 11. Quick Reference – Key Tables & Columns

| Table | Purpose | Key Columns |
|---|---|---|
| HOSPITALS | Hospital directory | HOSPITAL_ID, SPECIALTY_TYPE, TOTAL_BEDS |
| PATIENTS | Patient master | PATIENT_ID, AGE, PRIMARY_HOSPITAL_ID |
| ENCOUNTERS | All visits (ED & inpatient) | ENCOUNTER_DATE, ADMISSION_TIME, LOS |
| ADMISSIONS | Admitted patient subset | ADMISSION_DATE, DISCHARGE_DATE, LOS, ADMISSION_HOUR |
| DIAGNOSES | Diagnosis codes per encounter | ICD10_CODE, IS_PRIMARY |
| DEPARTMENTS | Ward/unit directory | DEPARTMENT_NAME, DEPARTMENT_TYPE, BED_COUNT |
| WEATHER | Daily weather context | WEATHER_DATE, TEMPERATURE_HIGH, PRECIPITATION_MM |

---

## 12. Contact & Updates

- **Dataset Version**: 2.0 (Hospital Specialization + Real-World Seasonality)
- **Last Updated**: February 4, 2026
- **Data Span**: January 1, 2025 – February 4, 2026 (400 days)
- **Total Rows**: ~6.5M (1.8M encounters + 300k admissions + 2.4M diagnoses + supporting tables)

For detailed implementation notes, see `IMPLEMENTATION_SUMMARY.md`. For gap analysis vs. clinical EHR systems, see `EPIC_COMPARISON_AND_GAP_ANALYSIS.md`.

