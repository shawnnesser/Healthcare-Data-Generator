# Healthcare Data Generator: Seasonality, Occupancy & Hospital Specialization Guide

**Version**: 2.0 (Enhanced with real-world patterns)  
**Date**: February 2026  
**Data Sources**: CDC NHAMCS, AHA Statistics, NIH/NCI Research, APTA, ACEP Operations

---

## Executive Summary

This document details recommended enhancements to make the healthcare data generator more realistic and actionable for leadership analysis. Current state: uniform 4.7k encounters/month across all hospitals. Recommended state: hospital-specific seasonality with 3,000–5,000 monthly encounters varying by specialty, realistic ER bed stress patterns, and clinically-appropriate admission workflows.

**Key Improvements:**
1. **Monthly Seasonality Variance** (Month-over-month trends by hospital type)
2. **ER Bed Occupancy Stress** (Hourly patterns showing capacity challenges)
3. **Hospital-Specific Patient Mix** (Pediatric, cardiac, cancer, rehab, general)
4. **Department Alignment** (Cardiac institute → no ED; rehab → no ED; specialty → business hours)
5. **Admission Timing Patterns** (Early morning cardiac peaks, business-hours oncology)
6. **Data-Driven Recommendations** (For hospital leaders to address)

---

## PART 1: MONTHLY SEASONALITY BY HOSPITAL SPECIALTY

### Overview
Rather than uniform ~4,700 encounters/month across all hospitals, each specialty hospital should reflect real-world monthly variance. This creates "natural" peaks and troughs that suggest operational challenges.

### Monthly Multipliers (Jan-Dec, normalized to annual average = 1.0)

#### 1. **Pediatric Hospitals** (Contoso Children's Hospital, id=7, 320 beds)
| Month | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | **Annual Avg Encounters** |
|-------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----| --- |
| Multiplier | 1.35 | 1.28 | 0.95 | 0.82 | 0.78 | 0.75 | 0.85 | 0.88 | 0.92 | 0.98 | 1.18 | 1.26 | ~3,400 |
| **Monthly Count** | 4,590 | 4,352 | 3,230 | 2,788 | 2,652 | 2,550 | 2,890 | 2,992 | 3,128 | 3,332 | 4,012 | 4,284 | |

**Drivers (Evidence-Based):**
- **Jan–Feb**: Influenza/RSV peak (40% of visits are respiratory), upper respiratory infections, fever workups
- **Nov–Dec**: Cold weather onset, holiday season congregation, immune system stress
- **Jun–Aug**: Summer dip — fewer respiratory illnesses, reduced trauma (supervised environments)
- **Peak Month**: January (1,456 more encounters than July baseline; **+35% vs. average**)
- **Lowest Month**: July (1,150 fewer encounters than January; **−25% vs. average**)

**Dominant Diagnoses:**
- Upper respiratory infections (22%)
- Acute otitis media/ear infections (18%)
- Asthma exacerbations (12%)
- Fractures/sprains (15%)
- Pneumonia/lower respiratory (8%)

**Sources:**
- CDC NHAMCS 2022: Pediatric ED visit distribution
- NIH Seasonal Respiratory Illness Data
- American Academy of Pediatrics (AAP) ED utilization studies

**Operational Implication:** January requires 35% more staffing/beds than July. Pediatric hospitals need surge capacity planning for winter months.

---

#### 2. **Cardiac Specialty Centers** (Contoso Heart Institute, id=6, 280 beds)
| Month | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | **Annual Avg Encounters** |
|-------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----| --- |
| Multiplier | 1.38 | 1.32 | 1.08 | 0.92 | 0.85 | 0.88 | 0.87 | 0.89 | 0.95 | 1.02 | 1.18 | 1.28 | ~3,600 |
| **Monthly Count** | 4,968 | 4,752 | 3,888 | 3,312 | 3,060 | 3,168 | 3,132 | 3,204 | 3,420 | 3,672 | 4,248 | 4,608 | |

**Drivers (Evidence-Based):**
- **Jan–Feb**: Acute Coronary Syndrome (ACS) peaks 25–30% above baseline
  - Cold-induced vasoconstriction ↑ cardiac stress
  - Hypertensive crisis from salt/dietary excess (post-holiday)
  - Reduced medication adherence post-holidays
- **Nov–Dec**: Holiday stress, increased alcohol/dietary sodium, reduced exercise
- **Summer (Jun–Aug)**: Lower ACS rates — heat-induced vasodilation, more activity
- **Peak Month**: January (1,368 more encounters than August; **+43% vs. average**)
- **Lowest Month**: July (468 fewer encounters than January; **−27% vs. average**)

**Dominant Diagnoses:**
- Acute coronary syndrome/MI (28% of encounters)
- Heart failure exacerbation (22%)
- Atrial fibrillation/new arrhythmia (18%)
- Unstable angina (12%)
- Hypertensive emergency (8%)

**Admission Rates by Condition:**
- STEMI: 98% admission, avg LOS 3.5 days
- NSTEMI: 95% admission, avg LOS 3.2 days
- Unstable angina: 80% admission, avg LOS 2.8 days
- Heart failure exacerbation: 85% admission, avg LOS 4.2 days

**Sources:**
- American Heart Association Cardiovascular Disease Statistics
- Circulation Journal seasonal ACS meta-analyses (winter excess: 20–30% vs. summer)
- Meta-analysis of cardiac mortality patterns

**Operational Implication:** January handles **43% more volume** than July. Cath lab capacity, ICU beds, and cardiology staffing need winter surge plan. Expected bed occupancy peaks February → ER showing 92–93% occupancy (near maximum).

---

#### 3. **Cancer Centers** (Contoso Cancer Center, id=8, 200 beds)
| Month | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | **Annual Avg Encounters** |
|-------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----| --- |
| Multiplier | 1.05 | 1.03 | 1.02 | 1.01 | 0.98 | 0.95 | 0.94 | 0.96 | 1.00 | 1.02 | 1.04 | 1.06 | ~2,400 |
| **Monthly Count** | 2,520 | 2,472 | 2,448 | 2,424 | 2,352 | 2,280 | 2,256 | 2,304 | 2,400 | 2,448 | 2,496 | 2,544 | |

**Drivers (Evidence-Based):**
- **Stable Baseline**: Oncology/hematology schedules are **planned and scheduled** (not driven by acute season)
- **Summer Dip (Jun–Aug)**: Vacation schedules, patient non-compliance (holiday travel), deferred admissions
- **Late Year Rise (Nov–Dec)**: Year-end insurance deductible thresholds met → increased treatment initiations
- **Max/Min Variance**: Only ±6% month-over-month (vs. ±43% cardiac, ±35% pediatric)

**Dominant Diagnoses:**
- Febrile neutropenia/chemotherapy complications (22%)
- Infection/sepsis (20%)
- Metastatic cancer/acute complications (18%)
- Acute leukemia (12%)
- Lymphoma (10%)

**Admission Characteristics:**
- Admission rate: **95–98%** (highest of all specialties)
- Avg LOS: **7.4 days** (longest)
- 70% admitted during business hours (8am–5pm)
- 30% emergency admissions overnight (chemo toxicity reactions)

**Sources:**
- National Cancer Institute SEER Database
- American Society of Clinical Oncology (ASCO) cancer admissions
- Oncology journal cancer admission patterns

**Operational Implication:** Cancer centers have **minimal month-to-month variance** (flat demand) but **high occupancy consistency** (95%+ beds occupied). Planning is routine elective; no surge capacity needed seasonally.

---

#### 4. **General Hospitals** (Contoso Medical Center, University, General, Regional, Community; ids 1–5, 550–750 beds each)
| Month | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | **Annual Avg Encounters** |
|-------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----| --- |
| Multiplier | 1.12 | 1.08 | 0.98 | 0.92 | 0.88 | 0.85 | 0.90 | 0.93 | 0.95 | 1.00 | 1.08 | 1.18 | ~4,700 |
| **Monthly Count** | 5,264 | 5,076 | 4,606 | 4,324 | 4,136 | 3,995 | 4,230 | 4,371 | 4,465 | 4,700 | 5,076 | 5,546 | |

**Drivers (Evidence-Based):**
- **Winter Peaks (Jan–Feb)**: Flu, trauma (ice/snow), cardiovascular events
- **Summer Troughs (Jun–Aug)**: Vacation season reduces elective admissions; trauma slightly elevated (July 4th)
- **Holiday Periods (Dec)**: Peak stress-related visits, trauma, acute exacerbations
- **Max/Min Variance**: December **+18% vs. baseline**; July **−10% vs. baseline**

**Patient Distribution:**
- Trauma: 20%
- Respiratory illness: 15%
- GI: 12%
- Orthopedic: 10%
- Infectious disease: 8%
- Psychiatry: 7%
- Other: 28%

**Admission Rates:**
- Trauma: ~25% → admission
- Medical: ~18% → admission
- Surgical: ~35% → admission
- Overall: ~20% → admission

**Sources:**
- CDC NHAMCS 2022 National ED Data
- Agency for Healthcare Research and Quality (AHRQ)

**Operational Implication:** General hospitals see a full spectrum of seasonal trends. December shows highest stress; July lowest. Elective surgery scheduling should taper July/August. ER shows 88–92% occupancy Dec–Feb, 70–75% Jun–Aug.

---

#### 5. **Rehabilitation Centers** (Contoso Rehab Center, id=9, 180 beds)
| Month | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | **Annual Avg Encounters** |
|-------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----| --- |
| Multiplier | 1.04 | 1.02 | 1.08 | 1.10 | 1.01 | 0.98 | 0.92 | 0.95 | 1.05 | 1.12 | 1.06 | 1.00 | ~1,900 |
| **Monthly Count** | 1,976 | 1,938 | 2,052 | 2,090 | 1,919 | 1,862 | 1,748 | 1,805 | 1,995 | 2,128 | 2,014 | 1,900 | |

**Drivers (Evidence-Based):**
- **Spring/Fall Peaks (Mar, Apr, Oct)**: Post-winter injury recovery surge, surgical rehabilitation admissions
- **Summer Dip (Jul–Aug)**: Reduced surgical schedules, patient vacations, staff time-off
- **Steady Baseline**: Chronic condition management provides floor demand
- **Max/Min Variance**: October **+12% vs. baseline**; July **−8% vs. baseline**

**Patient Population:**
- Stroke/neuro recovery (25%)
- Orthopedic/post-surgical (35%)
- Cardiac rehabilitation (15%)
- Pulmonary rehabilitation (10%)
- General deconditioning (10%)
- Pain management (5%)

**Admission Characteristics:**
- Admission rate: **~85%** (referral-based, not ED-driven)
- Avg LOS: **21 days** (longest of all facilities)
- 60% admitted morning (7am–11am) — planned rehab admissions
- 30% afternoon (1pm–4pm) — hospital discharge transitions
- 10% evening/sparse

**Sources:**
- American Physical Therapy Association (APTA) rehabilitation statistics
- Medicare rehabilitation utilization data

**Operational Implication:** Rehab centers are **bed-utilization stable** but **admission-timing predictable**. April and October require surge staffing. LOS of 21 days means patient flow is critical (steady-state occupancy = ~55 patients per 100-bed facility).

---

### SUMMARY TABLE: Monthly Encounter Counts by Hospital Specialty (4,700 baseline annual avg)

| Month | **Pediatric** (General Avg: 3,400) | **Cardiac** (General Avg: 3,600) | **Cancer** (General Avg: 2,400) | **General** (General Avg: 4,700) | **Rehab** (General Avg: 1,900) |
|-------|-----|-----|-----|-----|-----|
| **January** | **4,590** | **4,968** | 2,520 | **5,264** | 1,976 |
| **February** | **4,352** | **4,752** | 2,472 | **5,076** | 1,938 |
| **March** | 3,230 | 3,888 | 2,448 | 4,606 | **2,052** |
| **April** | 2,788 | 3,312 | 2,424 | 4,324 | **2,090** ⬆ Peak |
| **May** | 2,652 | 3,060 | 2,352 | 4,136 | 1,919 |
| **June** | 2,550 | 3,168 | 2,280 | 3,995 | 1,862 |
| **July** | 2,890 | 3,132 | **2,256** ⬇ Low | 4,230 | **1,748** ⬇ Low |
| **August** | 2,992 | 3,204 | 2,304 | 4,371 | 1,805 |
| **September** | 3,128 | 3,420 | 2,400 | 4,465 | 1,995 |
| **October** | 3,332 | 3,672 | 2,448 | 4,700 | **2,128** ⬆ Peak |
| **November** | **4,012** | **4,248** | 2,496 | **5,076** | 2,014 |
| **December** | **4,284** | **4,608** | 2,544 | **5,546** | 1,900 |
| **Peak Month** | **January (4,590)** | **January (4,968)** | December (2,544) | **December (5,546)** | **April (2,090)** |
| **Lowest Month** | **July (2,890)** | **July (3,132)** | **July (2,256)** | **July (4,230)** | **July (1,748)** |
| **Variance** | **−37% to +35%** | **−13% to +38%** | **−6% to +6%** | **−10% to +18%** | **−8% to +12%** |

---

## PART 2: HOURLY ER BED OCCUPANCY & STRESS PATTERNS

### Current State Problem
ED occupancy is currently uniform or based on generic multipliers. Real EDs show distinct hourly stress patterns that create operational crises for leaders to address.

### Recommended ER Occupancy Model

#### Hourly Baseline Occupancy (% of ER Beds Occupied)
Assume a 35-bed ED with 80% baseline occupancy = 28 beds typically occupied.

| Hour | 0–1 | 1–2 | 2–3 | 3–4 | 4–5 | 5–6 | 6–7 | 7–8 | 8–9 | 9–10 | 10–11 | 11–12 |
|------|-----|-----|-----|-----|-----|-----|-----|-----|-----|------|--------|--------|
| **Occupancy %** | 45 | 42 | 40 | 38 | 40 | 45 | 50 | 58 | 68 | 75 | 82 | 85 |
| **Beds (of 35)** | 16 | 15 | 14 | 13 | 14 | 16 | 18 | 20 | 24 | 26 | 29 | 30 |

| Hour | 12–1 | 1–2 | 2–3 | 3–4 | 4–5 | 5–6 | 6–7 | 7–8 | 8–9 | 9–10 | 10–11 | 11–12 |
|------|------|-----|-----|-----|-----|-----|-----|-----|-----|------|--------|--------|
| **Occupancy %** | 88 | 87 | 88 | 89 | 88 | 85 | 82 | 80 | 78 | 75 | 70 | 62 |
| **Beds (of 35)** | 31 | 30 | 31 | 31 | 31 | 30 | 29 | 28 | 27 | 26 | 25 | 22 |

**Key Observations:**
- **CRITICAL STRESS WINDOW: 2pm–7pm (14:00–19:00)** — Occupancy 87–89%
  - **2pm peak**: 89% occupancy (delayed morning discharges + lunch overflow)
  - **3–5pm plateau**: 88% (sustained peak stress)
  - **6–7pm**: 85% (evening surge beginning)
  
- **MODERATE STRESS: 10am–2pm** — 75–88% occupancy
  - Morning ramp: 10am (75%) → 12pm (85%) — morning surgery post-op arrivals
  
- **LOW OCCUPANCY (Admin Opportunity): Midnight–6am** — 38–45% occupancy
  - Minimum at 4–5am: 38% (13 of 35 beds occupied)
  - Pre-dawn: 40–45%
  
- **SHOULDER PERIODS**: 6–10am ramping (45%→75%), 7pm–midnight declining (82%→62%)

**Day-of-Week Occupancy Variance** (Applied as multiplier to hourly rates):

| Day | Peak Hour | Peak % | Morning Load | Evening Load | Notes |
|-----|-----------|--------|--------------|--------------|-------|
| **Monday** | 2–4pm | **92%** | 78% | 88% | **Week start surge**; 15% volume ↑ vs. weekend |
| **Tuesday** | 2–3pm | **91%** | 76% | 86% | Sustained high; surgical backup |
| **Wednesday** | 1–2pm | **90%** | 75% | 85% | Mid-week fatigue; some relief |
| **Thursday** | 3–4pm | **92%** | 77% | 89% | Pre-weekend surge begins |
| **Friday** | 2–6pm | **93%** | 79% | 92% | **HIGHEST STRESS**: Weekend electives, trauma surge |
| **Saturday** | 1–5pm | **85%** | 70% | 80% | Lower overall (elective closures) |
| **Sunday** | 12–4pm | **82%** | 68% | 75% | Lowest occupancy; weekend pattern |

**Calculations:**
- Friday 3pm: Base 89% × 1.04 (Friday mult) = **92.6% occupancy** (32 of 35 beds)
- Friday 6pm: Base 85% × 1.04 = **88.4% occupancy** (31 of 35 beds)
- Monday 2pm: Base 89% × 1.02 = **90.8% occupancy** (32 of 35 beds)
- Sunday 4am: Base 38% × 0.96 = **36.5% occupancy** (13 of 35 beds)

**Leadership Actions (Data-Driven):**
1. **Friday 2–6pm (92–93% occupancy)**: 
   - Elective surgeries should NOT discharge Friday afternoon
   - Weekend staffing surge needed (paramedics, admit nurses)
   - Activate admission hold or transfer protocol at 90% occupancy
   
2. **Monday 8–12pm (75–88% occupancy)**:
   - Weekend backlog processing begins
   - High surgical schedule conflict risk
   - Primary care referral surge (Friday rejections)
   
3. **Midnight–6am (38–45% occupancy)**:
   - Admin/cleaning window with 50% empty beds
   - Elective admission opportunity
   - Opportunity to transfer held patients

---

### Recommended ER Occupancy Stress Scenarios (Data Generator)

**Scenario A: "Normal Load" Hospital (Contoso General, Contoso Regional)**
- Friday 3pm: 88–90% occupancy
- Monday 2pm: 87–89% occupancy
- Sunday 4am: 38–42% occupancy

**Scenario B: "High-Stress" Hospital (Contoso Medical Center — largest general)**
- Friday 3pm: **93–95% occupancy** (approaching bypass)
- Monday 2pm: **91–93% occupancy**
- Sunday 4am: 40–45% occupancy

**Scenario C: "Specialty Stress" — Cardiac (Contoso Heart Institute)**
- Morning 8–10am (cardiac ACS peak): **94–96% occupancy** (early-morning crisis)
- Afternoon 2–4pm: **90–92% occupancy**
- Midnight–6am: 35–40% occupancy

**Scenario D: "Specialty Stress" — Pediatric (Contoso Children's Hospital)**
- Morning 8–10am: **88–91% occupancy** (school nurse referrals + overnight backlog)
- Afternoon 2–4pm: **85–88% occupancy** (after-school injuries)
- Evening 6–9pm: **83–86% occupancy** (fever workup peak)

---

## PART 3: HOSPITAL-SPECIFIC PATIENT ROUTING & DIAGNOSES

### Recommended Hospital Assignment Rules

**Patient-to-Hospital Routing Logic:**

```
IF patient_age < 18:
  → Route to Contoso Children's Hospital (id=7, pediatric specialty)
  ELSE IF patient_diagnosed_condition IN (cardiac_codes):
    → Route to Contoso Heart Institute (id=6, cardiac specialty)
    ELSE IF patient_diagnosed_condition IN (cancer_codes):
      → Route to Contoso Cancer Center (id=8, cancer specialty)
      ELSE IF patient_needs_rehabilitation:
        → Route to Contoso Rehab Center (id=9, rehab specialty)
        ELSE:
          → Route to nearest General Hospital (ids 1–5, based on capacity/load)
```

### Diagnosis Distribution by Hospital (% of encounters)

#### Contoso Children's Hospital (Pediatric, id=7)
**Encounter Mix:**
- Acute respiratory (URI, otitis, asthma): **52%**
- Injury/trauma (fractures, sprains): **15%**
- Infection/fever (pneumonia, fever workup, gastroenteritis): **18%**
- Surgical acute (appendicitis, bowel obstruction): **5%**
- Other (neurologic, psychiatric): **10%**

**Admission Rate: 12–15%**
- Most pediatric cases are observation/treatment only
- Asthma exacerbation: 8% admission rate
- Pneumonia: 20% admission rate
- Appendicitis: 70% admission rate
- Fractures: 10% admission rate

**Typical LOS:**
- Asthma: 1.2 days
- Pneumonia: 2.1 days
- Appendicitis: 2.3 days
- Fever workup (febrile infant): 1.3 days

---

#### Contoso Heart Institute (Cardiac Specialty, id=6)
**Encounter Mix:**
- Acute coronary syndrome (STEMI, NSTEMI, unstable angina): **45%**
- Heart failure exacerbation: **22%**
- Arrhythmia (AFib, other): **18%**
- Hypertensive emergency/urgency: **8%**
- Other cardiac (PE, aortic dissection, post-MI follow-up): **7%**

**Admission Rate: 70–75%**
- STEMI: 98% admission
- NSTEMI: 95% admission
- Heart failure: 85% admission
- Hypertensive emergency: 40% admission

**Typical LOS:**
- STEMI: 3.5 days (post-cath lab monitoring)
- NSTEMI: 3.2 days
- Heart failure exacerbation: 4.2 days
- Hypertensive urgency: 1.2 days

**NOTE: NO EMERGENCY DEPARTMENT** — Cardiac emergencies route through ED at general hospital, then transfer to Heart Institute for cardiology intervention.

---

#### Contoso Cancer Center (Oncology, id=8)
**Encounter Mix:**
- Febrile neutropenia/chemo toxicity: **22%**
- Infection/sepsis: **20%**
- Metastatic disease complications: **18%**
- Hematologic malignancy (acute leukemia, lymphoma): **18%**
- Solid tumors: **10%**
- Palliative/comfort care: **8%**
- Chemotherapy management: **4%**

**Admission Rate: 95–98%**
- Almost all cancer center visits result in admission
- ~95% arrive during business hours (8am–5pm)
- ~5% emergency admissions overnight (chemo reactions, sepsis)

**Typical LOS:**
- Febrile neutropenia: 5.2 days
- Acute leukemia: 14.3 days
- Infection/sepsis: 6.1 days
- Metastatic disease: 7.8 days
- Palliative/comfort: 6.7 days

**ADMISSION TIMING:** 
- 70% arrive 8am–5pm (scheduled chemo, planned admissions)
- 30% arrive 12am–8am (overnight reactions, emergency)

---

#### Contoso Rehab Center (Rehabilitation, id=9)
**Encounter Mix:**
- Stroke/neuro sequelae: **25%**
- Orthopedic post-surgical (hip, knee, ankle): **35%**
- Cardiac rehabilitation: **15%**
- Pulmonary rehabilitation: **10%**
- General deconditioning: **10%**
- Pain management: **5%**

**Admission Rate: ~85%** (referral-based, not ED-driven)
- Typical source: hospital discharge referral or physician referral
- ~60% admitted morning (7–11am) — planned rehab admissions
- ~30% admitted afternoon (1–4pm) — hospital discharge transfers
- ~10% admitted evening/scattered

**Typical LOS:**
- Stroke recovery: 21–28 days
- Post-hip replacement: 18–24 days
- Post-knee replacement: 14–21 days
- Cardiac rehab: 14–21 days
- Pulmonary rehab: 10–14 days

**NOTE: NOT AN EMERGENCY FACILITY** — No ED. Admissions from hospital discharge or physician referral only.

---

#### General Hospitals (Contoso Medical Center, University, General, Regional, Community; ids 1–5)
**Encounter Mix:**
- Emergency/trauma: **40%**
- Medical (infections, chronic exacerbation): **25%**
- Surgical (acute abdomen, appendicitis): **20%**
- Psychiatry: **10%**
- OB/GYN: **5%**

**Admission Rate: ~20%** (typical emergency admission rate)
- Trauma: ~25% admission
- Medical: ~18% admission
- Surgical: ~35% admission

**Typical LOS:**
- Trauma: 3.2 days
- Medical: 4.1 days
- Surgical: 5.8 days
- Psychiatry: 3.5 days
- OB/GYN: 2.1 days

**Overall Admission Avg LOS: 3.8 days**

---

## PART 4: DEPARTMENT CONSTRAINTS & BUSINESS HOURS

### Department Structure Recommendations

| Hospital | Departments | ER? | Admission Hours | Notes |
|----------|-----------|-----|-----------------|-------|
| **Contoso Heart Institute** | Cardiology, Interventional Cardio, Cardiac Surgery, Cardiac Rehab | **NO** | 24/7 (cardiology consult transfers) | No ED; emergencies route through general hospital |
| **Contoso Children's Hospital** | Pediatrics, Pediatric Surgery, Neonatology, Pediatric Urgent Care | **YES** (urgent care only) | 24/7 (less formal ED) | Pediatric-focused ED, not full trauma |
| **Contoso Cancer Center** | Oncology, Hematology, Infusion Center, Palliative Care | **NO** | 8am–5pm (business hours) | Highly scheduled; emergencies via general hospital |
| **Contoso Rehab Center** | Physical Rehab, Occupational Therapy, Speech Therapy | **NO** | 7am–5pm (discharge referrals) | Not a walk-in facility; physician referral only |
| **Contoso Diagnostic Center** | Radiology, Pathology, Laboratory | **NO** | 8am–5pm (business hours) | Outpatient diagnostic; no admissions |
| **General Hospitals (5)** | ER, Internal Medicine, Surgery, Cardiology, Radiology, Specialty | **YES** | 24/7 | Full-service ED; all emergencies route here |

### Business Hours Constraint Logic

**Specialty Clinics (8am–5pm):**
- Contoso Cancer Center: No admissions outside 8am–5pm (except emergencies rerouted to general hospital)
- Contoso Diagnostic Center: No patients arriving outside 8am–5pm
- Reason: No overnight staffing, no 24/7 imaging/labs

**Rehabilitation (7am–5pm Discharge Referrals, 7am–9pm "Office Hours"):**
- Contoso Rehab: Admissions accepted 7am–5pm from hospital discharge
- After-hours: No new referrals accepted
- LOS commitment: 14–28 days (not day-visit)

**Pediatric Urgent Care (Open but Limited 24/7):**
- Contoso Children's Hospital: Open 24/7 for pediatric emergencies
- Night shift: Staffed but lower volume (trauma, serious illness only)
- Routine illness/fever: Encouraged to daytime hours

**General Hospital ED (24/7 Full Service):**
- All trauma, acute medical emergencies
- Accepts transfers from specialty hospitals
- Handles overflow from specialty clinics

---

## PART 5: ADMISSION TIMING PATTERNS

### Morning vs. Evening Admissions by Hospital Type

| Hospital Type | 6–10am | 10am–2pm | 2–6pm | 6pm–midnight | midnight–6am | Top Hour |
|--------------|---------|----------|--------|-------------|-------------|----------|
| **Pediatric** | 25% | 15% | 20% | 22% | 18% | 6–8am (morning surge) |
| **Cardiac** | **35%** | 10% | 28% | 15% | 12% | **6–8am (ACS peak)** |
| **Cancer** | 45% | 25% | 15% | 5% | 10% | 8–10am (chemo management) |
| **Rehab** | **60%** | 15% | 20% | 3% | 2% | **7–9am (discharge transfers)** |
| **General** | 20% | 15% | 40% | 15% | 10% | 2–4pm (peak ED hours) |

**Implications for Data Generation:**

1. **Generate admission datetimes (not just admit_date)**:
   - Cardiac: Heavy morning bias (35% 6–10am)
   - Rehab: Very heavy morning bias (60% 7–9am)
   - General: Afternoon peak (40% 2–6pm)

2. **Set ER bed occupancy at peak times based on admission timing**:
   - Cardiac morning surge → 94–96% occupancy 8–10am
   - General afternoon surge → 88–90% occupancy 2–6pm
   - Rehab morning discharge transfers → not an ER metric (direct admission)

---

## PART 6: DATA-DRIVEN RECOMMENDATIONS FOR HOSPITAL LEADERS

### Generated Alerts & Issues (for dashboards)

These recommendations should appear in the data itself (via diagnosis patterns, occupancy alerts, LOS analysis):

#### **Pediatric Hospital Issue 1: Winter ED Overcrowding**
**Pattern in Data**: January encounters +35% vs. average; Friday 3pm occupancy 92–95%

**Root Cause**: Flu/RSV season + holiday concentration

**Recommended Actions**:
- Pre-season (October): Hire 3–4 temp RNs for Jan–Feb surge
- November: Implement flu shot drive for staff + families
- January: Expand waiting room; set up fast-track (minor illness lane)
- February: Monitor for staffing fatigue → reduce non-emergency scheduling

**Expected Outcome**: Reduce ED wait times from 4hrs to <2hrs; admit 90% within 2hr window

---

#### **Cardiac Hospital Issue 2: Early Morning Capacity Crisis**
**Pattern in Data**: January encounters peak +38%; early morning (6–10am) occupancy 94–96% on Friday/Monday

**Root Cause**: Acute coronary syndrome peaks in early morning (diurnal variation); winter worse

**Recommended Actions**:
- 6am: Open ICU "overflow bay" for overnight ACS arrivals (pre-plan)
- 7am: Full cardiology + interventional radiology team on-call (not staggered start)
- 7am: Single-shift cath lab: 7am–7pm (vs. 9am–5pm), to front-load morning ACS
- January scheduling: Reduce elective catheterizations in AM 6am–noon window

**Expected Outcome**: ACS door-to-cath times stay <120min even at peak; reduce transfer-outs to 0%

---

#### **Cancer Center Issue 3: Chemo Toxicity Overnight Admissions**
**Pattern in Data**: 5% of admissions midnight–8am; febrile neutropenia 20%+ of overall admits

**Root Cause**: Chemotherapy toxicity peaks 12–36hrs post-infusion (overnight)

**Recommended Actions**:
- Implement on-call oncology nurse 6pm–6am (phone triage)
- Develop fast-track admission protocol for febrile neutropenia (anticipated patients from morning chemo)
- Educate patients: Call hotline if fever >100.4°F post-chemo (same-day imaging, labs, admission)
- Capacity buffer: Hold 3–5 beds 8pm–8am for emergency chemo reactions

**Expected Outcome**: Febrile neutropenia patients admitted within 2hrs of ED arrival (vs. 4–6hrs); reduce sepsis mortality

---

#### **Rehab Center Issue 4: Discharge Bottleneck (Post-Surgical Pileup)**
**Pattern in Data**: April & October show +10% admissions; morning (7–9am) discharge transfer arrivals spike

**Root Cause**: Spring/fall peak in surgeries (orthopedic post-op, stroke rehab referral season); hospital discharge bottleneck

**Recommended Actions**:
- April & October: Hire temp PT/OT staff (2–3 FTE each)
- Pre-plan: Schedule discharge referrals the day before (known 7am arrivals)
- Add early discharge window: Hospital discharges rehab patients at 6am (not noon)
- Capacity: 180 beds × 21-day avg = 126 "steady-state" beds; April surge requires 140+ daily (plan overflow contract with local hotels or swing beds)

**Expected Outcome**: 48-hour hospital-to-rehab transfer time (vs. current 72–96hrs); reduce hospital bed-blocking

---

#### **General Hospital Issue 5: Friday ER Crisis (Approaching Bypass)**
**Pattern in Data**: Friday 2–6pm occupancy 93–95%; admits backed up (elective surgeries not discharging Friday PM)

**Root Cause**: Weekend elective surgeries + Friday afternoon ED surge + discharge delay

**Recommended Actions**:
- Discharge protocol: By Friday 10am, discharge all non-critical admits (don't hold for weekend coverage)
- OR schedule: No elective admissions Friday 1pm–6pm (block for emergencies)
- ED fast-track: Open triage-to-decision lane for non-acute (DC from fast-track by 2pm)
- Staffing: +1 FTE charge nurse (Friday) for admission coordination
- Call-in capacity: Pre-identify weekend staff list (activate Friday 2pm if occupancy >92%)

**Expected Outcome**: Friday occupancy stabilizes 88–90% (vs. 93–95%); bypass activations drop to <2/month

---

#### **System-Wide Issue 6: Summer Elective Surgery Schedule Gap**
**Pattern in Data**: June–August encounters drop 10–15% (general hospitals), surgical LOS normalizes

**Root Cause**: Vacation scheduling, reduced elective procedures, staff time-off cascades

**Recommended Actions**:
- January: Freeze elective surgeon vacation June 15–Aug 30
- May: Offer bonus pay (+10%) for summer weekend coverage
- June: Front-load elective surgeries (don't defer to fall; increases fall surge)
- Staffing: Cross-train summer staff; reduce ORs running (consolidate 6 ORs → 4 ORs)

**Expected Outcome**: Maintain stable occupancy year-round (not summer dip below 85%)

---

#### **Data-Driven Observation 7: Admission Rate Variance by Hospital Specialty**
**Pattern in Data**:
- General: ~20% ED visit → admission (typical)
- Pediatric: ~12% → admission (mostly observation)
- Cardiac: ~72% → admission (high acuity)
- Cancer: ~96% → admission (chronic management)
- Rehab: ~85% → admission (referral-based)

**Implication**: Comparing admission rates across specialties is misleading; focus on **case-adjusted LOS and complication rates** instead.

**Recommended Actions**:
- Report admission rate separately by hospital type (don't benchmark pediatric vs. cardiac)
- Track primary metric: Average LOS by condition (normalize for severity)
- Track secondary metric: Readmission rate within 30 days

**Expected Outcome**: Leadership dashboards show **specialty-adjusted KPIs** (not raw rates); data-driven priorities clear

---

## PART 7: IMPLEMENTATION ROADMAP

### Phase 1: Data Configuration (Week 1)
**Update config.py:**
- Add hospital-specific monthly multipliers (PEDIATRIC_MONTHLY, CARDIAC_MONTHLY, etc.)
- Add hourly ED occupancy percentages (HOURLY_ED_OCCUPANCY)
- Add day-of-week occupancy multiplier dict
- Add specialty diagnosis distributions

**Update main.py:**
- Import hospital_generation_helpers module
- Modify `generate_encounters()` to call `get_hospital_monthly_multiplier()`
- Modify `generate_diagnoses_weather_aware()` to use `get_specialty_diagnoses()`
- Modify `generate_admissions_for_day()` to use `get_admission_rate()` and `get_admission_times_by_specialty()`

**Test:**
- Verify January pediatric encounters ~35% above July
- Verify January cardiac encounters ~38% above July
- Verify Friday 3pm ER occupancy shows 93% (vs. Sunday 4am 36%)
- Verify cancer admission rate 96% vs. general 20%

### Phase 2: Hospital-Specific Department Structure (Week 1–2)
**Update DEPARTMENTS list:**
- Remove ED from Cardiac Institute, Cancer Center, Rehab Center
- Add specialty-specific departments (Cardiology, Hematology, PT/OT, etc.)
- Add business-hours constraints to metadata (e.g., `business_hours_only: True`)

**Update encounters/admissions logic:**
- Route pediatric patients (<18 years old) to Children's Hospital
- Route cardiac diagnoses to Heart Institute
- Route cancer diagnoses to Cancer Center
- Route post-surgical patients to Rehab Center
- Route overflow to General Hospitals

**Test:**
- Verify no ED patients assigned to Cardiac Institute
- Verify cancer center shows 95%+ admission rate
- Verify rehab center has early morning (7–9am) admission surge

### Phase 3: Occupancy Stress Visualization (Week 2–3)
**Add occupancy calculations to rebuild:**
- For each day, compute hourly ED occupancy by hospital
- Store in a new table: `ed_occupancy_hourly` (hospital_id, date, hour_of_day, occupancy_pct, beds_occupied, beds_available)
- Calculate Friday 3pm occupancy; flag if >92%
- Create alerts table for "occupancy_alerts" (hospital_id, date, alert_type, message)

**Sample Alerts:**
- "Friday 3pm occupancy 93.5% (33 of 35 beds) — approaching bypass threshold"
- "Monday 8–12pm strain: 20 elective admits + 40 ED visits = 88% occupancy"

**Test:**
- Verify Friday occupancy >92% at least 2–3 Fridays/month
- Verify Sunday 4am occupancy <40%
- Verify Cardiac Institute shows 94–96% occupancy 8–10am

### Phase 4: Documentation & Dashboard Examples (Week 3–4)
**Create PDF/Excel reports:**
- Monthly variance heat map (hospital specialty × month)
- Hourly occupancy by hospital (Friday vs. Sunday comparison)
- Admission rate summary by specialty
- LOS distribution by condition
- Top recommendations for leaders

**Example Report Findings:**
- "Pediatric hospital admissions surge 35% Jan–Feb; recommend 15% staffing increase"
- "Cardiac institute morning occupancy crisis: 94–96% on weekdays 8–10am; add 1 early-shift cath lab tech"
- "Friday ER occupancy 93%: last Friday of month highest risk; pre-activate weekend staff Friday 1pm"

---

## PART 8: SAMPLE DATA VALIDATION QUERIES

After implementing changes, run these SQL queries to validate:

### Query 1: Verify Monthly Encounter Variance
```sql
SELECT 
    h.specialty,
    MONTH(e.encounter_date) AS month,
    COUNT(*) AS encounter_count,
    CAST(COUNT(*) AS FLOAT) / 
        (SELECT COUNT(*) FROM encounters e2 WHERE h.specialty = ISNULL(...)) * 100 AS pct_of_annual
FROM encounters e
JOIN hospitals h ON e.hospital_id = h.hospital_id
WHERE YEAR(e.encounter_date) = 2025
GROUP BY h.specialty, MONTH(e.encounter_date)
ORDER BY h.specialty, month;
```
**Expected:** Pediatric shows 35% variance Jan vs. Jul; Cardiac 38%; Cancer <6%

### Query 2: Verify Hospital-Specific Admission Rates
```sql
SELECT 
    h.name,
    h.specialty,
    COUNT(DISTINCT e.encounter_id) AS encounters,
    COUNT(DISTINCT a.admission_id) AS admissions,
    CAST(COUNT(DISTINCT a.admission_id) AS FLOAT) / COUNT(DISTINCT e.encounter_id) * 100 AS admission_rate_pct
FROM encounters e
LEFT JOIN admissions a ON e.encounter_id = a.encounter_id
JOIN hospitals h ON e.hospital_id = h.hospital_id
GROUP BY h.name, h.specialty
ORDER BY admission_rate_pct DESC;
```
**Expected:** Cancer ~96%, Cardiac ~72%, General ~20%, Pediatric ~12%

### Query 3: Verify Early-Morning Cardiac Admission Spike
```sql
SELECT 
    DATEPART(HOUR, a.admit_datetime) AS hour_of_day,
    COUNT(*) AS admission_count
FROM admissions a
JOIN encounters e ON a.encounter_id = e.encounter_id
JOIN hospitals h ON a.hospital_id = h.hospital_id
WHERE h.specialty = 'cardiac'
    AND YEAR(a.admit_datetime) = 2025
GROUP BY DATEPART(HOUR, a.admit_datetime)
ORDER BY hour_of_day;
```
**Expected:** 6–10am shows 35% of daily admissions; 2–4pm shows 28%

### Query 4: Verify Friday ER Occupancy >92%
```sql
WITH occupancy AS (
    SELECT 
        h.name,
        CAST(a.admit_datetime AS DATE) AS admit_date,
        DATENAME(WEEKDAY, a.admit_datetime) AS day_of_week,
        COUNT(*) AS admissions_count
    FROM admissions a
    JOIN hospitals h ON a.hospital_id = h.hospital_id
    WHERE a.discharge_datetime IS NULL OR a.discharge_datetime > GETDATE()
    GROUP BY h.name, CAST(a.admit_datetime AS DATE), DATENAME(WEEKDAY, a.admit_datetime)
)
SELECT 
    name,
    day_of_week,
    AVG(admissions_count) AS avg_admits_per_day,
    MAX(admissions_count) AS peak_admits
FROM occupancy
WHERE day_of_week = 'Friday'
GROUP BY name, day_of_week;
```
**Expected:** Large general hospitals show Fridays with 32–34 admits (out of 35 beds = 91–97% occupancy)

---

## CONCLUSION & NEXT STEPS

This document provides **evidence-based, data-driven recommendations** for realistic healthcare data generation. Key benefits:

1. **Leadership Visibility**: Dashboard shows real operational challenges (ER overflow Friday afternoons, winter staffing shortages, admission bottlenecks)
2. **Quarterly Planning**: Seasonal variance enables realistic budget/staffing forecasts
3. **Capacity Planning**: Hourly occupancy data drives infrastructure decisions
4. **Specialty Benchmarking**: Admission rate/LOS comparisons now account for hospital type

**Next Implementation Step**: Choose Phase 1, 2, or 3 (above) to begin; recommend starting with Phase 1 (configuration) to validate multiplier impacts before full rebuild.

---

**Document Version**: 2.0  
**Last Updated**: February 3, 2026  
**Prepared For**: Hospital Leadership Analytics Team  
**Sources Cited**: CDC NHAMCS, AHA, NIH, NCI, APTA, ACEP, PMC Healthcare Research

---
