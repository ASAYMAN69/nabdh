# Hackathon Submission Checklist — Nabdh

**Challenge:** Future Health Digital Innovation Challenge · Population Health Challenge 04 — Precision Prevention and Screening
**Submission format:** working prototype repository + 3-minute pre-recorded demonstration
**Submission date:** 20 November 2026
**Team size:** 1
**Last verified:** 2026-11-20 · `126 passed, 2 skipped` (125/3 in a fresh clone) · `ruff` clean · demo aggregates `1 urgent / 9 high / 17 elevated / 1.0 expected cases`

**Status:** core build, documentation, tests, and demo UX are done. **Remaining: record the 3-minute video, rehearse, and submit.**

Legend: `[x]` done · `[ ]` to do · `[~]` partial / disclosed gap (not a blocker)

---

## 1. Required deliverables

| # | Deliverable | Status | Evidence / notes |
|---|---|---|---|
| 1 | Working prototype repository | [x] Done | `make setup && make demo` → `http://127.0.0.1:8000/` |
| 2 | 3-minute demo video | [ ] **To do** | Script ready (`docs/DEMO_SCRIPT.md`); recording not done |
| 3 | Technical documentation | [x] Done | `docs/TECHNICAL_OVERVIEW.md` |
| 4 | Clinician guide | [x] Done | `docs/CLINICIAN_GUIDE.md` |
| 5 | CSV preparation guide | [x] Done | `docs/CSV_GUIDE.md` |
| 6 | Clinician CSV templates | [x] Done | `clinician_template.csv`, `clinician_template_minimal.csv`, `clinician_template_lab_units.csv` |
| 7 | Model card | [x] Done | `docs/MODEL_CARD.md` |
| 8 | Assumptions & limitations | [x] Done | `docs/ASSUMPTIONS_AND_LIMITATIONS.md` |
| 9 | Clinical semantics change record | [x] Done | `docs/CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md` |
| 10 | Synthetic demo cohort | [x] Done | `data/sample/uae_demo_cohort.csv` (60 rows) |
| 11 | Clinician probe files | [x] Done | `data/sample/probes/` |
| 12 | Pilot proposal | [x] Done | `docs/PILOT_ONE_PAGER.md` |
| 13 | README | [x] Done | `README.md` |
| 14 | Submission write-up | [x] Done | `SUBMISSION.md` |
| 15 | QA master CSV (bonus) | [x] Done | `data/sample/qa/00_master_all_cases.csv` (206 rows) |

---

## 2. Challenge requirements (from `CONTEXT.md` / `SUBMISSION.md` §4)

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Transparent risk and care-gap identification | [x] Done | Model priority + 32 versioned rules; "Why Flagged" signed drivers; citations; `UAE-WOW-029` |
| 2 | Personalized preventive pathways | [x] Done | Stream-specific pathway + timing + recall; `UAE-URG-101`, `UAE-WCV-201` |
| 3 | Culturally appropriate engagement | [x] Done | AR/EN/TL previews, RTL rendering, consent choices, outcome strip; `UAE-WOW-029` |
| 4 | Local population safeguards | [x] Done | Segment audit, small-cell + complementary suppression, unit-suspect exclusion; `UAE-UNIT-102`, `UAE-SM-401` |
| 5 | Outcome-based evaluation | [x] Done | `GET/POST /api/outcomes` + SQLite; model card AUC/O:E/Brier/calibration candidate |
| 6 | UAE local validation | [~] Disclosed gap | No UAE data; NHANES US training + 2021–23 external; local recalibration required before pilot |

---

## 3. Demo readiness

| Item | Status | Notes |
|---|---|---|
| Demo file | [x] Done | `data/sample/uae_demo_cohort.csv` |
| Probe files | [x] Done | `data/sample/probes/` |
| Demo script | [x] Done | `docs/DEMO_SCRIPT.md` (updated for auto-score) |
| Auto-score on upload | [x] Done | No button; overlay + auto-scroll to report |
| Tier hero (Urgent largest) | [x] Done | Urgent / High / Elevated cards, then smaller KPIs |
| Loading state | [x] Done | "Scoring your cohort…" overlay + spinner |
| Pinned demo aggregates | [x] Done | `tests/test_demo_probes.py` |
| 3-minute video recording | [ ] **To do** | Record at 1440×900, 30 fps, captions |
| Full rehearsal | [ ] **To do** | Run the script twice end-to-end |
| Judge Q&A prep | [ ] **To do** | See §6 |

---

## 4. Final QA

| Check | Status | Command / evidence |
|---|---|---|
| Install from clean | [x] Done | `make setup` |
| Test suite | [x] Done | `126 passed, 2 skipped` (125/3 in a fresh clone) |
| Lint | [x] Done | `ruff check app nabdh tests scripts` |
| JS syntax | [x] Done | `node --check app/static/app.js` |
| Demo cohort | [x] Done | 60 rows → 1 urgent / 9 high / 17 elevated / 4 missed / 1.0 expected |
| Master QA file | [x] Done | 206 rows; 100% face-validity on clinical rule checks |
| API smoke | [x] Done | `/health`, `/`, `/api/score`, `/api/score.csv`, `/api/outcomes` |
| Auto-score UX | [x] Done | Playwright: overlay, auto-scroll, tier hero, no table re-render |
| No real patient data | [x] Done | Synthetic only; no names, Emirates IDs, phone numbers |
| No network/LLM calls during scoring | [x] Done | Deterministic; `StubReasoner` unavailable |
| CSV formula sanitisation | [x] Done | `_sanitize_cell` on export |
| Small-cell suppression | [x] Done | `<10` + complementary suppression |
| No stale demo numbers in docs | [x] Done | Swept: 126 tests, 9/17, 1.0, O:E 1.255 |

---

## 5. Known limitations (disclosed — not blockers, but judges may ask)

- [~] **No UAE data.** Trained on US NHANES 2017–20; external 2021–23. Local recalibration is the pilot's first step.
- [~] **Scores are uncalibrated priority ranks**, not individual probabilities. Platt candidate documented but not deployed.
- [~] **`full` variant is internally validated only.** The demo routes 43 of 45 scored adults to `full` because family history is present; the externally validated `nofamily` path is used least.
- [~] **CKD label is `KIQ022` self-report** ("told you had weak/failing kidneys"), not eGFR/ACR.
- [~] **Dysglycaemia and hypertension barely beat age-only ranking** (+3pp / +2–5pp top-30% capture).
- [~] **Six sign-clamped feature→target pairs** are zeroed and test-blessed (model card §4.4).
- [~] **No production auth/TLS/multi-tenancy/EHR/messaging gateway.** Local demo only.

---

## 6. Judge Q&A prep (to do)

Prepare 30-second answers for:

1. **Why no UAE data?** → Honest: US NHANES; local recalibration is the pilot's first step.
2. **Why does the demo use the internally validated model?** → Family history is predictive; `nofamily` is the externally validated fallback.
3. **Why is CKD a self-report label?** → `KIQ022`; construct validity limited; production needs eGFR/ACR.
4. **Why do two models barely beat age?** → They are part of a multi-target queue, not standalone screeners.
5. **Why are six features zeroed?** → Sign-constraint prevents clinically inverted gradients; documented.
6. **What is the calibration plan?** → Platt candidate documented but not deployed; local recalibration + threshold review.
7. **What is the outcome metric?** → Pilot: completion, time-to-action, urgent acknowledgement, equity gaps.
8. **What is the "wow" moment?** → 29-year-old missed by age rule + Arabic RTL outreach + outcomes strip.
9. **What is the safety story?** → Unit-suspect never escalates; urgent overrides model; sign-off required.
10. **What is the data governance?** → Synthetic demo; DPIA/data-sharing agreement before pilot.

---

## 7. Before you submit (ordered)

- [ ] Re-record the 3-minute demo with the new auto-score UI.
- [ ] Rehearse the full script twice; check the pinned numbers on screen.
- [ ] Run the final smoke test on the presentation machine (fresh `make setup && make demo`).
- [ ] Record a backup of the demo video and a repo zip.
- [ ] Submit the repo link + video to the portal.
- [ ] Prepare the judge Q&A answers.
- [ ] Confirm the submission timestamp before the deadline.

---

## 8. Submission-day runbook

```bash
cd /mnt/ee/aprojects/nabdh
make setup
make test          # 126 passed, 2 skipped
make demo          # http://127.0.0.1:8000/
```

Then in the browser:

1. Upload `data/sample/uae_demo_cohort.csv` — **auto-scores**; do not click a button.
2. Click `UAE-WOW-029` → **Why Flagged** → **Culturally Tailored Outreach (AR)** → Confirm slot → Mark completed.
3. Click `UAE-URG-101` → Urgent cardiac, no outreach preview.
4. Click `UAE-UNIT-102` → `unit_suspect`, **not escalated**.
5. Upload `data/sample/probes/probe_glycaemic_units.csv` → two High rows with conversions.
6. Upload `data/sample/probes/probe_bp_two_rows.csv` → urgent adult + urgent obstetric.
7. Scroll to **Segment Audit** → small-cell suppression (`<10`, complementary).

---

## 9. Hackathon file map

| File | Role |
|---|---|
| `SUBMISSION.md` | Submission write-up + requirement mapping |
| `README.md` | Project overview + quickstart |
| `CONTEXT.md` | Challenge statement + 5 requirements + judging guidance |
| `PATH.md` | Original solution blueprint / brainstorm |
| `docs/DEMO_SCRIPT.md` | 3-minute demo script (updated for auto-score) |
| `docs/DEMO_AND_LIMITATIONS.md` | Demo notes + assumptions |
| `docs/PILOT_ONE_PAGER.md` | 12-week pilot proposal |
| `docs/MODEL_CARD.md` | Model details, metrics, limitations |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Explicit assumptions and residual gaps |
| `docs/TECHNICAL_OVERVIEW.md` | Architecture and request flow |
| `docs/CLINICIAN_GUIDE.md` | Clinician-facing guide |
| `docs/CSV_GUIDE.md` | CSV preparation guide |
| `docs/CHANGE_RECORD_2026-11-19_CLINICAL_SEMANTICS.md` | Clinical semantics change record |
| `data/sample/uae_demo_cohort.csv` | 60-row synthetic demo cohort |
| `data/sample/probes/` | One-row clinician probes |
| `data/sample/qa/00_master_all_cases.csv` | 206-row QA master (bonus) |
| `tests/test_challenge04_features.py` | Challenge-04 feature tests |
| `tests/test_demo_probes.py` | Pinned demo aggregates |