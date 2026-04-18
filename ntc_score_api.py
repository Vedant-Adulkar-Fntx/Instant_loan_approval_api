"""
NTC loan surrogate scorecard — single file.
POST /score with test_cases.json-style nested JSON (one object or an array). No database.
Weights live in scoring_weights.json (edit on disk) or override per request via "scoring_config".
Run: uvicorn ntc_score_api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── configurable weights (scoring_weights.json + optional request override) ──

_WEIGHTS_PATH = Path(__file__).resolve().parent / "scoring_weights.json"
_active_weights: dict[str, Any] = {}
_SECTION_ORDER = (
    "income",
    "tax",
    "dti",
    "spending",
    "hygiene",
    "utility",
    "investments",
    "behavioural",
    "enquiry",
)


def _g(cfg: dict[str, Any], *path: str, default: Any = None) -> Any:
    cur: Any = cfg
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def refresh_scoring_weights() -> dict[str, Any]:
    global _active_weights
    if not _WEIGHTS_PATH.is_file():
        raise FileNotFoundError(f"Missing scoring weights file: {_WEIGHTS_PATH}")
    _active_weights = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
    return _active_weights


def get_active_weights() -> dict[str, Any]:
    if not _active_weights:
        refresh_scoring_weights()
    return _active_weights


def merged_weights(override: dict[str, Any] | None) -> dict[str, Any]:
    base = copy.deepcopy(get_active_weights())
    if override:
        return deep_merge(base, override)
    return base


def configured_max_score(cfg: dict[str, Any]) -> float:
    t = _g(cfg, "totals", "max_score", default=None)
    if t is not None:
        return float(t)
    return sum(float(_g(cfg, "sections", k, "max", default=0) or 0) for k in _SECTION_ORDER)


try:
    refresh_scoring_weights()
except FileNotFoundError:
    pass

# ── adapter: nested JSON → flat features ─────────────────────────────────────


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y")
    return bool(v)


def _ratio_0_1(v: Any) -> float:
    if v is None:
        return 0.0
    x = float(v)
    if x > 1.0:
        return max(0.0, min(1.0, x / 100.0))
    return max(0.0, min(1.0, x))


def _maybe_pct_to_unit(v: Any) -> float:
    if v is None:
        return 0.0
    x = float(v)
    if x > 1.0:
        return max(0.0, min(1.0, x / 100.0))
    return max(0.0, x)


def _employer_category(raw: Any) -> str:
    s = str(raw or "").strip().upper().replace(" ", "_")
    aliases = {
        "PRIVATE_LIMITED": "PRIVATE_LTD",
        "PRIVATE.LTD": "PRIVATE_LTD",
        "PVT_LTD": "PRIVATE_LTD",
        "PSU": "PSU_MNC",
        "MNC": "PSU_MNC",
    }
    return aliases.get(s, s)


def _lender_type_mix(raw: Any) -> str:
    s = str(raw or "").strip().upper().replace(" ", "_")
    aliases = {
        "BANK": "FORMAL",
        "FINTECH": "FORMAL",
        "NONE": "NONE",
        "NBFC_MFI": "MFI_ONLY",
        "MFI": "MFI_ONLY",
        "MFI_ONLY": "MFI_ONLY",
        "FORMAL": "FORMAL",
        "MIXED": "MIXED",
    }
    return aliases.get(s, "MIXED")


def _amb_trend(raw: Any) -> str:
    s = str(raw or "").strip().upper()
    aliases = {
        "STABLE": "FLAT",
        "VOLATILE": "DECLINING",
        "FLAT": "FLAT",
        "RISING": "RISING",
        "DECLINING": "DECLINING",
    }
    return aliases.get(s, "FLAT")


def _salary_regularity(v: Any) -> float:
    if v is None:
        return 0.0
    x = float(v)
    if x <= 1.0:
        return max(0.0, min(1.0, x))
    return max(0.0, min(1.0, x / 12.0))


def _merchant_risk_for_rules(v: Any) -> float:
    if v is None:
        return 0.0
    x = float(v)
    if 0 <= x <= 3 and x == int(x):
        return x
    return max(0.0, min(3.0, 3.0 * (1.0 - x / 100.0)))


def nested_to_flat(raw: Mapping[str, Any]) -> SimpleNamespace:
    inc = raw.get("income") or {}
    tax = raw.get("tax") or {}
    dti = raw.get("dti") or {}
    sp = raw.get("spending") or {}
    hy = raw.get("account_hygiene") or raw.get("hygiene") or {}
    ut = raw.get("utility") or {}
    inv = raw.get("investment") or {}
    beh = raw.get("behavioral") or {}
    enq = raw.get("enquiry") or {}
    risk = raw.get("risk_flags") or {}

    nmi = float(inc.get("net_monthly_income") or dti.get("net_monthly_income") or 1)
    dti_ratio = float(dti.get("dti_ratio") or 0)
    msr = float(sp.get("monthly_savings_rate") or 0)
    if abs(msr) > 1.0:
        msr = msr / 100.0

    return SimpleNamespace(
        salary_credit_regularity=_salary_regularity(inc.get("salary_credit_regularity")),
        income_growth_percentage=float(inc.get("income_growth_percentage") or 0),
        employer_category=_employer_category(inc.get("employer_category")),
        job_tenure_months=int(inc.get("job_tenure_months") or 0),
        net_monthly_income=nmi,
        income_stability_index=_ratio_0_1(inc.get("income_stability_index")),
        salary_variance=float(inc.get("salary_variance") or 0),
        income_consistency_months=int(inc.get("income_consistency_months") or 0),
        pan_verified=_bool(tax.get("pan_verified")),
        pan_aadhaar_linked=_bool(tax.get("pan_aadhaar_linked")),
        itr_filing_years=int(tax.get("itr_filing_years") or 0),
        itr_income=float(tax.get("itr_income") or 0),
        bank_income=float(tax.get("bank_income") or 0),
        income_mismatch_percentage=float(tax.get("income_mismatch_percentage") or 0),
        gst_active=_bool(tax.get("gst_active")),
        gst_filing_regular=_bool(tax.get("gst_filing_regular")),
        tds_detected=_bool(tax.get("tds_detected")),
        tds_amount=float(tax.get("tds_amount") or 0),
        total_monthly_obligations=float(dti.get("total_monthly_obligations") or 0),
        dti_ratio=dti_ratio,
        emi_outflows=float(dti.get("emi_outflows") or 0),
        rent_outflow=float(dti.get("rent_outflow") or 0),
        insurance_outflow=float(dti.get("insurance_outflow") or 0),
        essential_spend_ratio=_ratio_0_1(sp.get("essential_spend_ratio")),
        discretionary_spend_ratio=_ratio_0_1(sp.get("discretionary_spend_ratio")),
        avg_month_end_balance=float(sp.get("avg_month_end_balance") or 0),
        negative_balance_months=int(sp.get("negative_balance_months") or 0),
        high_risk_merchant_flag=_bool(sp.get("high_risk_merchant_flag")),
        cash_withdrawal_ratio=_ratio_0_1(sp.get("cash_withdrawal_ratio")),
        large_transaction_count=int(sp.get("large_transaction_count") or 0),
        impulse_spending_index=_maybe_pct_to_unit(sp.get("impulse_spending_index")),
        monthly_savings_rate=msr,
        merchant_risk_score=_merchant_risk_for_rules(sp.get("merchant_risk_score")),
        bounce_count_outward=int(hy.get("bounce_count_outward") or 0),
        bounce_count_inward=int(hy.get("bounce_count_inward") or 0),
        od_utilization_ratio=_ratio_0_1(hy.get("od_utilization_ratio")),
        late_payment_count=int(hy.get("late_payment_count") or 0),
        average_monthly_balance=float(hy.get("average_monthly_balance") or 0),
        amb_trend=_amb_trend(hy.get("amb_trend")),
        bounce_severity_score=float(hy.get("bounce_severity_score") or 0),
        amb_slope=float(hy.get("amb_slope") or 0),
        electricity_payment_regular=_bool(ut.get("electricity_payment_regular")),
        gas_payment_regular=_bool(ut.get("gas_payment_regular")),
        mobile_bill_regular=_bool(ut.get("mobile_bill_regular")),
        broadband_payment_regular=_bool(ut.get("broadband_payment_regular")),
        rent_payment_regular=_bool(ut.get("rent_payment_regular")),
        water_bill_regular=_bool(ut.get("water_bill_regular")),
        utility_late_payments=int(ut.get("utility_late_payments") or 0),
        bill_payment_score=_ratio_0_1(ut.get("bill_payment_score")),
        sip_active=_bool(inv.get("sip_active")),
        sip_consistency_months=int(inv.get("sip_consistency_months") or 0),
        sip_amount=float(inv.get("sip_amount") or 0),
        fd_amount=float(inv.get("fd_amount") or 0),
        fd_recent_closure=_bool(inv.get("fd_recent_closure")),
        rd_active=_bool(inv.get("rd_active")),
        demat_active=_bool(inv.get("demat_active")),
        portfolio_value=float(inv.get("portfolio_value") or 0),
        ppf_contribution=_bool(inv.get("ppf_contribution")),
        nps_contribution=_bool(inv.get("nps_contribution")),
        investment_discipline_score=_ratio_0_1(inv.get("investment_discipline_score")),
        application_completeness_score=_ratio_0_1(beh.get("application_completeness_score")),
        device_trust_score=_ratio_0_1(beh.get("device_trust_score")),
        is_rooted_device=_bool(beh.get("is_rooted_device")),
        is_emulator=_bool(beh.get("is_emulator")),
        sim_age_days=int(beh.get("sim_age_days") or 0),
        multiple_apps_same_device=_bool(beh.get("multiple_apps_same_device")),
        application_hour=int(beh.get("application_hour") or 0),
        loan_purpose_match_score=_ratio_0_1(beh.get("loan_purpose_match_score")),
        enquiries_last_3_months=int(enq.get("enquiries_last_3_months") or 0),
        enquiries_last_12_months=int(enq.get("enquiries_last_12_months") or 0),
        internal_rejection_flag=_bool(enq.get("internal_rejection_flag")),
        months_since_last_rejection=int(enq.get("months_since_last_rejection") or 0),
        income_change_since_last_application=float(enq.get("income_change_since_last_application") or 0),
        loan_amount_change=float(enq.get("loan_amount_change") or 0),
        lender_type_mix=_lender_type_mix(enq.get("lender_type_mix")),
        kyc_fraud_flag=_bool(risk.get("kyc_fraud_flag")),
        device_risk_flag=_bool(risk.get("device_risk_flag")),
        dti_exceeded=_bool(risk.get("dti_exceeded")),
        high_enquiry_flag=_bool(risk.get("high_enquiry_flag")),
        recent_rejection_flag=_bool(risk.get("recent_rejection_flag")),
    )


# ── scoring rules (weights from scoring_weights.json + request override) ─────


def score_income_employment(d: Any, cfg: dict[str, Any]) -> dict:
    s = _g(cfg, "sections", "income", default={}) or {}
    smax = float(s.get("max", 180))
    scm = float(s.get("salary_credit_max", 45))
    gm = float(s.get("growth_max", 28))
    scores: dict[str, float] = {}
    r = float(d.salary_credit_regularity)
    scores["salary_credit_regularity"] = round(scm * r, 2)
    g = float(d.income_growth_percentage)
    gh = float(s.get("growth_high_gt", 10))
    gmid = float(s.get("growth_mid_gte", 5))
    gmf = float(s.get("growth_mid_factor", 0.6))
    glf = float(s.get("growth_low_factor", 0.2))
    if g > gh:
        scores["income_growth_trend"] = gm
    elif g >= gmid:
        scores["income_growth_trend"] = round(gm * gmf, 2)
    else:
        scores["income_growth_trend"] = round(gm * glf, 2)
    em = float(s.get("employer_max", 37))
    er = s.get("employer_ratios") or {}
    default_er = float(er.get("default", 0.15))
    ratio = float(er.get(str(d.employer_category).upper(), default_er))
    scores["employer_category"] = round(em * ratio, 2)
    t = int(d.job_tenure_months)
    tm = float(s.get("tenure_max", 36))
    tb = s.get("tenure_bounds") or {}
    t1, t2, t3 = int(tb.get("tier1", 24)), int(tb.get("tier2", 12)), int(tb.get("tier3", 6))
    f1 = float(s.get("tenure_ge_24_factor", 1.0))
    f2 = float(s.get("tenure_ge_12_factor", 0.7))
    f3 = float(s.get("tenure_ge_6_factor", 0.4))
    f4 = float(s.get("tenure_low_factor", 0.1))
    if t >= t1:
        scores["job_tenure"] = round(tm * f1, 2)
    elif t >= t2:
        scores["job_tenure"] = round(tm * f2, 2)
    elif t >= t3:
        scores["job_tenure"] = round(tm * f3, 2)
    else:
        scores["job_tenure"] = round(tm * f4, 2)
    nmi = float(d.net_monthly_income)
    nm = float(s.get("nmi_max", 34))
    nb = s.get("nmi_bounds") or {}
    nf = s.get("nmi_factors") or {}
    b1, b2, b3 = float(nb.get("b1", 50000)), float(nb.get("b2", 30000)), float(nb.get("b3", 15000))
    ff1, ff2, ff3, ff4 = float(nf.get("f1", 1.0)), float(nf.get("f2", 0.75)), float(nf.get("f3", 0.5)), float(nf.get("f4", 0.25))
    if nmi >= b1:
        scores["net_monthly_income"] = round(nm * ff1, 2)
    elif nmi >= b2:
        scores["net_monthly_income"] = round(nm * ff2, 2)
    elif nmi >= b3:
        scores["net_monthly_income"] = round(nm * ff3, 2)
    else:
        scores["net_monthly_income"] = round(nm * ff4, 2)
    total = round(sum(scores.values()), 2)
    title = str(s.get("title", "Income & Employment"))
    return {"section": title, "max": smax, "score": min(total, smax), "breakdown": scores}


def score_tax_identifiers(d: Any, cfg: dict[str, Any]) -> dict:
    s = _g(cfg, "sections", "tax", default={}) or {}
    smax = float(s.get("max", 90))
    scores: dict[str, float] = {}
    pf = float(s.get("pan_full", 18))
    pp = float(s.get("pan_partial", 9))
    if d.pan_verified and d.pan_aadhaar_linked:
        scores["pan_verified"] = pf
    elif d.pan_verified:
        scores["pan_verified"] = pp
    else:
        scores["pan_verified"] = 0.0
    iy = int(d.itr_filing_years)
    im = float(s.get("itr_max", 23))
    iyf = int(s.get("itr_years_full_ge", 2))
    iy1 = float(s.get("itr_one_year_factor", 0.5))
    if iy >= iyf:
        scores["itr_filing_history"] = im
    elif iy == 1:
        scores["itr_filing_history"] = round(im * iy1, 2)
    else:
        scores["itr_filing_history"] = 0.0
    mm = float(d.income_mismatch_percentage)
    mx = float(s.get("mismatch_max", 18))
    m20 = float(s.get("mismatch_le_20", 20))
    m30 = float(s.get("mismatch_le_30", 30))
    m50 = float(s.get("mismatch_le_50", 50))
    mmid = float(s.get("mismatch_mid_factor", 0.6))
    mhi = float(s.get("mismatch_high_factor", 0.3))
    if mm <= m20:
        scores["income_match_itr_bank"] = mx
    elif mm <= m30:
        scores["income_match_itr_bank"] = round(mx * mmid, 2)
    elif mm <= m50:
        scores["income_match_itr_bank"] = round(mx * mhi, 2)
    else:
        scores["income_match_itr_bank"] = 0.0
    gf = float(s.get("gst_full", 18))
    gp = float(s.get("gst_partial", 9))
    if d.gst_active and d.gst_filing_regular:
        scores["gst_registration"] = gf
    elif d.gst_active:
        scores["gst_registration"] = gp
    else:
        scores["gst_registration"] = gf if d.tds_detected else 0.0
    f26 = float(s.get("form26_max", 13))
    f26s = float(s.get("form26_tds_scale", 3))
    if d.tds_detected and float(d.tds_amount) > 0:
        tds_ratio = min(float(d.tds_amount) / max(float(d.bank_income) / 12, 1), 1.0)
        scores["form_26as"] = round(f26 * min(tds_ratio * f26s, 1.0), 2)
    else:
        scores["form_26as"] = 0.0
    total = round(sum(scores.values()), 2)
    title = str(s.get("title", "Tax Identifiers"))
    return {"section": title, "max": smax, "score": min(total, smax), "breakdown": scores}


def score_dti(d: Any, cfg: dict[str, Any]) -> dict:
    s = _g(cfg, "sections", "dti", default={}) or {}
    smax = float(s.get("max", 140))
    dr = float(d.dti_ratio)
    dti = dr * 100 if dr <= 1 else dr
    bands = s.get("bands") or []
    default_pts = 0.0
    chosen: float | None = None
    for b in bands:
        if b.get("default"):
            default_pts = float(b.get("score", 0))
            continue
        if "lt" in b and dti < float(b["lt"]):
            chosen = float(b["score"])
            break
        if "lte" in b and dti <= float(b["lte"]):
            chosen = float(b["score"])
            break
    pts = chosen if chosen is not None else default_pts
    title = str(s.get("title", "Debt-to-Income Ratio"))
    return {
        "section": title,
        "max": smax,
        "score": pts,
        "breakdown": {"dti_ratio_pct": round(dti, 2), "dti_band_score": pts},
    }


def score_spending_pattern(d: Any, cfg: dict[str, Any]) -> dict:
    s = _g(cfg, "sections", "spending", default={}) or {}
    smax = float(s.get("max", 140))
    scores: dict[str, float] = {}
    em = float(s.get("essential_max", 28))
    e60 = float(s.get("essential_ge_60", 0.6))
    e50 = float(s.get("essential_ge_50", 0.5))
    emid = float(s.get("essential_mid_factor", 0.7))
    elow = float(s.get("essential_low_factor", 0.3))
    er = float(d.essential_spend_ratio)
    if er >= e60:
        scores["essential_vs_discretionary"] = em
    elif er >= e50:
        scores["essential_vs_discretionary"] = round(em * emid, 2)
    else:
        scores["essential_vs_discretionary"] = round(em * elow, 2)
    nm = float(s.get("negbal_max", 28))
    n2 = int(s.get("negbal_le_2", 2))
    nf1 = float(s.get("negbal_mid_factor", 0.6))
    nf2 = float(s.get("negbal_high_factor", 0.2))
    neg = int(d.negative_balance_months)
    if neg == 0:
        scores["month_end_balance"] = nm
    elif neg <= n2:
        scores["month_end_balance"] = round(nm * nf1, 2)
    else:
        scores["month_end_balance"] = round(nm * nf2, 2)
    base = float(s.get("merchant_base", 23))
    mpr = float(s.get("merchant_pts_per_risk", 8))
    mcap = float(s.get("merchant_deduction_cap", 24))
    deduction = float(d.merchant_risk_score) * mpr
    scores["merchant_category"] = max(round(base - min(deduction, mcap), 2), 0)
    cm = float(s.get("cash_max", 18))
    clt = float(s.get("cash_low_lt", 0.15))
    cmid = float(s.get("cash_mid_lte", 0.3))
    cf1 = float(s.get("cash_mid_factor", 0.6))
    cf2 = float(s.get("cash_low_factor", 0.2))
    cwr = float(d.cash_withdrawal_ratio)
    if cwr < clt:
        scores["cash_withdrawal"] = cm
    elif cwr <= cmid:
        scores["cash_withdrawal"] = round(cm * cf1, 2)
    else:
        scores["cash_withdrawal"] = round(cm * cf2, 2)
    imx = float(s.get("impulse_max", 18))
    i1 = float(s.get("impulse_le_01", 0.1))
    i3 = float(s.get("impulse_le_03", 0.3))
    if1 = float(s.get("impulse_mid_factor", 0.7))
    if2 = float(s.get("impulse_high_factor", 0.4))
    isi = float(d.impulse_spending_index)
    if isi == 0:
        scores["impulse_spending"] = imx
    elif isi <= i1:
        scores["impulse_spending"] = round(imx * if1, 2)
    elif isi <= i3:
        scores["impulse_spending"] = round(imx * if2, 2)
    else:
        scores["impulse_spending"] = 0.0
    sv = float(s.get("savings_max", 25))
    s20 = float(s.get("savings_ge_20", 0.2))
    s10 = float(s.get("savings_ge_10", 0.1))
    sf1 = float(s.get("savings_mid_factor", 0.6))
    sf2 = float(s.get("savings_low_factor", 0.3))
    sr = float(d.monthly_savings_rate)
    if sr >= s20:
        scores["savings_rate"] = sv
    elif sr >= s10:
        scores["savings_rate"] = round(sv * sf1, 2)
    elif sr >= 0:
        scores["savings_rate"] = round(sv * sf2, 2)
    else:
        scores["savings_rate"] = 0.0
    total = round(sum(scores.values()), 2)
    title = str(s.get("title", "Spending Pattern"))
    return {"section": title, "max": smax, "score": min(total, smax), "breakdown": scores}


def score_account_hygiene(d: Any, cfg: dict[str, Any]) -> dict:
    s = _g(cfg, "sections", "hygiene", default={}) or {}
    smax = float(s.get("max", 140))
    scores: dict[str, float] = {}
    bo0 = float(s.get("bounce_out_max", 55))
    bo2 = float(s.get("bounce_out_le_2", 28))
    bo5 = float(s.get("bounce_out_le_5", 10))
    bc = int(d.bounce_count_outward)
    if bc == 0:
        scores["bounce_count"] = bo0
    elif bc <= 2:
        scores["bounce_count"] = bo2
    elif bc <= 5:
        scores["bounce_count"] = bo5
    else:
        scores["bounce_count"] = 0.0
    bim = float(s.get("bounce_in_max", 18))
    bif1 = float(s.get("bounce_in_eq1_factor", 0.6))
    bif2 = float(s.get("bounce_in_else_factor", 0.2))
    ib = int(d.bounce_count_inward)
    if ib == 0:
        scores["inward_bounce"] = bim
    elif ib == 1:
        scores["inward_bounce"] = round(bim * bif1, 2)
    else:
        scores["inward_bounce"] = round(bim * bif2, 2)
    odmax = float(s.get("od_max", 18))
    od30 = float(s.get("od_le_30", 0.3))
    od60 = float(s.get("od_le_60", 0.6))
    odf1 = float(s.get("od_mid_factor", 0.5))
    odf2 = float(s.get("od_high_factor", 0.2))
    od = float(d.od_utilization_ratio)
    if od <= od30:
        scores["od_utilization"] = odmax
    elif od <= od60:
        scores["od_utilization"] = round(odmax * odf1, 2)
    else:
        scores["od_utilization"] = round(odmax * odf2, 2)
    lm = float(s.get("late_max", 23))
    lf1 = float(s.get("late_le_2_factor", 0.65))
    lf2 = float(s.get("late_high_factor", 0.2))
    lp = int(d.late_payment_count)
    if lp == 0:
        scores["late_payments"] = lm
    elif lp <= 2:
        scores["late_payments"] = round(lm * lf1, 2)
    else:
        scores["late_payments"] = round(lm * lf2, 2)
    am = float(s.get("amb_max", 26))
    trend_map = s.get("amb_trend_factors") or {"RISING": 1.0, "FLAT": 0.6, "DECLINING": 0.25, "default": 0.25}
    ratio = float(trend_map.get(str(d.amb_trend).upper(), trend_map.get("default", 0.25)))
    scores["amb_trend"] = round(am * ratio, 2)
    total = round(sum(scores.values()), 2)
    title = str(s.get("title", "Account Hygiene"))
    return {"section": title, "max": smax, "score": min(total, smax), "breakdown": scores}


def score_utility_bills(d: Any, cfg: dict[str, Any]) -> dict:
    s = _g(cfg, "sections", "utility", default={}) or {}
    smax = float(s.get("max", 90))
    late = int(d.utility_late_payments)
    f2 = float(s.get("late_le_2_factor", 0.7))
    f4 = float(s.get("late_le_4_factor", 0.4))
    bill_max = s.get("bill_max") or {}

    def bill_pts(key: str, is_regular: bool) -> float:
        max_pts = float(bill_max.get(key, 0))
        if not is_regular:
            return 0.0
        if late == 0:
            return max_pts
        if late <= 2:
            return round(max_pts * f2, 2)
        if late <= 4:
            return round(max_pts * f4, 2)
        return 0.0

    scores = {
        "electricity": bill_pts("electricity", bool(d.electricity_payment_regular)),
        "gas": bill_pts("gas", bool(d.gas_payment_regular)),
        "mobile_bill": bill_pts("mobile_bill", bool(d.mobile_bill_regular)),
        "broadband": bill_pts("broadband", bool(d.broadband_payment_regular)),
        "rent": bill_pts("rent", bool(d.rent_payment_regular)),
        "water": bill_pts("water", bool(d.water_bill_regular)),
    }
    total = round(sum(scores.values()), 2)
    title = str(s.get("title", "Utility Bill Payments"))
    return {"section": title, "max": smax, "score": min(total, smax), "breakdown": scores}


def score_investments(d: Any, cfg: dict[str, Any]) -> dict:
    s = _g(cfg, "sections", "investments", default={}) or {}
    smax = float(s.get("max", 90))
    scores: dict[str, float] = {}
    sipm = float(s.get("sip_max", 28))
    sipmo = int(s.get("sip_months_ge", 6))
    sipp = float(s.get("sip_partial_factor", 0.5))
    if d.sip_active and int(d.sip_consistency_months) >= sipmo:
        scores["sip"] = sipm
    elif d.sip_active:
        scores["sip"] = round(sipm * sipp, 2)
    else:
        scores["sip"] = 0.0
    fd = float(d.fd_amount)
    fdh = float(s.get("fd_high_ge", 50000))
    fdhp = float(s.get("fd_high_pts", 22))
    fdm = float(s.get("fd_mid_ge", 10000))
    fdmp = float(s.get("fd_mid_pts", 11))
    fdcl = float(s.get("fd_closure_factor", 0.5))
    if fd >= fdh:
        base = fdhp
    elif fd >= fdm:
        base = fdmp
    else:
        base = 0.0
    if d.fd_recent_closure:
        base = round(base * fdcl, 2)
    scores["fd"] = base
    scores["rd"] = float(s.get("rd_max", 18)) if d.rd_active else 0.0
    dm = float(s.get("demat_max", 13))
    dpv = float(s.get("demat_pv_ge", 5000))
    dpf = float(s.get("demat_partial_factor", 0.5))
    if d.demat_active and float(d.portfolio_value) >= dpv:
        scores["demat"] = dm
    elif d.demat_active:
        scores["demat"] = round(dm * dpf, 2)
    else:
        scores["demat"] = 0.0
    pn = float(s.get("ppf_nps_max", 9))
    scores["ppf_nps"] = pn if (d.ppf_contribution or d.nps_contribution) else 0.0
    total = round(sum(scores.values()), 2)
    title = str(s.get("title", "Investments & Holdings"))
    return {"section": title, "max": smax, "score": min(total, smax), "breakdown": scores}


def score_behavioural(d: Any, cfg: dict[str, Any]) -> dict:
    s = _g(cfg, "sections", "behavioural", default={}) or {}
    smax = float(s.get("max", 50))
    scores: dict[str, float] = {}
    cm = float(s.get("completeness_max", 15))
    dm = float(s.get("device_max", 15))
    simlt = int(s.get("sim_age_penalty_lt", 30))
    simp = float(s.get("sim_age_penalty_pts", 8))
    nh0 = int(s.get("night_hour_start", 2))
    nh1 = int(s.get("night_hour_end", 5))
    tm = float(s.get("time_max", 10))
    nf = float(s.get("night_factor", 0.7))
    pm = float(s.get("purpose_max", 10))
    scores["completeness"] = round(cm * float(d.application_completeness_score), 2)
    base_device = round(dm * float(d.device_trust_score), 2)
    if d.is_rooted_device or d.is_emulator:
        base_device = 0.0
    if int(d.sim_age_days) < simlt:
        base_device = max(base_device - simp, 0)
    if d.multiple_apps_same_device:
        base_device = 0.0
    scores["device_trust"] = round(base_device, 2)
    h = int(d.application_hour)
    if nh0 <= h <= nh1:
        scores["application_time"] = round(tm * nf, 2)
    else:
        scores["application_time"] = tm
    scores["loan_purpose"] = round(pm * float(d.loan_purpose_match_score), 2)
    total = round(sum(scores.values()), 2)
    title = str(s.get("title", "Behavioural & Intent"))
    return {"section": title, "max": smax, "score": min(total, smax), "breakdown": scores}


def score_enquiry_history(d: Any, cfg: dict[str, Any]) -> dict:
    s = _g(cfg, "sections", "enquiry", default={}) or {}
    smax = float(s.get("max", 120))
    scores: dict[str, float] = {}
    e3 = int(d.enquiries_last_3_months)
    if e3 == 0:
        scores["enquiries_3m"] = float(s.get("e3_eq0", 25))
    elif e3 <= 2:
        scores["enquiries_3m"] = float(s.get("e3_le2", 15))
    elif e3 <= 4:
        scores["enquiries_3m"] = float(s.get("e3_le4", 5))
    else:
        scores["enquiries_3m"] = float(s.get("e3_else", 0))
    e12 = int(d.enquiries_last_12_months)
    if e12 == 0:
        scores["enquiries_12m"] = float(s.get("e12_eq0", 20))
    elif e12 <= 3:
        scores["enquiries_12m"] = float(s.get("e12_le3", 14))
    elif e12 <= 6:
        scores["enquiries_12m"] = float(s.get("e12_le6", 6))
    else:
        scores["enquiries_12m"] = float(s.get("e12_else", 0))
    iok = float(s.get("internal_ok", 20))
    igt = float(s.get("internal_gt12", 14))
    ige = float(s.get("internal_ge6", 8))
    if not d.internal_rejection_flag:
        scores["internal_rejection"] = iok
    else:
        m = int(d.months_since_last_rejection)
        if m > 12:
            scores["internal_rejection"] = igt
        elif m >= 6:
            scores["internal_rejection"] = ige
        else:
            scores["internal_rejection"] = 0.0
    rmx = float(s.get("recency_max", 10))
    rlam = float(s.get("recency_decay_lambda", 0.1))
    if d.internal_rejection_flag and int(d.months_since_last_rejection) > 0:
        decay = round(rmx * math.exp(-rlam * int(d.months_since_last_rejection)), 2)
        scores["recency_decay"] = min(decay, rmx)
    else:
        scores["recency_decay"] = rmx
    reapp = 0.0
    ige_inc = float(s.get("reapp_income_ge", 15))
    ige_pts = float(s.get("reapp_income_pts", 10))
    rln = float(s.get("reapp_loan_neg_pts", 5))
    rcap = float(s.get("reapp_cap", 25))
    if float(d.income_change_since_last_application) >= ige_inc:
        reapp += ige_pts
    if float(d.loan_amount_change) < 0:
        reapp += rln
    scores["reapplication_quality"] = min(reapp, rcap)
    lmx = float(s.get("lender_max", 20))
    lender_map = s.get("lender_ratios") or {}
    ldef = float(lender_map.get("default", 0.6))
    ratio = float(lender_map.get(str(d.lender_type_mix).upper(), ldef))
    scores["lender_type_mix"] = round(lmx * ratio, 2)
    total = round(sum(scores.values()), 2)
    title = str(s.get("title", "Application & Enquiry History"))
    return {"section": title, "max": smax, "score": min(total, smax), "breakdown": scores}


def check_hard_declines(d: Any, cfg: dict[str, Any]) -> list[str]:
    hd = _g(cfg, "hard_decline", default={}) or {}
    reasons: list[str] = []
    if d.kyc_fraud_flag:
        reasons.append("CKYC fraud flag detected")
    if d.is_rooted_device or d.is_emulator:
        reasons.append("Rooted or emulated device detected")
    dr = float(d.dti_ratio)
    dti_pct = dr * 100 if dr <= 1 else dr
    dti_lim = float(hd.get("dti_pct_gt", 50))
    if dti_pct > dti_lim:
        reasons.append(f"DTI breach: {dti_pct:.1f}% exceeds {dti_lim}% limit")
    enq_ge = int(hd.get("enquiries_3m_gte", 5))
    if int(d.enquiries_last_3_months) >= enq_ge:
        reasons.append(f"Hard enquiry overload: {int(d.enquiries_last_3_months)} enquiries in last 3 months")
    cool = int(hd.get("cooling_months_since_rejection_lt", 1))
    if d.internal_rejection_flag and int(d.months_since_last_rejection) < cool:
        reasons.append("Cooling period violation: rejection within last 30 days")
    return reasons


def get_band(score: float, cfg: dict[str, Any]) -> dict:
    bands = list(cfg.get("risk_bands") or [])
    bands.sort(key=lambda x: float(x.get("min_score", 0)), reverse=True)
    for b in bands:
        if score >= float(b.get("min_score", 0)):
            return {k: v for k, v in b.items() if k != "min_score"}
    return copy.deepcopy(cfg.get("risk_band_fallback") or {})


def score_flat(d: Any, cfg: dict[str, Any]) -> dict:
    hard = check_hard_declines(d, cfg)
    s1 = score_income_employment(d, cfg)
    s2 = score_tax_identifiers(d, cfg)
    s3 = score_dti(d, cfg)
    s4 = score_spending_pattern(d, cfg)
    s5 = score_account_hygiene(d, cfg)
    s6 = score_utility_bills(d, cfg)
    s7 = score_investments(d, cfg)
    s8 = score_behavioural(d, cfg)
    s9 = score_enquiry_history(d, cfg)
    section_scores = {
        "income": s1,
        "tax": s2,
        "dti": s3,
        "spending": s4,
        "hygiene": s5,
        "utility": s6,
        "investments": s7,
        "behavioural": s8,
        "enquiry": s9,
    }
    max_den = configured_max_score(cfg)
    hdb = cfg.get("hard_decline_band") or {}
    if hard:
        final = 0.0
        band = copy.deepcopy(hdb)
    else:
        final = round(sum(s["score"] for s in section_scores.values()), 2)
        band = get_band(final, cfg)
    pct = round(final / max_den * 100, 2) if max_den > 0 else 0.0
    return {
        "hard_decline": bool(hard),
        "hard_decline_reasons": hard,
        "total_score": final,
        "max_score": max_den,
        "score_percentage": pct,
        "risk_band": band,
        "section_scores": [{k: v for k, v in s.items() if k != "breakdown"} for s in section_scores.values()],
        "section_breakdown": section_scores,
        "scoring_schema_version": cfg.get("schema_version"),
    }


def score_nested_case(app: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    meta = app.get("meta") if isinstance(app.get("meta"), dict) else {}
    app_id = meta.get("application_id")
    flat = nested_to_flat(app)
    result = score_flat(flat, cfg)
    if app_id:
        result["application_id"] = app_id
    if meta:
        result["meta"] = meta
    return result


def score_payload(body: Any) -> Any:
    if isinstance(body, list):
        out: list[dict[str, Any]] = []
        for item in body:
            if not isinstance(item, dict):
                continue
            if set(item.keys()) == {"_comment"}:
                continue
            ov = item.get("scoring_config") if isinstance(item.get("scoring_config"), dict) else None
            app = {k: v for k, v in item.items() if k != "scoring_config"}
            cfg = merged_weights(ov)
            out.append(score_nested_case(app, cfg))
        return out
    if isinstance(body, dict):
        ov = body.get("scoring_config") if isinstance(body.get("scoring_config"), dict) else None
        app = {k: v for k, v in body.items() if k != "scoring_config"}
        cfg = merged_weights(ov)
        return score_nested_case(app, cfg)
    raise ValueError("Body must be a JSON object or array of objects")


# ── OpenAPI / Swagger examples (test_cases.json shape) ───────────────────────

_SCORE_EXAMPLE_SINGLE: dict[str, Any] = {
    "income": {
        "salary_credit_regularity": 12,
        "income_growth_percentage": 8,
        "employer_category": "PRIVATE_LTD",
        "job_tenure_months": 24,
        "net_monthly_income": 48000,
        "income_stability_index": 85,
        "salary_variance": 5,
        "income_consistency_months": 12,
    },
    "tax": {
        "pan_verified": 1,
        "pan_aadhaar_linked": 1,
        "itr_filing_years": 2,
        "itr_income": 550000,
        "bank_income": 576000,
        "income_mismatch_percentage": 4.5,
        "gst_active": 0,
        "gst_filing_regular": 0,
        "tds_detected": 1,
        "tds_amount": 12000,
    },
    "dti": {
        "total_monthly_obligations": 14400,
        "net_monthly_income": 48000,
        "dti_ratio": 30,
        "emi_outflows": 0,
        "rent_outflow": 12000,
        "insurance_outflow": 2400,
    },
    "spending": {
        "essential_spend_ratio": 55,
        "discretionary_spend_ratio": 45,
        "negative_balance_months": 0,
        "cash_withdrawal_ratio": 15,
        "impulse_spending_index": 20,
        "monthly_savings_rate": 10,
        "merchant_risk_score": 85,
    },
    "account_hygiene": {
        "bounce_count_outward": 0,
        "bounce_count_inward": 0,
        "od_utilization_ratio": 0,
        "late_payment_count": 0,
        "amb_trend": "FLAT",
    },
    "utility": {
        "electricity_payment_regular": 1,
        "mobile_bill_regular": 1,
        "utility_late_payments": 0,
    },
    "investment": {"sip_active": 0, "fd_amount": 0},
    "behavioral": {
        "application_completeness_score": 100,
        "device_trust_score": 90,
        "is_rooted_device": 0,
        "is_emulator": 0,
        "sim_age_days": 800,
        "multiple_apps_same_device": 0,
        "application_hour": 18,
        "loan_purpose_match_score": 80,
    },
    "enquiry": {
        "enquiries_last_3_months": 1,
        "enquiries_last_12_months": 2,
        "internal_rejection_flag": 0,
        "lender_type_mix": "BANK",
    },
    "risk_flags": {
        "kyc_fraud_flag": 0,
        "device_risk_flag": 0,
        "dti_exceeded": 0,
        "high_enquiry_flag": 0,
        "recent_rejection_flag": 0,
    },
    "meta": {
        "application_id": "example-app-id",
        "user_id": "USR-00001",
        "source": "swagger",
    },
}


# ── FastAPI (Swagger at /docs, OpenAPI JSON at /openapi.json) ────────────────

app = FastAPI(
    title="NTC Scoring API",
    version="1.0",
    description=(
        "NTC surrogate scorecard: nested JSON like `test_cases.json` (**one object** or **array**). "
        "Default weights: `scoring_weights.json` next to this module. "
        "Optional per-request override: add `\"scoring_config\": { ... }` (partial JSON, deep-merged). "
        "Inspect defaults: **GET /scoring-config**. Reload file without restart: **POST /scoring-config/reload**."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Scoring", "description": "Loan application scoring"},
        {"name": "Configuration", "description": "Scoring weights (view / reload)"},
        {"name": "Health", "description": "Service health"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"], summary="Liveness check")
def health():
    return {"status": "ok"}


@app.get(
    "/scoring-config",
    tags=["Configuration"],
    summary="View active scoring weights",
    description="Returns the merged-in-memory defaults loaded from `scoring_weights.json` (copy; safe to inspect in Swagger).",
)
def get_scoring_config():
    return copy.deepcopy(get_active_weights())


@app.post(
    "/scoring-config/reload",
    tags=["Configuration"],
    summary="Reload scoring_weights.json from disk",
    description="Re-reads `scoring_weights.json` without restarting the server. Fails if the file is missing.",
)
def reload_scoring_config():
    w = refresh_scoring_weights()
    return {"ok": True, "schema_version": w.get("schema_version"), "weights_path": str(_WEIGHTS_PATH)}


@app.post(
    "/score",
    tags=["Scoring"],
    summary="Score one or many applications",
    description=(
        "Body: one nested application object or an array (like `test_cases.json`). "
        "Optional top-level **`scoring_config`**: partial object merged over `scoring_weights.json` for this request only. "
        "See **GET /scoring-config** for the full weight schema."
    ),
    responses={
        200: {
            "description": "Score result (object) or list of results (array input)",
            "content": {
                "application/json": {
                    "example": {
                        "application_id": "example-app-id",
                        "hard_decline": False,
                        "hard_decline_reasons": [],
                        "total_score": 720.5,
                        "max_score": 1000,
                        "score_percentage": 72.05,
                        "risk_band": {
                            "band": "Standard NTC",
                            "decision": "Auto Approve",
                            "max_loan": 50000,
                            "interest_rate": "20-24% p.a.",
                            "review": "None",
                        },
                    }
                }
            },
        }
    },
)
def post_score(
    payload: Any = Body(
        ...,
        openapi_examples={
            "single_application": {
                "summary": "One application (nested)",
                "description": "Same shape as one element in test_cases.json.",
                "value": _SCORE_EXAMPLE_SINGLE,
            },
            "batch": {
                "summary": "Batch (array)",
                "description": "Array of nested application objects.",
                "value": [_SCORE_EXAMPLE_SINGLE],
            },
        },
    ),
):
    return score_payload(payload)
