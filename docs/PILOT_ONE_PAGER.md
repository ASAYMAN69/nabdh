# Pilot One-Pager — Nabdh

**Proposal:** a 12-week, nurse-led, two-district pilot of pre-lab cardiometabolic triage plus guideline-rule alerts, embedded in the existing adult comprehensive screening pathway.
**Status:** concept for discussion; no UAE data has been accessed.
**Owner:** population-health programme lead, with a clinical safety officer and a data protection officer.

---

## 1. Why pilot

Age-40 invitations miss younger adults with clustered cardiometabolic risk and over-invite low-risk adults. A pre-lab priority score can reorder the existing invitation list without changing the eligibility rules; deterministic alerts then catch urgent labs and vitals that arrive through the screening visit. The pilot tests whether reordering improves completion and time-to-action without increasing harm or inequity.

## 2. Design

| Item | Proposal |
|---|---|
| Population | Adults 20–64 registered in two districts, not pregnant, no diagnosed diabetes/CVD at baseline |
| Sample | ~6,000 eligible adults; 3,000 randomised to priority ordering, 3,000 to usual age-based ordering |
| Unit | Primary-care screening clinic; existing nurses and recall staff |
| Intervention | Queue ordered by Nabdh priority; guideline-due and care-gap flags; deterministic urgent alerts; Arabic/English outreach previews with consent choices |
| Control | Existing age/sex invitation order and usual recall |
| Duration | 12 weeks recruitment + 12 weeks follow-up |
| Primary outcome | Completed comprehensive screening (HbA1c or FPG + lipids + BP) within 12 weeks |
| Secondary | Time from upload to clinician action; urgent-alert acknowledgement within 24 h; outreach response by language; missed urgent findings; screening yield (new dysglycaemia, hypertension, dyslipidaemia, CKD); calibration by subgroup |
| Safety | Every actionable tier requires clinician sign-off; urgent findings suppress automated outreach; incident log for missed or delayed urgent findings; independent safety review at weeks 4 and 12 |

## 3. What the pilot must prove

| Question | Threshold for continuation |
|---|---|
| Does prioritisation increase completion? | ≥5 percentage-point absolute increase vs. control, with 95% CI excluding no effect |
| Does it reach younger/high-risk adults? | ≥30% of completed screenings from adults <40 in the intervention arm |
| Is the model calibrated locally? | O:E 0.8–1.25 overall; no subgroup O:E outside 0.6–1.6 without review |
| Are urgent alerts safe? | 100% acknowledged within 24 h; zero unresolved urgent findings at audit |
| Is outreach equitable? | Response and completion gaps by language/district <10 percentage points, or an approved remediation plan |
| Is the workflow usable? | Median upload-to-queue <2 min; <5% of rows requiring manual unit correction |

Failure on any safety threshold pauses the pilot. Failure on completion triggers a process review, not an automatic model change.

## 4. Data and governance

- **Data minimisation:** only fields required for triage and the screening pathway; no free-text notes; no Emirates ID in the analytic extract.
- **Legal basis:** authorised use under the participating health authority; DPIA completed before extraction; data-sharing agreement with the programme.
- **Storage:** in-country, encrypted at rest and in transit; role-based access; audit logging; 12-month retention unless the authority specifies otherwise.
- **Model artefacts:** frozen for the pilot; any recalibration is versioned, reviewed, and deployed behind a change record.
- **Consent:** outreach includes an explicit opt-out; declining does not affect access to care.
- **Small cells:** counts below 10 suppressed in all reports, with complementary suppression.
- **Reporting:** monthly dashboard to the programme; serious incidents within 24 h.

## 5. Recalibration, not retraining

The pilot's first 1,000 complete records are used for intercept/slope recalibration and subgroup checks. The model structure stays frozen. Re-deriving tier thresholds requires the clinical safety officer and programme lead; the thresholds are product heuristics, not validated clinical cut-offs. Retraining waits for at least 12 months of local outcome data and a separate protocol.

## 6. Costs and roles

| Role | Commitment |
|---|---|
| Programme lead | 0.2 FTE |
| Clinical safety officer | 0.1 FTE |
| Data analyst | 0.4 FTE |
| Nurse/recall team | existing |
| Engineering | 0.3 FTE for deployment, monitoring, rule-pack updates |
| Independent reviewer | 2 safety audits |

Direct costs are dominated by integration and governance, not model compute. Scoring is CPU-only and deterministic.

## 7. Scale path

If the pilot meets its thresholds: extend to all districts, add FHIR-based ingestion, integrate with the recall scheduler, and add Arabic voice/WhatsApp channels through an approved gateway. If it does not: publish the negative result, retain the rule-alert layer if it proves safe, and revisit the pre-lab model with local data.

## 8. What this pilot will not do

- It will not diagnose, prescribe, or replace clinical judgement.
- It will not use genomic data until a separate consent and governance pathway is approved.
- It will not send automated messages without an approved channel and opt-out.
- It will not claim UAE-wide validity from two districts.

---

**Contact:** submission owner, Nabdh.
**Evidence pack:** `docs/MODEL_CARD.md`, `docs/ASSUMPTIONS_AND_LIMITATIONS.md`, `docs/TECHNICAL_OVERVIEW.md`.
