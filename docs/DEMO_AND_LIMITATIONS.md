# Nabdh — 3-Minute Demo Script, Assumptions & Limitations

**Challenge:** Future Health Digital Innovation Challenge · Population Health Challenge 04 (Precision Prevention & Screening)  
**Submission Cohort File:** `data/sample/uae_demo_cohort.csv` (60 synthetic Abu Dhabi resident profiles)

---

## 1. 3-Minute Live Demo ("Happy Path")

1. **Upload the Cohort (0:00 – 0:30)**
   - Open `http://127.0.0.1:8000/` and drop `data/sample/uae_demo_cohort.csv` onto the ingestion pad. Scoring starts automatically.
   - Highlight the **Triage Summary**: shows `Urgent review`, `High priority (30d)`, `Elevated (90d)`, `Missed by age-40 rule`, and `Observations captured` in one unified cohort view.
2. **"Wow" Moment 1 — Catching the Invisible 29-Year-Old (`UAE-WOW-029`, 0:30 – 1:15)**
   - Click `UAE-WOW-029` (female, 29, Al Ain, Arabic). Standard `age >= 40` rules miss her completely.
   - Show the **Why Flagged** drivers (family history of diabetes, central adiposity, elevated BP, plus `GEN-PRS-01` high cardiometabolic polygenic risk) and her **Culturally Tailored Outreach (AR)** preview with interactive **Confirm slot / Reschedule / Opt out** and **Mark screening completed** controls updating the live **Outcome & recall conversion** strip.
3. **"Wow" Moment 2 — Critical Cardiac Safety & Unit Protection (`UAE-URG-101` & `UAE-UNIT-102`, 1:15 – 2:00)**
   - Click `UAE-URG-101`: elevated `troponin_i` (`0.18 ng/mL`), `nt_probnp` (`1420 pg/mL`), and `lvef_pct` (`36%`) escalate straight to **Urgent Clinical Review** with citable AHA/ACC/HFSA rules (`CV-TROP-01`, `CV-NT-proBNP-01`, `CV-LVEF-01`) and **automated patient outreach suppressed** for clinician sign-off.
   - Click `UAE-UNIT-102` (`troponin_i_ng_ml = 4500`): caught as `unit_suspect` instead of hallucinating a critical alert.
4. **"Wow" Moment 3 — Well-Child Visit & Equity Safeguards (`UAE-WCV-201` & Segment Audit, 2:00 – 3:00)**
   - Click `UAE-WCV-201` (age 3): routed to the **paediatric** stream (zero adult ML), flagging missed Well-Child visits, developmental milestone evaluation, overdue immunisations, and G6PD deficiency.
   - Scroll to **Segment Audit**: `Liwa Oasis` (`n < 10`) and `TL` (`n < 10`) are automatically redacted (`<suppressed (<10)>`) to prevent re-identification.

---

## 2. Explicit Technical Assumptions & Limitations

1. **Epidemiological Training Domain vs. Target Population**
   - The 5 adult ML models (`undiagnosed_dm`, `dysglycaemia`, `undiagnosed_htn`, `undiagnosed_dyslipidaemia`, `ckd_risk`) are trained on **U.S. NHANES 2017–2020** and externally validated on **NHANES 2021–2023** (`models/metrics.json`). Before clinical deployment in Abu Dhabi, intercept/slope recalibration on local DoH / Malaffi cohorts is required.
2. **Synthetic Demo Data**
   - `data/sample/uae_demo_cohort.csv` is 100% synthetic and generated for demonstration only; it contains no real patient records.
3. **Clinical Boundary (Non-Diagnostic)**
   - Nabdh is strictly a **population screening prioritisation and recall-routing tool** (`requires_signoff: true`), not an autonomous diagnostic or prescribing system.
4. **Genomic & Well-Child Rules**
   - Genomic markers (`prs_cardiometabolic`, `g6pd_status`, `thalassemia_carrier`) and Well-Child developmental/immunisation flags are evaluated deterministically via `nabdh/rules/rules_pack.json` rather than trained on NHANES (which lacks Emirati Genome Program PRS and paediatric milestone tables).
5. **Layer 3 Reasoning & Live Messaging**
   - Cohort scoring (`score()`) runs deterministically with **zero LLM or network calls** (`StubReasoner` returns `status: "unavailable"` unless a local GGUF or opt-in cloud reasoner is explicitly configured). Outreach previews are simulated in the UI + persisted in `data/outcomes.db` rather than wired to an external SMS/WhatsApp gateway.
