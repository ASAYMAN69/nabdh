"""Bilingual English/Arabic outreach payload formatting with meaningful opt-in/snooze choice."""
from __future__ import annotations

_AR_PATHWAYS = {
    "Accelerated adult comprehensive screening - metabolic track "
    "(HbA1c + fasting glucose, lipids, BP)": (
        "الفحص الشامل المتسارع للبالغين - المسار الأيضي"
    ),
    "Adult comprehensive screening - cardiometabolic track": (
        "الفحص الشامل للبالغين - مسار صحة القلب والأيض"
    ),
    "Adult comprehensive screening - standard track (guideline-due, no recent test)": (
        "الفحص الشامل للبالغين - المسار القياسي"
    ),
    "Well-Child Visit - paediatric weight and metabolic review": (
        "زيارة صحة الطفل - متابعة النمو والأيض"
    ),
    "Well-Child Visit - growth and nutrition review": (
        "زيارة صحة الطفل - متابعة النمو والتغذية"
    ),
    "Well-Child Visit - growth faltering review": (
        "زيارة صحة الطفل - تقييم تأخر النمو"
    ),
    "Well-Child Visit - priority developmental & paediatric review": (
        "زيارة صحة الطفل - تقييم النمو والتطور ذو الأولوية"
    ),
    "Well-Child Visit - catch-up preventive & immunisation review": (
        "زيارة صحة الطفل - متابعة التطعيمات والفحص الوقائي"
    ),
    "Well-Child Visit - standard schedule": (
        "زيارة صحة الطفل - الجدول الدوري"
    ),
    "Prenatal cardiometabolic & GDM screening track": (
        "مسار الفحص الوقائي لصحة القلب والأيض وسكري الحمل"
    ),
    "Multi-domain preventive screening - cardiometabolic & renal track": (
        "الفحص الوقائي متعدد المجالات - مسار صحة القلب والأيض والكلى"
    ),
    "Elevated cardiovascular marker — preventive cardiology review": (
        "ارتفاع مؤشر قلبي وعائي — مراجعة طب القلب الوقائي"
    ),
}

_AR_TIMINGS = {
    "Within 30 days": "خلال 30 يوماً",
    "Within 90 days": "خلال 90 يوماً",
    "Within 6 months": "خلال 6 أشهر",
    "At next routine cycle (12 months)": "في الموعد الدوري القادم",
    "Per prenatal schedule": "حسب جدول متابعة الحمل",
}


def format_outreach_preview(
    resident_id: str,
    pathway: str,
    timing: str,
    language: str = "EN",
    population: str = "adult",
) -> dict[str, str | list[str]]:
    """Generate a culturally respectful outreach preview (clinician sign-off required)."""
    raw_lang = (language or "EN").strip().upper()
    out_lang = (
        "AR"
        if raw_lang in ("AR", "AR-AE", "ARABIC") or raw_lang.startswith("AR-")
        else "EN"
    )
    is_ped = population == "child/adolescent"

    if out_lang == "AR":
        ar_pathway = _AR_PATHWAYS.get(pathway, "المتابعة الوقائية الموصى بها")
        ar_timing = _AR_TIMINGS.get(timing, "في أقرب وقت مناسب")
        if is_ped:
            body = (
                f"عزيزي ولي أمر الطفل ({resident_id})، حرصاً على نموه وصحته، "
                f"نوصي بحجز موعد ({ar_pathway}) {ar_timing}. "
                "المشاركة اختيارية بالكامل — يمكنك تأكيد الموعد، تأجيله، أو الاعتذار."
            )
        else:
            body = (
                f"مرحباً ({resident_id})، حرصاً على صحتك وصحة أسرتك، "
                f"نوصي بمتابعة وقائية ({ar_pathway}) {ar_timing}. "
                "المشاركة اختيارية بالكامل — يمكنك تأكيد الموعد، تأجيله، أو الاعتذار."
            )
    else:
        t_clean = timing.strip()
        timing_phrase = (
            t_clean[0].lower() + t_clean[1:]
            if t_clean.lower().startswith(("within ", "at ", "per "))
            else f"within {t_clean}"
        )
        if is_ped:
            body = (
                f"Dear parent/caregiver of {resident_id}, to support your child's healthy growth, "
                f"a preventive review ({pathway}) is recommended {timing_phrase}. "
                "Participation is voluntary — you may confirm a slot, reschedule, or decline."
            )
        else:
            body = (
                f"Hello ({resident_id}), to support your family's long-term health, "
                f"a preventive check ({pathway}) is recommended {timing_phrase}. "
                "Participation is voluntary — you may confirm a slot, reschedule, or decline."
            )
    return {
        "language": out_lang,
        "message": body,
        "choices": ["Confirm slot", "Reschedule", "Opt out"],
    }
