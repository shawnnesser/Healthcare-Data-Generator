# Length-of-Stay Benchmarks for the Simulated Patient Journey

> Research deliverable backing the benchmark-driven length of stay (LOS) in
> `src/hospital_operations/patient_flow_simulator.py`. Every figure below is
> traceable to a published US source, and each one is graded for confidence so
> that a reader can tell a published statistic from an interpolation.
>
> **Scope:** this document informs the *ODS demo dataset only*. These are
> population-level operational benchmarks used to make synthetic timing
> plausible. They are **not** clinical guidance, not a care standard, and must
> never be presented as a prediction for any real patient.

## Why this exists

Before this work the simulator had a single constant, `_MIN_DWELL_HOURS = 2.0`,
gating readiness, transfer and discharge for every patient. Length of stay was
effectively a geometric random walk over iteration count, which made it a
function of the `SPEED_MULTIPLIER` demo knob rather than of the patient's
condition. An ED chest-pain visit and an ICU sepsis stay were timed
identically. The benchmarks here replace that with per-condition targets.

## Confidence key

| Mark | Meaning |
|---|---|
| 🟢 | Directly published in the cited source |
| 🟡 | Derived or computed from published data (method stated) |
| 🔴 | Reasonable interpolation — **not sourced**, a modeling assumption |

## 1. Emergency department length of stay

### 1.1 Treated and released

CMS measure **OP-18b** (median time in ED before leaving, excluding transfers
and psychiatric patients), reporting period 2024-10-01 – 2025-09-30, aggregated
across the 4,081 hospitals reporting a score:

| Statistic across US hospitals | Minutes | Hours |
|---|---|---|
| Median hospital | **148** | **2.5** |
| Mean of hospital medians | 156.9 | 2.6 |
| 25th / 75th percentile | 119 / 188 | 2.0 / 3.1 |
| 90th percentile | 225 | 3.8 |
| Range | 42 – 413 | 0.7 – 6.9 |

Source: CMS Provider Data Catalog, "Timely and Effective Care – Hospital,"
dataset `yv7e-xc69`, measure `OP_18b`.
<https://data.cms.gov/provider-data/dataset/yv7e-xc69>

Behavioral health runs ~1.7× longer with an extreme right tail — **OP-18c**
median hospital **247 min (4.1 h)**, 90th percentile 428 min, max 6,870 min.

Corroborating peer review (Emergency Department Benchmarking Alliance, 317
hospital-based EDs): median overall ED LOS 140 min; treated-and-released
**122.9 min (2.0 h)**; admitted **241.8 min (4.0 h)**; boarding 71.3 min.
Dark C et al., *J Am Coll Emerg Physicians Open.* 2020;1(6):1297-1303.
PMID 33392536.

Academic EDs run materially longer: median **277 min** vs **190 min**
non-academic. Reznek MA et al., *BMC Emerg Med.* 2019;19(1):72. PMID 31752708.

### 1.2 Admitted patients (ED arrival → inpatient bed)

⚠️ **Known gap.** CMS retired ED-1b/ED-2b from Care Compare; this was verified
by enumerating every measure ID under `_condition = "Emergency Department"` in
dataset `yv7e-xc69` (only `EDV`, `OP_18a`–`OP_18d`, `OP_22`, `OP_23` exist).
The archived Hospital Compare flat files return HTTP 404. Best available:

| Metric | Value | Population | Source |
|---|---|---|---|
| Median ED LOS, admitted | 🟢 **241.8 min (4.0 h)** | 317 EDs, ~2018 | Dark 2020, PMID 33392536 |
| Median boarding | 🟢 71.3 min | same | same |
| Median boarding, national sample | 🟢 79 min (IQR 36–145) | NHAMCS 2007–2010 | Pitts SR et al., *Acad Emerg Med.* 2014;21(5):497-503. PMID 24842499 |
| Admits boarding >2 h | 🟢 32% (95% CI 30–35) | same | Pitts 2014 |

Both sources predate 2020 and boarding has worsened since, so **4 h is a floor**
for modern ED dwell on admitted patients. A defensible synthetic range is
**4–6 h**, with behavioral-health admits far longer.

### 1.3 By acuity

Median ED LOS falls monotonically with acuity: **~200 min at ESI 1 → ~80 min at
ESI 5**; 89% of admitted patients were ESI 2–3. Theiling BJ et al.,
*West J Emerg Med.* 2020;21(5):1147-1155. PMID 32970568.

Triage mix (NHAMCS 2021, Table 6): ESI 2 10.4%, ESI 3 34.8%, ESI 4 18.3%,
ESI 5 2.5%, unknown 23.1%.

## 2. Inpatient LOS by condition family

Two complementary sources. **Use HCUP all-payer as the headline value per
family, and the CMS DRG table for severity-tiered variation** — they differ
because the populations and LOS conventions differ (HCUP counts a same-day
admit/discharge as LOS 0; DRG values are Medicare fee-for-service only).

### 2.1 HCUP all-payer ALOS by CCSR condition (2022 Q4)

| CCSR condition | 2019 Q1 | 2022 Q4 |
|---|---|---|
| Acute myocardial infarction | 4.51 | **4.45** |
| Cardiac dysrhythmias | 3.53 | **3.43** |
| Cardiac arrest & ventricular fibrillation | 5.65 | **5.76** |
| Heart failure | 5.50 | **5.81** |
| Acute hemorrhagic cerebrovascular disease | 8.95 | **9.61** |
| Diabetes mellitus with complication | 4.99 | **5.52** |
| Septicemia | 7.18 | **7.58** |
| COVID-19 | — | 5.47 |
| Osteoarthritis | 1.93 | **2.21** |
| Acute myeloid leukemia | 19.05 | **19.70** |
| Short gestation / low birth weight | 30.15 | 31.92 |

Source: AHRQ/HCUP *Summary Trend Tables*, Table 2c, National worksheet.
<https://hcup-us.ahrq.gov/reports/trendtables/summarytrendtables.jsp>

### 2.2 CMS MS-DRG geometric/arithmetic mean LOS (FY2025 IPPS Table 5)

Selected rows, days. **GM** = geometric mean, **AM** = arithmetic mean.
Source: CMS FY2025 IPPS Final Rule Table 5 (FY2023 MedPAR claims).
<https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2025-ipps-final-rule-home-page>

| Family | DRG | Title | GM | AM |
|---|---|---|---|---|
| Cardiac | 280 / 281 | Acute MI, discharged alive w/ MCC / w/ CC | 4.1 / 2.4 | 5.5 / 2.9 |
| Cardiac | 291 / 292 / 293 | Heart failure & shock w/ MCC / CC / none | 3.9 / 3.0 / 2.1 | 5.1 / 3.8 / 2.5 |
| Cardiac | 308 / 309 / 310 | Arrhythmia w/ MCC / CC / none | 3.4 / 2.3 / 1.8 | 4.5 / 2.8 / 2.1 |
| Cardiac | 313 | Chest pain | 1.7 | 2.1 |
| Pulmonary | 193 / 194 / 195 | Simple pneumonia w/ MCC / CC / none | 4.0 / 2.8 / 2.3 | 5.0 / 3.5 / 2.7 |
| Pulmonary | 190 / 191 / 192 | COPD w/ MCC / CC / none | 3.4 / 2.7 / 2.1 | 4.3 / 3.3 / 2.6 |
| Pulmonary | 202 / 203 | Bronchitis & asthma w/ CC-MCC / without | 2.9 / 2.1 | 3.6 / 2.6 |
| Pulmonary | 208 / 207 | Ventilator ≤96 h / >96 h | 4.9 / 12.8 | 7.1 / 15.3 |
| Sepsis | 871 / 872 | Severe sepsis w/ MCC / without | 4.9 / 3.5 | 6.6 / 4.2 |
| Sepsis | 870 | Severe sepsis w/ MV >96 h | 12.8 | 15.4 |
| Neuro | 064 / 065 / 066 | Intracranial hemorrhage or infarction w/ MCC / CC / none | 4.5 / 2.8 / 1.9 | 6.4 / 3.6 / 2.3 |
| Neuro | 100 / 101 | Seizures w/ MCC / without | 4.4 / 2.7 | 6.5 / 3.5 |
| Endocrine | 637 / 638 / 639 | Diabetes w/ MCC / CC / none | 4.0 / 3.0 / 2.0 | 5.4 / 3.8 / 2.5 |
| GI | 377 / 378 / 379 | GI hemorrhage w/ MCC / CC / none | 4.5 / 2.9 / 2.0 | 5.8 / 3.5 / 2.4 |
| Ortho | 470 / 469 | Major joint replacement w/o MCC / w/ MCC | 1.7 / 3.5 | 2.1 / 5.0 |
| Ortho | 521 / 522 | Hip replacement for hip fracture w/ MCC / without | 6.2 / 4.0 | 7.3 / 4.5 |
| Renal | 682 / 683 / 684 | Renal failure w/ MCC / CC / none | 4.4 / 3.0 / 2.2 | 5.8 / 3.8 / 2.6 |
| Psych | 885 | Psychoses | 6.5 | 9.9 |
| Psych | 895 / 897 | Alcohol/drug w/ rehab / without, no MCC | 7.6 / 3.3 | 10.6 / 4.3 |
| Oncology | 846 / 847 / 848 | Chemotherapy w/ MCC / CC / none | 6.0 / 3.9 / 2.7 | 7.9 / 4.4 / 3.1 |
| OB | 807 / 806 | Vaginal delivery w/o CC / w/ CC | 2.0 / 2.3 | 2.2 / 2.6 |
| OB | 785 / 784 | C-section w/ sterilization w/o CC / w/ CC | 2.5 / 3.1 | 2.9 / 4.3 |

For obstetrics prefer the HCUP all-payer deliveries figure (**2.58 days**);
Medicare OB volume is too small to be representative.

### 2.3 Baseline and service-line LOS

Overall US inpatient ALOS: **4.7 days pre-COVID (2019)** → **5.1 days (2022)**.
Q1 runs 0.3–0.4 days higher than Q2–Q4 (respiratory season).

| Encounter type | 2019 Q1 | 2022 Q4 |
|---|---|---|
| Non-elective, admitted through the ED | 5.07 | **5.52** |
| Non-elective, not through the ED | 6.45 | 6.74 |
| Elective | 4.32 | 4.86 |
| Deliveries | 2.67 | **2.58** |
| Normal newborns | 1.97 | 1.78 |

| Service line (≈ unit type) | 2019 Q1 | 2022 Q4 |
|---|---|---|
| Other medical (≈ general med-surg) | 4.74 | **5.17** |
| Surgical | 5.71 | **6.46** |
| Injury | 5.20 | **6.04** |
| Mental health / substance use | 7.06 | **7.63** |
| Maternal / neonatal | 3.24 | **3.14** |

By payer (2022 Q4): Medicare 5.89, Medicaid 4.95, Private 4.23.
By age: 0–4 3.92, 18–44 3.98, 45–64 5.80, 65–79 5.90, 80+ 5.66.
Urban 5.18 vs rural 4.28. Same HCUP Table 2c source as above.

## 3. ICU length of stay

⚠️ **Weakest-sourced area.** No current CMS or AHRQ national ICU-LOS statistic
exists.

| Metric | Value | Population | Source |
|---|---|---|---|
| Mean ICU LOS | 🟢 **3.86 days** | 116,209 admissions, 104 ICUs, 45 US hospitals | Zimmerman JE et al., *Crit Care Med.* 2006;34(10):2517-29. PMID 16932234 |
| "Short stay" threshold | 🟢 ≤1.7 days | same | same |
| "Long stay" threshold | 🟢 ≥9.4 days | same | same |
| Adult stays involving ICU charges | 🟢 26.9% | HCUP SID, 29 states, 2011 | Statistical Brief #185 |
| Any mechanical ventilation, ALOS | 🟢 15.11 days | all-payer 2022 Q4 | HCUP Table 2c |

Mean 3.86 with a 1.7-day short threshold and 9.4-day long threshold implies a
**median around 2 days with a heavy right tail** — the classic lognormal shape.

### ICU utilization by DRG (upper bound)

Percent of stays with ICU charges, HCUP Statistical Brief #185 (2011, 29
states): ventilator <96 h **93.3%**; AMI w/ MCC **70.3%**; intracranial
hemorrhage/infarction w/ MCC **64.6%**; sepsis w/ MCC **59.0%**; heart failure
w/ MCC **53.8%**; renal failure w/ MCC 47.6%; diabetes w/ CC 44.1%; GI
hemorrhage w/ CC 43.3%; chest pain **40.6%**; pneumonia w/ MCC 40.5%.

⚠️ These are ICU *charge* flags, and the brief only included DRGs at ≥40%, so
they are a **selected upper bound**, not the family-wide ICU rate. Chest pain at
40.6% reflects telemetry/observation charge practice, not critical illness.

⚠️ **Unsourced gap:** no authoritative US statistic was found for what fraction
of ICU stays step down to a ward versus discharge directly from ICU.

## 4. ED-to-inpatient transfer patterns

Source: CDC/NCHS NHAMCS ED Web Tables, 2021 (Table 23/24) and 2019.
<https://www.cdc.gov/nchs/data/nhamcs/web_tables/2021-nhamcs-ed-web-tables-508.pdf>

**Admission rate:** 🟢 **13.1%** of ED visits (2021; 11.2% in 2019), plus 2.3%
admitted to observation.

**By age — a strong driver worth encoding:** 15–24 **6.1%**; 25–44 **7.4%**;
45–64 **16.4%**; 65–74 **24.4%**; 75+ **33.8%**.

**Destination of ED admissions (2021):**

| First unit | % of admits |
|---|---|
| Critical care (ICU) | **15.5%** |
| Step-down / telemetry | 2.7% |
| Operating room | 5.4% |
| Mental health / detox | 3.6% |
| Cardiac cath lab | 2.2% |
| Other bed or unit (≈ med-surg) | **55.3%** |
| Unknown | 15.2% |

**Recommended modeling split** (🟡 redistributing "unknown" proportionally):
ICU ~18%, step-down ~3%, OR ~6%, behavioral ~4%, cath lab ~3%,
general med-surg ~65%.

⚠️ Step-down is almost certainly under-reported — NHAMCS "other bed or unit"
likely absorbs many telemetry beds; real-world telemetry is typically 15–25%.

**Inpatient LOS after ED admission:** 🟢 4.9 days (2019) → **5.2 days (2021)**,
corroborated by HCUP's 5.52 days for ED-admitted non-elective stays.

## 5. Compact configuration table

This is the table the simulator encodes. ED dwell in hours; LOS in days.

| Family (ICD-10) | ED dwell, admitted (h) | LOS mean (d) | LOS median (d) | ICU-bound | ICU LOS mean (d) |
|---|---|---|---|---|---|
| **Baseline / all causes** | 🟢 4.0 | 🟢 5.1 | 🟡 3.0 | 🟡 18% | 🟢 3.9 |
| Cardiac — AMI (I21) | 🟡 3.5 | 🟢 4.45 | 🟡 3.0 | 🟢 70% | 🟡 2.5 |
| Cardiac — heart failure (I50) | 🟡 4.5 | 🟢 5.81 | 🟡 4.0 | 🟢 43–54% | 🟡 2.5 |
| Cardiac — dysrhythmia (I48) | 🟡 4.0 | 🟢 3.43 | 🟡 2.0 | 🟢 51% ⚠️ | 🔴 1.5 |
| Cardiac — chest pain (R07) | 🟡 3.5 | 🟢 2.1 | 🟡 1.0 | 🟢 41% ⚠️ | 🔴 1.0 |
| Pulmonary — pneumonia (J12–J18) | 🟡 4.5 | 🟢 4.4–4.9 | 🟡 3.0 | 🟢 41% | 🟡 3.0 |
| Pulmonary — COPD (J44) | 🟡 4.5 | 🟢 2.6–4.3 | 🟡 3.0 | 🔴 25% | 🟡 3.0 |
| Pulmonary — asthma (J45) | 🟡 4.0 | 🟢 2.6–3.6 | 🟡 2.0 | 🔴 15% | 🔴 2.0 |
| Pulmonary — resp. failure (J96) | 🟡 2.0 | 🟢 7.1 / 15.3 | 🟡 8.0 | 🟢 93% | 🟡 5–10 |
| Infectious — sepsis (A41) | 🟡 4.0 | 🟢 7.58 | 🟡 5.0 | 🟢 59% | 🟡 4.0 |
| Infectious — cellulitis (L03) | 🟡 4.0 | 🟢 3.9–6.0 | 🟡 3.0 | 🔴 8% | 🔴 2.5 |
| GI / digestive (K00–K95) | 🟡 4.0 | 🟢 2.4–6.1 | 🟡 3.0 | 🟢 43% | 🔴 2.5 |
| Neuro — stroke (I60–I69) | 🟡 2.5 | 🟢 9.61 hem. / 2.3–6.4 isch. | 🟡 4.0 | 🟢 47–65% | 🟡 3.0 |
| Neuro — other (G00–G99) | 🟡 4.0 | 🟢 3.5–6.5 | 🟡 3.0 | 🔴 25% | 🔴 2.5 |
| Endocrine (E00–E89) | 🟡 4.5 | 🟢 5.52 | 🟡 4.0 | 🟢 44% | 🔴 2.0 |
| Ortho — hip fracture (S72) | 🟡 5.0 | 🟢 4.5–7.6 | 🟡 5.0 | 🔴 15% | 🔴 2.0 |
| Ortho — elective joint (M16/M17) | n/a | 🟢 2.21 | 🟡 2.0 | 🔴 3% | 🔴 1.5 |
| Injury / trauma (S00–T88) | 🟡 4.0 | 🟢 6.04 | 🟡 4.0 | 🔴 25% | 🔴 3.5 |
| OB — vaginal delivery (O80) | n/a | 🟢 2.58 | 🟡 2.0 | 🔴 <1% | 🔴 1.5 |
| OB — C-section (O82) | n/a | 🟢 2.9–4.3 | 🟡 3.0 | 🔴 1% | 🔴 1.5 |
| Psychiatry (F01–F99) | 🔴 10.0 | 🟢 7.63 | 🟡 6.0 | 🔴 2% | 🔴 2.0 |
| Oncology (C00–D49) | 🟡 5.5 | 🟢 19.7 AML / 3.1–7.9 chemo | 🟡 5.0 | 🔴 12% | 🔴 3.0 |
| Renal / GU (N00–N99) | 🟡 4.5 | 🟢 2.6–5.8 | 🟡 3.0 | 🟢 48% | 🔴 2.5 |

### What the 🟡 and 🔴 marks mean here

- **Per-condition ED admit rates are all 🔴.** Only the overall rate (13.1%) and
  the by-age breakdown are published. No per-condition ED admit-rate table was
  found.
- **Every median inpatient LOS is 🟡.** HCUP and CMS publish means and geometric
  means, not medians. Medians here are set at roughly the geometric mean, or
  ~0.75× the arithmetic mean — the standard relationship for right-skewed LOS.
  Exact medians would require NIS microdata.
- **ICU LOS by condition is 🔴/🟡**, scaled from the APACHE IV overall mean of
  3.86 days using relative hospital-LOS ratios from the DRG table.
- **Per-condition ED dwell is 🟡**, derived from the ESI gradient (200 min at
  ESI 1 → 80 min at ESI 5) mapped to each condition's typical acuity and
  anchored to the OP-18b median of 148 min. Only the overall discharged (2.5 h),
  overall admitted (4.0 h), psych (4.1 h) and cancer (4.9 h) values are 🟢.
- **Psych ED dwell of 10 h is 🔴**, an extrapolation. OP-18c gives a 4.1 h median
  across mostly-discharged psych patients; admitted psych patients board far
  longer.

## 6. How the simulator consumes these numbers

Each drawn stay comes from a right-skewed lognormal fitted to the published
mean and median for its family. Because a lognormal is fully determined by
those two statistics, the fit is derived rather than guessed:

```
median = exp(mu)              =>  mu    = ln(median)
mean   = exp(mu + sigma^2/2)  =>  sigma = sqrt(2 * ln(mean / median))
```

`_draw_los_hours()` implements this, falling back to symmetric jitter when a
source reports no usable median or a median at or above the mean (which no
lognormal can represent). Draws are capped at `_LOS_OUTLIER_CAP_MULTIPLE`
(6×  the mean) so an unbounded tail cannot produce a year-long demo stay, and
floored at `_MIN_DWELL_HOURS` so no patient discharges instantly.

Verified empirically over 200,000 draws per category — the drawn distribution
reproduces the target statistics:

| Target mean / median | Drawn mean | Drawn median | p95 | Max |
|---|---|---|---|---|
| 4.50 / 3.0 | 4.42 | 3.00 | 13.25 | 27.00 |
| 5.40 / 4.0 | 5.36 | 3.99 | 14.36 | 32.40 |
| 2.60 / 2.0 | 2.59 | 2.00 | 6.61 | 15.60 |
| 3.80 / 3.0 | 3.79 | 3.00 | 9.33 | 22.80 |
| 1.90 / 1.0 | 1.79 | 1.00 | 6.48 | 11.40 |

The drawn target is persisted per episode so length of stay is a property of
the patient's condition rather than of the `SPEED_MULTIPLIER` demo setting.

### What the simulator encodes

`_LOS_BENCHMARKS` in `src/hospital_operations/patient_flow_simulator.py` holds
one row per `icd_reference.clinical_family`, carrying `ed_dwell_hours`,
`los_mean_days`, `los_median_days`, `icu_share` and `icu_los_days` from the
table in section 5. `_BASELINE_LOS` supplies the all-causes fallback for any
family without its own row.

At admission the simulator draws `target_los_hours` for the stay, draws an ED
dwell, decides whether the stay needs critical care, adds the family's ICU
length of stay when it does, and writes the resulting plan to
`ops_simulated_episode` (`icd_family`, `target_los_hours`, `ed_dwell_hours`,
`icu_expected_flag`, `expected_discharge_datetime`) and to
`ops_bed_state.expected_release_datetime`. Discharge barriers then clear only
once the simulated clock passes that timestamp, and internal transfers carry it
with the patient.

**ICU rate calibration.** The per-family `icu_share` values in section 5 are
*within-condition* cohort rates — roughly 70% of AMI admissions reach a CCU —
so applying them directly would put most of the census in critical care. They
are multiplied by a single factor, `_ICU_CALIBRATION`, chosen so the blended
rate equals the published `_ICU_TARGET_SHARE` of 18% of admissions while the
relative ordering between conditions is preserved. This keeps both published
facts: the aggregate share and the condition-level ranking.

**Known gap: the realized ICU share runs high.** The calibration factor
averages across all 16 families *unweighted*, but the simulator currently
admits through only five specialty stories. Those map to Respiratory
(general and pediatric), Cardiology, Hematology and Musculoskeletal, and the
two highest-ICU families dominate the draw. The live bounded run showed
33.3% ICU-flagged (8 of 24) against the 18% target. Fix options: calibrate
against the families the stories actually admit, or widen the story catalog
to cover every family. The validators report this share as an info summary
rather than a gate.

Verified on a live bounded run (20 iterations, 24 new episodes): every episode
carried a family, a drawn length of stay, an ED dwell and an ICU flag; the
Respiratory cohort drew a 4.45-day mean against its 4.50-day target; no stay
discharged before its planned date; and ED transfers split across general and
critical-care destinations instead of every ED patient being sent to the ICU.

## 7. Gaps and follow-ups

1. **No current CMS ED-arrival-to-inpatient-bed measure.** ED-1b/ED-2b were
   retired; archived Hospital Compare ZIPs 404. Follow-up: the Provider Data
   Catalog archive UI at
   <https://data.cms.gov/provider-data/archived-data/hospitals>, or the Hospital
   IQR specifications manual.
2. **Boarding data predate the pandemic** (EDBA ~2018, NHAMCS 2007–2010) and
   boarding has worsened materially since. Treat published values as floors.
3. **No national ICU-LOS-by-diagnosis table exists.** Current ICU values are
   scaled proxies, and the APACHE IV anchor is 2002–2003 data.
4. **Step-down vs direct ICU discharge is unsourced** and is a pure modeling
   assumption.
5. **ICU utilization percentages are a selected upper bound** (≥40% inclusion
   threshold, 2011 charge data), not family-wide ICU rates.
