"""
src/data/generator.py
---------------------
Telecom Revenue Assurance -- Synthetic Dataset Generator v2.0

Generates all 23 tables with 42 leakage types injected.
Config is read from config/config.yaml via src.utils.config.

Run directly:
    python -m src.data.generator

Or via Makefile:
    make data
"""

import sqlite3, random, uuid, datetime, os, json, math, copy
import numpy as np
import pandas as pd

# -- config -- replace ALL hardcoded values with cfg ----------
try:
    from src.utils.config import cfg, ensure_dirs
    OUTPUT_DIR   = str(cfg.db_path.parent)
    DB_PATH      = str(cfg.db_path)
    N_SUBSCRIBERS = cfg.n_subscribers
    N_TOWERS      = cfg.n_towers
    N_DAYS        = cfg.n_days
    LEAKAGE_RATE  = cfg.leakage_rate
    RANDOM_SEED   = cfg.random_seed
except ImportError:
    # Fallback when running standalone outside the package
    print("[generator] WARNING: running without config -- using defaults")
    OUTPUT_DIR    = "data/raw"
    DB_PATH       = "data/raw/telecom_ra.db"
    N_SUBSCRIBERS = 3000
    N_TOWERS      = 200
    N_DAYS        = 90
    LEAKAGE_RATE  = 0.07
    RANDOM_SEED   = 42

os.makedirs(OUTPUT_DIR, exist_ok=True)

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

# -------------------------------------------------------------
# DATE RANGE
# -------------------------------------------------------------
START_DATE = datetime.datetime(2024, 1, 1)
END_DATE   = datetime.datetime(2024, 3, 31, 23, 59, 59)

# -------------------------------------------------------------
# DOMAIN CONSTANTS (unchanged from v2)
# -------------------------------------------------------------
REGIONS      = ["North", "South", "East", "West", "Central"]
OPERATORS    = ["OpA", "OpB", "OpC", "OpD"]
TOWER_TYPES  = ["macro", "micro", "pico", "indoor"]
CALL_TYPES   = ["voice", "sms", "data", "video"]
TERMINATIONS = ["normal", "busy", "no_answer", "dropped", "rejected"]
ROAMING_PARTNERS = [
    ("India","IN"),("UAE","AE"),("UK","GB"),("USA","US"),
    ("Singapore","SG"),("Germany","DE"),("France","FR"),("Japan","JP")
]
CREDIT_CLASSES     = ["AAA","AA","A","BBB","BB","B","C"]
DEVICE_TYPES       = ["smartphone","feature_phone","tablet","router","iot","modem"]
APP_CATEGORIES     = ["social","streaming","gaming","voip","browsing","unknown"]
ROUTE_TYPES        = ["domestic","international","transit","bypass","grey"]
SIGNALING          = ["SIP","SS7","H323","ISUP","unknown"]
DESTINATION_TYPES  = ["normal","premium","international","satellite","unknown"]
NUMBER_RANGE_TYPES = ["geographic","non-geographic","premium","mobile","international"]
ACCESS_TYPES       = ["direct","pbx","voip_gateway","reseller","unknown"]
VAS_TYPES          = ["ringtone","wallpaper","news","sports","astrology","music","games"]
AGENT_IDS          = [f"AGT{i:04d}" for i in range(1, 51)]
PARTNER_NAMES      = ["ContentCo","MusicStream","NewsPlus","GameZone","SportsPro"]

PLAN_CATALOGUE = [
    {"plan_id":"PL001","plan_name":"Basic Voice",     "plan_type":"prepaid",  "monthly_rent":99,
     "voice_rate_per_min":1.50,"sms_rate":0.50,"data_rate_per_mb":2.00,
     "roaming_multiplier":3.0,"free_mins":100, "free_sms":50,  "free_data_mb":500,
     "valid_from":"2023-01-01","valid_to":"2099-12-31","promo_eligible":1},
    {"plan_id":"PL002","plan_name":"Smart Unlimited", "plan_type":"postpaid", "monthly_rent":399,
     "voice_rate_per_min":0.00,"sms_rate":0.00,"data_rate_per_mb":0.00,
     "roaming_multiplier":2.5,"free_mins":99999,"free_sms":9999,"free_data_mb":50000,
     "valid_from":"2023-01-01","valid_to":"2099-12-31","promo_eligible":1},
    {"plan_id":"PL003","plan_name":"Data Plus",       "plan_type":"postpaid", "monthly_rent":249,
     "voice_rate_per_min":0.50,"sms_rate":0.25,"data_rate_per_mb":0.00,
     "roaming_multiplier":2.0,"free_mins":500, "free_sms":200, "free_data_mb":99999,
     "valid_from":"2023-01-01","valid_to":"2099-12-31","promo_eligible":1},
    {"plan_id":"PL004","plan_name":"Corporate Elite", "plan_type":"corporate","monthly_rent":799,
     "voice_rate_per_min":0.00,"sms_rate":0.00,"data_rate_per_mb":0.00,
     "roaming_multiplier":1.5,"free_mins":99999,"free_sms":9999,"free_data_mb":99999,
     "valid_from":"2023-01-01","valid_to":"2099-12-31","promo_eligible":0},
    {"plan_id":"PL005","plan_name":"Budget Talk",     "plan_type":"prepaid",  "monthly_rent":49,
     "voice_rate_per_min":2.00,"sms_rate":1.00,"data_rate_per_mb":3.00,
     "roaming_multiplier":4.0,"free_mins":30,  "free_sms":20,  "free_data_mb":200,
     "valid_from":"2023-01-01","valid_to":"2099-12-31","promo_eligible":1},
    {"plan_id":"PL006","plan_name":"Youth Pack",      "plan_type":"prepaid",  "monthly_rent":149,
     "voice_rate_per_min":1.00,"sms_rate":0.25,"data_rate_per_mb":0.00,
     "roaming_multiplier":3.5,"free_mins":200, "free_sms":100, "free_data_mb":10000,
     "valid_from":"2023-01-01","valid_to":"2099-12-31","promo_eligible":1},
    {"plan_id":"PL007","plan_name":"Legacy 2G",       "plan_type":"prepaid",  "monthly_rent":29,
     "voice_rate_per_min":3.00,"sms_rate":1.50,"data_rate_per_mb":5.00,
     "roaming_multiplier":5.0,"free_mins":10,  "free_sms":10,  "free_data_mb":50,
     "valid_from":"2020-01-01","valid_to":"2023-12-31","promo_eligible":0},
]

# -------------------------------------------------------------
# UTILS
# -------------------------------------------------------------
def uid():
    return str(uuid.uuid4())

def rand_msisdn(prefix="91"):
    return f"+{prefix}{random.randint(7000000000,9999999999)}"

def rand_dt(start=START_DATE, end=END_DATE):
    delta = int((end - start).total_seconds())
    return start + datetime.timedelta(seconds=random.randint(0, delta))

def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def fmtd(dt):
    return dt.strftime("%Y-%m-%d")

def mk(s):
    """Return YYYY-MM from a datetime string."""
    return s[:7]

def rate_cdr(call_type, duration_sec, data_mb, is_roaming, plan):
    """Calculate the correct charge for a CDR given its plan."""
    rm = plan["roaming_multiplier"] if is_roaming else 1.0
    if call_type in ("voice", "video"):
        billable = max(0, duration_sec / 60 - plan["free_mins"] / 30)
        mult = 1.5 if call_type == "video" else 1.0
        return round(billable * plan["voice_rate_per_min"] * mult * rm, 4)
    elif call_type == "sms":
        return round(max(0, 1 - plan["free_sms"] / 100) * plan["sms_rate"] * rm, 4)
    elif call_type == "data":
        billable_mb = max(0, data_mb - plan["free_data_mb"] / 30)
        return round(billable_mb * plan["data_rate_per_mb"] * rm, 4)
    return 0.0


# -------------------------------------------------------------
# LEAKAGE DISTRIBUTION -- 42 types weighted
# -------------------------------------------------------------
LEAKAGE_DIST = {
    "L1_unbilled":          0.070,
    "L4_duplicate":         0.060,
    "L7_suppression":       0.030,
    "L8_late_cdr":          0.025,
    "L9_partial_cdr":       0.020,
    "L10_timestamp_fraud":  0.015,
    "L2_wrong_tariff":      0.065,
    "L11_free_period":      0.020,
    "L12_promo_abuse":      0.025,
    "L13_rounding":         0.030,
    "L14_bundle_mismatch":  0.020,
    "L15_expired_plan":     0.015,
    "L3_roaming_gap":       0.055,
    "L16_interconnect_bypass": 0.030,
    "L17_tap_errors":       0.020,
    "L18_rate_arbitrage":   0.015,
    "L19_mvno_leakage":     0.015,
    "L20_grey_voip":        0.020,
    "L21_ghost_sub":        0.025,
    "L22_plan_downgrade":   0.020,
    "L23_sim_swap":         0.015,
    "L24_multi_sim":        0.015,
    "L25_corporate_misuse": 0.015,
    "L26_subsidy_abuse":    0.010,
    "L6_simbox":            0.035,
    "L27_irsf":             0.025,
    "L28_wangiri":          0.020,
    "L29_pbx_hack":         0.015,
    "L30_credit_abuse":     0.015,
    "L31_internal_fraud":   0.010,
    "L5_zero_rated":        0.040,
    "L32_vas_billing":      0.020,
    "L33_tethering":        0.020,
    "L34_api_billing":      0.015,
    "L35_iot_billing":      0.015,
    "L36_ott_bypass":       0.020,
    "L37_invoice_suppress": 0.015,
    "L38_writeoff_abuse":   0.010,
    "L39_credit_fraud":     0.015,
    "L40_payment_mispost":  0.015,
    "L41_tax_leakage":      0.020,
    "L42_partner_settle":   0.010,
}
# Normalise so weights sum to 1.0
_total_w = sum(LEAKAGE_DIST.values())
LEAKAGE_DIST = {k: v / _total_w for k, v in LEAKAGE_DIST.items()}


# -------------------------------------------------------------
# MAIN GENERATION FUNCTION
# -------------------------------------------------------------
def generate(output_dir: str = None, db_path: str = None,
             n_subscribers: int = None, n_towers: int = None,
             n_days: int = None, leakage_rate: float = None,
             random_seed: int = None):
    """
    Generate the full telecom RA synthetic dataset.

    All parameters default to values from config.yaml when not supplied.
    """
    out_dir      = output_dir   or OUTPUT_DIR
    db           = db_path      or DB_PATH
    n_subs       = n_subscribers or N_SUBSCRIBERS
    n_tow        = n_towers     or N_TOWERS
    n_d          = n_days       or N_DAYS
    l_rate       = leakage_rate if leakage_rate is not None else LEAKAGE_RATE
    seed         = random_seed  if random_seed  is not None else RANDOM_SEED

    os.makedirs(out_dir, exist_ok=True)
    random.seed(seed)
    np.random.seed(seed)

    plan_map = {p["plan_id"]: p for p in PLAN_CATALOGUE}

    # -- 1. Plans ---------------------------------------------
    print("Generating plans...")
    plans_df = pd.DataFrame(PLAN_CATALOGUE)

    # -- 2. Cell towers ---------------------------------------
    print("Generating towers...")
    towers = []
    for i in range(n_tow):
        towers.append({
            "tower_id":         f"TWR{i+1:04d}",
            "region":            random.choice(REGIONS),
            "tower_type":        random.choice(TOWER_TYPES),
            "operator":          random.choice(OPERATORS),
            "latitude":          round(random.uniform(8.0,35.0),6),
            "longitude":         round(random.uniform(68.0,97.0),6),
            "capacity_erlangs":  random.randint(50,500),
            "is_active":         random.choices([1,0],[95,5])[0],
            "interconnect_type": random.choice(["domestic","international","both"]),
        })
    towers_df = pd.DataFrame(towers)

    # -- 3. Subscribers ---------------------------------------
    print("Generating subscribers...")
    plan_ids = [p["plan_id"] for p in PLAN_CATALOGUE if p["plan_id"] != "PL007"]
    plan_wts = [25,20,20,10,15,10]
    subscribers = []
    for i in range(n_subs):
        reg_dt   = rand_dt(START_DATE - datetime.timedelta(days=730), START_DATE)
        plan_id  = random.choices(plan_ids, weights=plan_wts)[0]
        is_act   = random.choices([1,0],[92,8])[0]
        ctype    = random.choices(["individual","corporate","wholesale","mvno"],[78,14,4,4])[0]
        churn_dt = rand_dt(START_DATE - datetime.timedelta(days=180), END_DATE) if not is_act else None
        last_act = rand_dt(START_DATE - datetime.timedelta(days=random.randint(0,180)), END_DATE)
        subscribers.append({
            "subscriber_id":     f"SUB{i+1:05d}",
            "msisdn":             rand_msisdn(),
            "imsi":              f"404{random.randint(10,99)}{random.randint(1000000000,9999999999)}",
            "plan_id":            plan_id,
            "region":             random.choice(REGIONS),
            "credit_class":       random.choices(CREDIT_CLASSES,[5,10,25,30,15,10,5])[0],
            "registration_date":  fmt(reg_dt),
            "is_active":          is_act,
            "customer_type":      ctype,
            "avg_monthly_spend":  round(random.uniform(50,2000),2),
            "churn_date":         fmt(churn_dt) if churn_dt else "",
            "last_activity_date": fmt(last_act),
            "device_category":    random.choice(["consumer","iot","enterprise","wholesale"]),
            "linked_account_id":  f"SUB{random.randint(1,n_subs):05d}" if random.random()<0.1 else "",
            "subsidy_device_id":  f"DEV{random.randint(10000,99999)}" if random.random()<0.2 else "",
        })
    subscribers_df = pd.DataFrame(subscribers)
    sub_map     = {s["subscriber_id"]: s for s in subscribers}
    active_subs = [s for s in subscribers if s["is_active"]]

    # -- 4. Plan change history -------------------------------
    print("Generating plan change history...")
    plan_changes = []
    for sub in random.sample(subscribers, int(n_subs*0.25)):
        old_plan = random.choice(plan_ids)
        new_plan = random.choice([p for p in plan_ids if p != old_plan])
        change_dt = rand_dt(START_DATE - datetime.timedelta(days=60), END_DATE)
        plan_changes.append({
            "change_id":     f"CHG{uid()[:8]}",
            "subscriber_id": sub["subscriber_id"],
            "old_plan_id":   old_plan,
            "new_plan_id":   new_plan,
            "change_date":   fmt(change_dt),
            "change_reason": random.choice(["upgrade","downgrade","migration","promo","retention"]),
            "agent_id":      random.choice(AGENT_IDS),
            "effective_date":fmt(change_dt + datetime.timedelta(days=random.randint(0,3))),
        })
    plan_changes_df = pd.DataFrame(plan_changes)

    # -- 5. Subscriber addons ---------------------------------
    print("Generating subscriber addons...")
    ADDON_TYPES = ["extra_data_1gb","extra_data_5gb","roaming_pack",
                   "sms_pack","night_data","caller_tune"]
    addons = []
    for sub in random.sample(subscribers, int(n_subs*0.40)):
        act_dt = rand_dt(START_DATE - datetime.timedelta(days=90), END_DATE)
        addons.append({
            "addon_id":       f"ADN{uid()[:8]}",
            "subscriber_id":  sub["subscriber_id"],
            "addon_type":     random.choice(ADDON_TYPES),
            "addon_charge":   round(random.uniform(10,199),2),
            "activated_date": fmt(act_dt),
            "expiry_date":    fmt(act_dt + datetime.timedelta(days=random.randint(7,90))),
            "is_active":      random.choices([1,0],[80,20])[0],
            "billing_applied":random.choices([1,0],[90,10])[0],
        })
    addons_df = pd.DataFrame(addons)

    # -- 6. Promotions ----------------------------------------
    print("Generating promotions...")
    PROMO_CODES = [f"PROMO{i:03d}" for i in range(1,21)]
    promotions = []
    for sub in random.sample(subscribers, int(n_subs*0.35)):
        applied_dt = rand_dt(START_DATE, END_DATE)
        promotions.append({
            "promo_id":      f"PRO{uid()[:8]}",
            "subscriber_id": sub["subscriber_id"],
            "promo_code":    random.choice(PROMO_CODES),
            "discount_pct":  random.choice([5,10,15,20,25,50]),
            "applied_date":  fmt(applied_dt),
            "valid_until":   fmt(applied_dt + datetime.timedelta(days=random.randint(7,30))),
            "times_applied": random.randint(1,5),
            "max_allowed":   1,
            "is_valid":      random.choices([1,0],[85,15])[0],
        })
    promos_df = pd.DataFrame(promotions)

    # -- 7. SIM swap events -----------------------------------
    print("Generating SIM swap events...")
    sim_swaps = []
    for sub in random.sample(subscribers, int(n_subs*0.05)):
        swap_dt = rand_dt(START_DATE, END_DATE)
        sim_swaps.append({
            "swap_id":       f"SWP{uid()[:8]}",
            "subscriber_id": sub["subscriber_id"],
            "old_imsi":      sub["imsi"],
            "new_imsi":     f"404{random.randint(10,99)}{random.randint(1000000000,9999999999)}",
            "old_msisdn":    sub["msisdn"],
            "new_msisdn":    rand_msisdn(),
            "swap_date":     fmt(swap_dt),
            "channel":       random.choice(["store","online","call_center","unauthorized"]),
            "verified":      random.choices([1,0],[80,20])[0],
            "fraud_flag":    random.choices([0,1],[90,10])[0],
        })
    sim_swaps_df = pd.DataFrame(sim_swaps)

    # -- 8. Device subsidies ----------------------------------
    print("Generating device subsidies...")
    subsidies = []
    for sub in [s for s in subscribers if s["subsidy_device_id"]]:
        grant_dt = rand_dt(START_DATE - datetime.timedelta(days=365), END_DATE)
        subsidies.append({
            "subsidy_id":        f"SUB{uid()[:8]}",
            "subscriber_id":     sub["subscriber_id"],
            "device_id":         sub["subsidy_device_id"],
            "device_model":      random.choice(["iPhone15","Samsung S24","Pixel8","OnePlus12","Redmi13"]),
            "subsidy_amount":    round(random.uniform(2000,15000),2),
            "grant_date":        fmt(grant_dt),
            "lock_period_days":  random.choice([180,365,730]),
            "early_exit_fee":    round(random.uniform(1000,8000),2),
            "churn_within_lock": random.choices([0,1],[85,15])[0],
            "recovery_status":   random.choices(["recovered","pending","waived","not_applicable"],[40,30,10,20])[0],
        })
    subsidies_df = pd.DataFrame(subsidies)

    # -- 9. MVNO accounts -------------------------------------
    print("Generating MVNO accounts...")
    MVNO_NAMES = ["QuickMobile","BudgetTalk","NetConnect","EasyCall","VoiceX"]
    mvno_accounts = []
    for sub in [s for s in subscribers if s["customer_type"] == "mvno"]:
        mvno_accounts.append({
            "mvno_id":           f"MVNO{uid()[:8]}",
            "subscriber_id":     sub["subscriber_id"],
            "mvno_name":         random.choice(MVNO_NAMES),
            "wholesale_plan":    random.choice(["WH001","WH002","WH003"]),
            "settlement_cycle":  "monthly",
            "last_settled_month":random.choice(["2024-01","2024-02","2024-03",""]),
            "outstanding_amount":round(random.uniform(0,50000),2),
            "settlement_status": random.choices(["settled","pending","disputed","missing"],[60,20,10,10])[0],
        })
    mvno_df = pd.DataFrame(mvno_accounts)

    # -- 10. VAS subscriptions --------------------------------
    print("Generating VAS subscriptions...")
    vas_subs_list = []
    for sub in random.sample(subscribers, int(n_subs*0.30)):
        sub_dt = rand_dt(START_DATE - datetime.timedelta(days=90), END_DATE)
        vas_subs_list.append({
            "vas_sub_id":       f"VAS{uid()[:8]}",
            "subscriber_id":    sub["subscriber_id"],
            "vas_type":         random.choice(VAS_TYPES),
            "partner_name":     random.choice(PARTNER_NAMES),
            "monthly_charge":   round(random.uniform(5,99),2),
            "subscribed_date":  fmt(sub_dt),
            "unsubscribed_date":"",
            "is_active":        random.choices([1,0],[75,25])[0],
            "consent_recorded": random.choices([1,0],[85,15])[0],
            "billing_applied":  random.choices([1,0],[90,10])[0],
        })
    vas_df = pd.DataFrame(vas_subs_list)

    # -- 11. Topup events -------------------------------------
    print("Generating topup events...")
    topups = []
    for sub in random.sample(active_subs, int(len(active_subs)*0.40)):
        for _ in range(random.randint(1, 8)):
            top_dt = rand_dt()
            topups.append({
                "topup_id":             f"TOP{uid()[:8]}",
                "subscriber_id":        sub["subscriber_id"],
                "topup_amount":         random.choice([10,20,50,100,200,500]),
                "bonus_amount":         round(random.uniform(0,50),2),
                "topup_date":           fmt(top_dt),
                "channel":              random.choice(["app","ussd","retailer","bank","auto"]),
                "bonus_redeemed":       random.choices([1,0],[80,20])[0],
                "bonus_count_this_month":random.randint(1,5),
            })
    topups_df = pd.DataFrame(topups)

    # -- 12. Agent actions ------------------------------------
    print("Generating agent actions...")
    ACTION_TYPES = ["credit_applied","discount_given","bill_waived","plan_changed",
                    "refund_issued","writeoff_approved","fee_reversed","free_addon"]
    agent_actions = []
    for _ in range(int(n_subs * 0.8)):
        sub = random.choice(subscribers)
        act_dt = rand_dt()
        agent_actions.append({
            "action_id":         f"ACT{uid()[:8]}",
            "agent_id":          random.choice(AGENT_IDS),
            "subscriber_id":     sub["subscriber_id"],
            "action_type":       random.choice(ACTION_TYPES),
            "action_date":       fmt(act_dt),
            "amount":            round(random.uniform(0,5000),2),
            "approved_by":       random.choice(AGENT_IDS + [""]),
            "approval_required": random.choices([1,0],[60,40])[0],
            "approved":          random.choices([1,0],[85,15])[0],
            "notes":             random.choice(["customer_complaint","retention",
                                               "error_correction","loyalty",
                                               "fraud_reversal","system_error",""]),
            "suspicious_flag":   random.choices([0,1],[92,8])[0],
        })
    agent_df = pd.DataFrame(agent_actions)

    # -- 13. Credit notes -------------------------------------
    print("Generating credit notes...")
    credit_notes = []
    for _ in range(int(n_subs * 0.15)):
        sub = random.choice(subscribers)
        cn_dt = rand_dt()
        credit_notes.append({
            "credit_note_id":    f"CN{uid()[:8]}",
            "subscriber_id":     sub["subscriber_id"],
            "agent_id":          random.choice(AGENT_IDS),
            "credit_amount":     round(random.uniform(10,2000),2),
            "reason":            random.choice(["billing_error","service_outage","complaint",
                                               "goodwill","unknown","duplicate_charge"]),
            "issue_date":        fmt(cn_dt),
            "approved":          random.choices([1,0],[80,20])[0],
            "justification_doc": random.choices([1,0],[70,30])[0],
            "bill_month":        mk(fmt(cn_dt)),
        })
    cn_df = pd.DataFrame(credit_notes)

    # -- 14. Writeoff events ----------------------------------
    print("Generating writeoff events...")
    writeoffs = []
    for _ in range(int(n_subs * 0.05)):
        sub = random.choice(subscribers)
        wo_dt = rand_dt()
        writeoffs.append({
            "writeoff_id":         f"WO{uid()[:8]}",
            "subscriber_id":       sub["subscriber_id"],
            "agent_id":            random.choice(AGENT_IDS),
            "writeoff_amount":     round(random.uniform(100,20000),2),
            "writeoff_date":       fmt(wo_dt),
            "reason":              random.choice(["bad_debt","deceased","fraud",
                                                 "dispute_settled","unknown"]),
            "days_overdue":        random.randint(30,730),
            "collection_attempts": random.randint(0,10),
            "approved_by_finance": random.choices([1,0],[75,25])[0],
            "recovery_possible":   random.choices([0,1],[70,30])[0],
        })
    wo_df = pd.DataFrame(writeoffs)

    # -- 15. Payments -----------------------------------------
    print("Generating payments...")
    payments = []
    for sub in random.sample(subscribers, int(n_subs*0.85)):
        for _ in range(random.randint(1,4)):
            pay_dt = rand_dt()
            payments.append({
                "payment_id":       f"PAY{uid()[:8]}",
                "subscriber_id":    sub["subscriber_id"],
                "payment_amount":   round(random.uniform(50,3000),2),
                "payment_date":     fmt(pay_dt),
                "payment_method":   random.choice(["upi","card","netbanking",
                                                   "cash","auto_debit","cheque"]),
                "reference_no":     f"REF{random.randint(100000000,999999999)}",
                "posting_status":   random.choices(["posted","pending","failed","unallocated"],
                                                   [85,7,3,5])[0],
                "bill_month_applied":mk(fmt(pay_dt)),
                "posting_delay_days":random.randint(0,15),
            })
    payments_df = pd.DataFrame(payments)

    # -- 16. API usage ----------------------------------------
    print("Generating API usage records...")
    API_NAMES = ["LocationAPI","MessagingAPI","NumberVerifyAPI","NetworkSliceAPI","QoSAPI"]
    api_usage = []
    for _ in range(int(n_subs * 2)):
        sub = random.choice(subscribers)
        api_dt = rand_dt()
        api_usage.append({
            "api_usage_id":   f"API{uid()[:8]}",
            "subscriber_id":  sub["subscriber_id"],
            "api_name":       random.choice(API_NAMES),
            "partner_id":     random.choice(PARTNER_NAMES),
            "call_count":     random.randint(1,1000),
            "usage_date":     fmt(api_dt),
            "expected_charge":round(random.uniform(0,500),2),
            "billed_amount":  0.0,
            "billing_status": random.choices(["billed","unbilled","waived"],[65,30,5])[0],
        })
    api_df = pd.DataFrame(api_usage)

    # -- 17. Partner revenue share ----------------------------
    print("Generating partner revenue share records...")
    partner_rev = []
    for partner in PARTNER_NAMES:
        for month in ["2024-01","2024-02","2024-03"]:
            billed = round(random.uniform(10000,200000),2)
            payout = round(billed * random.uniform(0.25,0.65),2)
            partner_rev.append({
                "rev_share_id":          f"REV{uid()[:8]}",
                "partner_name":          partner,
                "bill_month":            month,
                "total_billed_to_subs":  billed,
                "partner_payout":        payout,
                "payout_rate_pct":       round(payout/billed*100,2),
                "settlement_status":     random.choices(["settled","pending","disputed"],[75,15,10])[0],
                "payout_exceeds_billed": int(payout > billed),
                "audit_flag":            random.choices([0,1],[88,12])[0],
            })
    pr_df = pd.DataFrame(partner_rev)

    # -- 18. CDRs ---------------------------------------------
    print("Generating CDRs...")
    simbox_msisdns  = [rand_msisdn() for _ in range(5)]
    irsf_numbers    = [f"+{random.randint(200,299)}{random.randint(1000000,9999999)}"
                       for _ in range(20)]
    wangiri_msisdns = [rand_msisdn() for _ in range(8)]

    n_cdrs = len(active_subs) * n_d * 3
    cdrs, leakage_audit, dup_cdrs = [], [], []

    for i in range(n_cdrs):
        sub   = random.choice(active_subs)
        plan  = plan_map[sub["plan_id"]]
        tower = random.choice(towers)
        ts    = rand_dt()
        ct    = random.choices(CALL_TYPES, weights=[40,15,40,5])[0]
        dur   = 0
        data_mb = 0.0
        if ct in ("voice","video"):
            dur = min(int(np.random.exponential(180)), 7200)
        elif ct == "data":
            data_mb = min(round(np.random.exponential(50),2), 5000)

        is_roam = random.random() < 0.08
        roam_country = roam_iso = ""
        if is_roam:
            rc, ri = random.choice(ROAMING_PARTNERS)
            roam_country, roam_iso = rc, ri

        charge           = rate_cdr(ct, dur, data_mb, is_roam, plan)
        charge_truncated = math.floor(charge * 100) / 100
        rounding_loss    = round(charge - charge_truncated, 4)

        cdrs.append({
            "cdr_id":             f"CDR{i+1:08d}",
            "subscriber_id":      sub["subscriber_id"],
            "msisdn_a":           sub["msisdn"],
            "msisdn_b":           rand_msisdn(),
            "imsi":               sub["imsi"],
            "plan_id":            sub["plan_id"],
            "tower_id":           tower["tower_id"],
            "region":             tower["region"],
            "call_type":          ct,
            "start_time":         fmt(ts),
            "end_time":           fmt(ts + datetime.timedelta(seconds=dur)),
            "duration_sec":       dur,
            "data_mb":            data_mb,
            "is_roaming":         int(is_roam),
            "roaming_country":    roam_country,
            "roaming_iso":        roam_iso,
            "termination_cause":  random.choices(TERMINATIONS,[70,10,8,8,4])[0],
            "charge_expected":    charge,
            "charge_truncated":   charge_truncated,
            "rounding_loss":      rounding_loss,
            # Ground truth columns -- set to "none" / 0 for clean records
            "ground_truth_leakage_type": "none",   # <- THE KEY COLUMN FOR ML
            "leakage_type":       "none",           # same value, legacy name kept
            "leakage_flag":       0,
            "sql_detected_leakage_type":  "",       # filled by rule_engine.py
            "model_predicted_leakage_type": "",     # filled by ML model
            "model_confidence":   0.0,              # filled by ML model
            "mediation_status":   "success",
            "leakage_metadata":   "",
            "cli_original":       sub["msisdn"],
            "cli_presented":      sub["msisdn"],
            "route_type":         "domestic",
            "signaling_protocol": random.choice(SIGNALING),
            "destination_type":   "normal",
            "number_range_type":  "geographic",
            "access_type":        "direct",
            "pbx_flag":           0,
            "device_type":        random.choice(DEVICE_TYPES),
            "imei":              f"{random.randint(100000000000000,999999999999999)}",
            "tethering_flag":     0,
            "app_category":       random.choice(APP_CATEGORIES),
        })

    print(f"  Base CDRs: {len(cdrs):,}")

    # -- Leakage injection ------------------------------------
    print("Injecting leakage...")
    n_leaky = int(len(cdrs) * l_rate)
    leaky_idx = random.sample(range(len(cdrs)), n_leaky)

    type_assignments = []
    for lt, frac in LEAKAGE_DIST.items():
        type_assignments.extend([lt] * int(n_leaky * frac))
    while len(type_assignments) < n_leaky:
        type_assignments.append("L1_unbilled")
    random.shuffle(type_assignments)

    for pos, idx in enumerate(leaky_idx):
        c  = cdrs[idx]
        lt = type_assignments[pos]
        loss = 0.0

        # Set both the legacy and new ground truth columns
        c["leakage_type"] = lt
        c["leakage_flag"] = 1

        # -- A: Network/CDR ------------------------------------
        if lt == "L1_unbilled":
            c["mediation_status"] = "success"
            loss = c["charge_expected"]

        elif lt == "L4_duplicate":
            c["leakage_type"] = "L4_duplicate_original"
            dup = copy.deepcopy(c)
            dup["cdr_id"]       = f"CDRDUP_{c['cdr_id']}"
            dup["leakage_type"] = "L4_duplicate_copy"
            orig_ts = datetime.datetime.strptime(c["start_time"],"%Y-%m-%d %H:%M:%S")
            dup["start_time"]   = fmt(orig_ts + datetime.timedelta(seconds=random.randint(1,30)))
            dup_cdrs.append(dup)
            loss = c["charge_expected"]

        elif lt == "L7_suppression":
            c["mediation_status"] = "failed"
            c["leakage_metadata"] = json.dumps({"error":"suppressed","tower":c["tower_id"]})
            loss = c["charge_expected"]

        elif lt == "L8_late_cdr":
            old_ts = datetime.datetime.strptime(c["start_time"],"%Y-%m-%d %H:%M:%S")
            c["start_time"] = fmt(old_ts - datetime.timedelta(days=random.randint(32,60)))
            c["end_time"]   = fmt(datetime.datetime.strptime(c["start_time"],"%Y-%m-%d %H:%M:%S")
                                  + datetime.timedelta(seconds=c["duration_sec"]))
            loss = c["charge_expected"]

        elif lt == "L9_partial_cdr":
            c["duration_sec"]     = 0
            c["data_mb"]          = 0.0
            c["imsi"]             = ""
            c["termination_cause"]= "parse_error"
            c["charge_expected"]  = 0.0
            c["leakage_metadata"] = json.dumps({"missing_fields":["duration_sec","data_mb","imsi"]})
            loss = rate_cdr(c["call_type"], random.randint(30,600), 0,
                            bool(c["is_roaming"]), plan_map[c["plan_id"]])

        elif lt == "L10_timestamp_fraud":
            orig_ts  = datetime.datetime.strptime(c["start_time"],"%Y-%m-%d %H:%M:%S")
            off_peak = orig_ts.replace(hour=random.randint(2,5))
            c["start_time"]      = fmt(off_peak)
            c["end_time"]        = fmt(off_peak + datetime.timedelta(seconds=c["duration_sec"]))
            c["leakage_metadata"]= json.dumps({"original_hour":orig_ts.hour,
                                                "shifted_to_hour":off_peak.hour})
            loss = c["charge_expected"] * 0.3

        # -- B: Rating/Tariff ----------------------------------
        elif lt == "L2_wrong_tariff":
            wrong = random.choice([p for p in PLAN_CATALOGUE if p["plan_id"] != c["plan_id"]])
            wrong_charge = rate_cdr(c["call_type"],c["duration_sec"],c["data_mb"],
                                    bool(c["is_roaming"]), wrong)
            correct = c["charge_expected"]
            c["charge_expected"]  = wrong_charge
            c["leakage_metadata"] = json.dumps({"correct_plan":c["plan_id"],
                                                 "applied_plan":wrong["plan_id"],
                                                 "correct_charge":correct,
                                                 "loss":round(correct-wrong_charge,4)})
            loss = max(0, correct - wrong_charge)

        elif lt == "L11_free_period":
            loss = rate_cdr(c["call_type"],c["duration_sec"],c["data_mb"],
                            bool(c["is_roaming"]),plan_map[c["plan_id"]])
            c["charge_expected"]  = 0.0
            c["leakage_metadata"] = json.dumps({"abuse":"free_trial_repeated_activation"})

        elif lt == "L12_promo_abuse":
            original = c["charge_expected"]
            c["charge_expected"]  = round(original * 0.5, 4)
            c["leakage_metadata"] = json.dumps({"promo_applied_times":random.randint(2,5),
                                                 "max_allowed":1,"original_charge":original})
            loss = round(original * 0.5, 4)

        elif lt == "L13_rounding":
            floored = math.floor(c["charge_expected"] * 10) / 10
            loss    = round(c["charge_expected"] - floored, 4)
            c["charge_expected"] = floored
            c["rounding_loss"]   = loss
            c["leakage_metadata"]= json.dumps({"truncated_to":floored,"loss_per_cdr":loss})

        elif lt == "L14_bundle_mismatch":
            loss = rate_cdr(c["call_type"],c["duration_sec"],c["data_mb"],
                            bool(c["is_roaming"]),plan_map[c["plan_id"]])
            c["charge_expected"]  = 0.0
            c["leakage_metadata"] = json.dumps({"issue":"add_on_not_activated"})

        elif lt == "L15_expired_plan":
            expired      = plan_map["PL007"]
            wrong_charge = rate_cdr(c["call_type"],c["duration_sec"],c["data_mb"],
                                    bool(c["is_roaming"]), expired)
            correct      = c["charge_expected"]
            c["plan_id"]         = "PL007"
            c["charge_expected"] = wrong_charge
            c["leakage_metadata"]= json.dumps({"correct_plan":c["plan_id"],
                                                "expired_plan":"PL007",
                                                "loss":round(correct-wrong_charge,4)})
            loss = max(0, correct - wrong_charge)

        # -- C: Roaming ----------------------------------------
        elif lt == "L3_roaming_gap":
            rc, ri = random.choice(ROAMING_PARTNERS)
            c["is_roaming"] = 1; c["roaming_country"] = rc; c["roaming_iso"] = ri
            c["charge_expected"] = rate_cdr(c["call_type"],c["duration_sec"],
                                             c["data_mb"],True,plan_map[c["plan_id"]])
            loss = c["charge_expected"]

        elif lt == "L16_interconnect_bypass":
            c["cli_original"]    = rand_msisdn(prefix="44")
            c["cli_presented"]   = rand_msisdn()
            c["route_type"]      = "bypass"
            c["is_roaming"]      = 0
            c["leakage_metadata"]= json.dumps({"cli_spoofed":True,"presented_as":"domestic"})
            loss = c["charge_expected"] * 2

        elif lt == "L17_tap_errors":
            c["is_roaming"] = 1
            rc, ri = random.choice(ROAMING_PARTNERS)
            c["roaming_country"] = rc; c["roaming_iso"] = ri
            c["leakage_metadata"]= json.dumps({"tap_issue":random.choice(["missing_record",
                                                "seq_gap","format_error","duplicate_tap"])})
            loss = c["charge_expected"]

        elif lt == "L18_rate_arbitrage":
            c["is_roaming"] = 1
            rc, ri = random.choice(ROAMING_PARTNERS)
            c["roaming_country"] = rc; c["roaming_iso"] = ri
            wholesale = round(random.uniform(2,5),4)
            retail    = c["charge_expected"]
            c["leakage_metadata"]= json.dumps({"wholesale_rate":wholesale,"retail_rate":retail,
                                                "arbitrage_loss":max(0,round(wholesale-retail,4))})
            loss = max(0, wholesale - retail)

        elif lt == "L19_mvno_leakage":
            c["leakage_metadata"]= json.dumps({"mvno_type":"unsettled_usage"})
            loss = c["charge_expected"]

        elif lt == "L20_grey_voip":
            c["route_type"]="grey"; c["signaling_protocol"]="SIP"
            c["destination_type"]="international"; c["charge_expected"]=0.0
            c["leakage_metadata"]=json.dumps({"path":"unregistered_voip_gateway"})
            loss = rate_cdr(c["call_type"],c["duration_sec"],c["data_mb"],
                            True, plan_map[c["plan_id"]])

        # -- D: Subscription -----------------------------------
        elif lt == "L21_ghost_sub":
            inactive = [s for s in subscribers if not s["is_active"]]
            if inactive:
                ghost = random.choice(inactive)
                c["subscriber_id"] = ghost["subscriber_id"]
                c["msisdn_a"]      = ghost["msisdn"]
                c["imsi"]          = ghost["imsi"]
            c["leakage_metadata"] = json.dumps({"issue":"churned_sub_still_active"})
            loss = c["charge_expected"]

        elif lt == "L22_plan_downgrade":
            higher = [p for p in PLAN_CATALOGUE
                      if p["monthly_rent"] > plan_map[c["plan_id"]]["monthly_rent"]]
            if not higher:
                higher = [p for p in PLAN_CATALOGUE if p["plan_id"] != c["plan_id"]]
            old_plan  = random.choice(higher)
            correct   = c["charge_expected"]
            wrong_ch  = rate_cdr(c["call_type"],c["duration_sec"],c["data_mb"],
                                 bool(c["is_roaming"]), old_plan)
            c["charge_expected"]  = wrong_ch
            c["leakage_metadata"] = json.dumps({"old_plan_applied":old_plan["plan_id"],
                                                 "overcharge":round(wrong_ch-correct,4)})
            loss = max(0, correct - wrong_ch)

        elif lt == "L23_sim_swap":
            c["imsi"]    = f"404{random.randint(10,99)}{random.randint(1000000000,9999999999)}"
            c["msisdn_a"]= rand_msisdn()
            c["leakage_metadata"] = json.dumps({"issue":"post_swap_billing_mismatch"})
            loss = c["charge_expected"]

        elif lt == "L24_multi_sim":
            c["msisdn_a"] = rand_msisdn()
            c["leakage_metadata"] = json.dumps({"issue":"multiple_sims_sharing_allowance"})
            loss = c["charge_expected"] * 0.5

        elif lt == "L25_corporate_misuse":
            c["leakage_metadata"] = json.dumps({"issue":"personal_usage_on_corporate_plan"})
            loss = c["charge_expected"] * 0.7

        elif lt == "L26_subsidy_abuse":
            c["leakage_metadata"] = json.dumps({"issue":"churned_within_lock_period"})
            loss = round(random.uniform(1000,8000),2)

        # -- E: Fraud ------------------------------------------
        elif lt == "L6_simbox":
            c["msisdn_a"]       = random.choice(simbox_msisdns)
            c["call_type"]      = "voice"
            c["duration_sec"]   = random.randint(5,45)
            c["charge_expected"]= 0.0
            c["route_type"]     = "bypass"
            c["leakage_metadata"]= json.dumps({"hub_msisdn":c["msisdn_a"],"pattern":"bulk_short_calls"})
            loss = rate_cdr("voice",c["duration_sec"],0,False,plan_map[c["plan_id"]])

        elif lt == "L27_irsf":
            c["msisdn_b"]          = random.choice(irsf_numbers)
            c["destination_type"]  = "premium"
            c["number_range_type"] = "premium"
            c["call_type"]         = "voice"
            c["duration_sec"]      = random.randint(300,3600)
            c["charge_expected"]   = round(c["duration_sec"]/60 * random.uniform(5,20),4)
            c["leakage_metadata"]  = json.dumps({"pattern":"premium_number_pumping"})
            loss = c["charge_expected"]

        elif lt == "L28_wangiri":
            c["msisdn_a"]          = random.choice(wangiri_msisdns)
            c["duration_sec"]      = random.randint(1,4)
            c["termination_cause"] = "no_answer"
            c["call_type"]         = "voice"
            c["charge_expected"]   = 0.0
            c["leakage_metadata"]  = json.dumps({"pattern":"one_ring_callback_trap"})
            loss = rate_cdr("voice",random.randint(180,600),0,True,plan_map[c["plan_id"]])

        elif lt == "L29_pbx_hack":
            c["access_type"] = "pbx"; c["pbx_flag"] = 1
            c["call_type"]   = "voice"; c["is_roaming"] = 1
            rc, ri = random.choice(ROAMING_PARTNERS)
            c["roaming_country"] = rc; c["roaming_iso"] = ri
            c["duration_sec"]    = random.randint(600,7200)
            c["charge_expected"] = rate_cdr("voice",c["duration_sec"],0,True,plan_map[c["plan_id"]])
            c["leakage_metadata"]= json.dumps({"pattern":"compromised_pbx_international_calls"})
            loss = c["charge_expected"]

        elif lt == "L30_credit_abuse":
            loss = rate_cdr(c["call_type"],c["duration_sec"],c["data_mb"],
                            bool(c["is_roaming"]),plan_map[c["plan_id"]])
            c["charge_expected"]  = 0.0
            c["leakage_metadata"] = json.dumps({"pattern":"topup_bonus_velocity_abuse"})

        elif lt == "L31_internal_fraud":
            loss = rate_cdr(c["call_type"],c["duration_sec"],c["data_mb"],
                            bool(c["is_roaming"]),plan_map[c["plan_id"]])
            c["charge_expected"]  = 0.0
            c["leakage_metadata"] = json.dumps({"pattern":"agent_credit_without_approval",
                                                 "agent_id":random.choice(AGENT_IDS)})

        # -- F: Data/VAS ---------------------------------------
        elif lt == "L5_zero_rated":
            c["call_type"]      = "data"
            c["data_mb"]        = round(random.uniform(20,500),2)
            c["charge_expected"]= 0.0
            loss = rate_cdr("data",0,c["data_mb"],bool(c["is_roaming"]),plan_map[c["plan_id"]])

        elif lt == "L32_vas_billing":
            c["charge_expected"]  = round(random.uniform(5,99),2)
            c["call_type"]        = "sms"
            c["leakage_metadata"] = json.dumps({"issue":"vas_billed_without_consent",
                                                 "vas_type":random.choice(VAS_TYPES)})
            loss = c["charge_expected"]

        elif lt == "L33_tethering":
            c["call_type"]        = "data"
            c["tethering_flag"]   = 1
            c["data_mb"]          = round(random.uniform(200,5000),2)
            c["device_type"]      = "router"
            c["charge_expected"]  = 0.0
            c["leakage_metadata"] = json.dumps({"issue":"tethering_not_billed","data_mb":c["data_mb"]})
            loss = rate_cdr("data",0,c["data_mb"],bool(c["is_roaming"]),plan_map[c["plan_id"]])

        elif lt == "L34_api_billing":
            c["charge_expected"]  = 0.0
            c["leakage_metadata"] = json.dumps({"issue":"api_usage_not_billed_to_partner"})
            loss = round(random.uniform(10,500),2)

        elif lt == "L35_iot_billing":
            c["device_type"]      = "iot"
            c["call_type"]        = "data"
            c["data_mb"]          = round(random.uniform(0.01,10),3)
            c["charge_expected"]  = 0.0
            c["leakage_metadata"] = json.dumps({"issue":"iot_micro_session_not_rated"})
            loss = c["data_mb"] * plan_map[c["plan_id"]]["data_rate_per_mb"]

        elif lt == "L36_ott_bypass":
            c["app_category"]     = "voip"
            c["call_type"]        = "data"
            c["data_mb"]          = round(random.uniform(5,50),2)
            c["leakage_metadata"] = json.dumps({"issue":"voice_over_ott_not_charged_at_voice_rate"})
            loss = max(0, rate_cdr("voice",c["duration_sec"],0,False,plan_map[c["plan_id"]])
                          - rate_cdr("data",0,c["data_mb"],False,plan_map[c["plan_id"]]))

        # -- G: Billing/Collection -----------------------------
        elif lt == "L37_invoice_suppress":
            c["leakage_metadata"] = json.dumps({"issue":"invoice_generated_not_dispatched"})
            loss = c["charge_expected"]

        elif lt == "L38_writeoff_abuse":
            c["leakage_metadata"] = json.dumps({"issue":"recoverable_debt_written_off_without_approval"})
            loss = round(random.uniform(100,20000),2)

        elif lt == "L39_credit_fraud":
            loss = rate_cdr(c["call_type"],c["duration_sec"],c["data_mb"],
                            bool(c["is_roaming"]),plan_map[c["plan_id"]])
            c["charge_expected"]  = 0.0
            c["leakage_metadata"] = json.dumps({"issue":"unjustified_credit_note_issued",
                                                 "agent_id":random.choice(AGENT_IDS)})

        elif lt == "L40_payment_mispost":
            c["leakage_metadata"] = json.dumps({"issue":"payment_received_not_applied"})
            loss = c["charge_expected"]

        elif lt == "L41_tax_leakage":
            correct_tax = round(c["charge_expected"] * 0.18, 4)
            applied_tax = round(c["charge_expected"] * random.uniform(0.0,0.12), 4)
            c["leakage_metadata"] = json.dumps({"correct_tax_rate":0.18,
                                                 "applied_tax_rate":round(applied_tax/max(c["charge_expected"],0.01),4),
                                                 "tax_loss":round(correct_tax-applied_tax,4)})
            loss = round(correct_tax - applied_tax, 4)

        elif lt == "L42_partner_settle":
            c["leakage_metadata"] = json.dumps({"issue":"partner_payout_exceeds_billed_revenue",
                                                 "partner":random.choice(PARTNER_NAMES)})
            loss = round(random.uniform(100,5000),2)

        # -- Set ground truth AFTER all modifications ----------
        # ground_truth_leakage_type is the AUTHORITATIVE label for ML
        c["ground_truth_leakage_type"] = c["leakage_type"]

        leakage_audit.append({
            "audit_id":                    uid(),
            "cdr_id":                      c["cdr_id"],
            "leakage_type":                c["leakage_type"],
            "ground_truth_leakage_type":   c["leakage_type"],   # canonical ML label
            "leakage_category":            c["leakage_type"].split("_")[0],
            "subscriber_id":               c["subscriber_id"],
            "plan_id":                     c["plan_id"],
            "call_type":                   c["call_type"],
            "start_time":                  c["start_time"],
            "region":                      c["region"],
            "tower_id":                    c["tower_id"],
            "estimated_loss":              round(loss, 2),
            "estimated_loss_inr":          round(loss, 2),     # ML evaluator uses this col
            "detection_method":            "injected",
            "auto_detected":               0,
            "sql_detected":                0,                   # filled by rule_engine.py
            "ml_predicted":                0,                   # filled by ML model
            "resolved":                    0,
            "resolution_note":             "",
            "severity":                    "high" if loss>100 else "medium" if loss>10 else "low",
        })

    # Append duplicate CDRs and shuffle
    cdrs.extend(dup_cdrs)
    random.shuffle(cdrs)

    # Ensure all CDRs have every column
    for c in cdrs:
        for col in ["leakage_metadata","cli_original","cli_presented","route_type",
                    "signaling_protocol","destination_type","number_range_type",
                    "access_type","device_type","imei","app_category"]:
            if col not in c: c[col] = ""
        for col in ["pbx_flag","tethering_flag"]:
            if col not in c: c[col] = 0
        for col in ["ground_truth_leakage_type","sql_detected_leakage_type",
                    "model_predicted_leakage_type"]:
            if col not in c: c[col] = "none" if col == "ground_truth_leakage_type" else ""
        if "model_confidence" not in c: c["model_confidence"] = 0.0

    print(f"  CDRs after injection: {len(cdrs):,}")
    print(f"  Leakage records:      {sum(1 for c in cdrs if c['leakage_flag']==1):,}")

    cdrs_df  = pd.DataFrame(cdrs)
    audit_df = pd.DataFrame(leakage_audit)

    # -- 19. Mediation events ---------------------------------
    print("Generating mediation events...")
    mediation = []
    for c in cdrs:
        status = "failed" if c["leakage_type"] == "L7_suppression" else "success"
        if c["leakage_type"] == "L9_partial_cdr": status = "partial"
        err = "" if status == "success" else random.choice(
            ["suppressed","parse_error","timeout","partial_record"])
        mediation.append({
            "mediation_id":    f"MED_{c['cdr_id']}",
            "cdr_id":           c["cdr_id"],
            "subscriber_id":    c["subscriber_id"],
            "received_at":      c["start_time"],
            "processed_at":     fmt(datetime.datetime.strptime(c["start_time"],"%Y-%m-%d %H:%M:%S")
                                    + datetime.timedelta(seconds=random.randint(1,30))),
            "status":           status,
            "error_code":       err,
            "output_to_rating": int(status == "success"),
            "processing_node":  f"NODE{random.randint(1,10):02d}",
        })
    med_df = pd.DataFrame(mediation)

    # -- 20. Rating events ------------------------------------
    print("Generating rating events...")
    SKIP_RATING = {"L1_unbilled","L7_suppression","L9_partial_cdr"}
    rating_events = []
    for c in cdrs:
        if c["leakage_type"] in SKIP_RATING:
            continue
        plan = plan_map.get(c["plan_id"], PLAN_CATALOGUE[0])
        rating_events.append({
            "rating_id":       f"RAT_{c['cdr_id']}",
            "cdr_id":           c["cdr_id"],
            "subscriber_id":    c["subscriber_id"],
            "plan_id":          c["plan_id"],
            "rated_at":         c["start_time"],
            "call_type":        c["call_type"],
            "billable_units":   c["duration_sec"] if c["call_type"] in ("voice","video")
                                else c["data_mb"],
            "unit_type":        "seconds" if c["call_type"] in ("voice","video") else "mb",
            "rate_applied":     plan["voice_rate_per_min"] if c["call_type"] in ("voice","video")
                                else plan["data_rate_per_mb"],
            "charge_amount":    c["charge_expected"],
            "discount":         0.0,
            "final_charge":     c["charge_expected"],
            "rounding_loss":    c.get("rounding_loss", 0.0),
            "leakage_type":     c["leakage_type"],
            "rating_engine":    f"ENG{random.randint(1,4):02d}",
        })
    rating_df = pd.DataFrame(rating_events)

    # -- 21. Billing records ----------------------------------
    print("Generating billing records...")
    SKIP_BILLING = {"L1_unbilled","L5_zero_rated","L6_simbox","L7_suppression","L9_partial_cdr"}
    billing_map = {}
    for c in cdrs:
        if c["leakage_type"] in SKIP_BILLING:
            continue
        key = (c["subscriber_id"], mk(c["start_time"]))
        if key not in billing_map:
            billing_map[key] = {"calls":0,"sms":0,"data_mb":0.0,"charge":0.0}
        billing_map[key]["calls"]   += 1 if c["call_type"] in ("voice","video") else 0
        billing_map[key]["sms"]     += 1 if c["call_type"] == "sms" else 0
        billing_map[key]["data_mb"] += c["data_mb"]
        billing_map[key]["charge"]  += c["charge_expected"]

    billing = []
    for (sid, month), agg in billing_map.items():
        sub   = sub_map[sid]
        plan  = plan_map[sub["plan_id"]]
        total = round(plan["monthly_rent"] + agg["charge"], 2)
        tax   = round(total * 0.18, 2)
        dispatch = random.choices(["sent","not_sent","bounced"],[92,5,3])[0]
        billing.append({
            "bill_id":         f"BILL_{sid}_{month.replace('-','')}",
            "subscriber_id":    sid,
            "plan_id":          sub["plan_id"],
            "bill_month":       month,
            "monthly_rent":     plan["monthly_rent"],
            "voice_charge":     round(agg["charge"]*0.5,2),
            "data_charge":      round(agg["charge"]*0.4,2),
            "sms_charge":       round(agg["charge"]*0.1,2),
            "roaming_charge":   0.0,
            "total_calls":      agg["calls"],
            "total_sms":        agg["sms"],
            "total_data_mb":    round(agg["data_mb"],2),
            "total_charge":     total,
            "tax_amount":       tax,
            "grand_total":      round(total + tax, 2),
            "bill_status":      random.choices(["paid","pending","overdue"],[80,15,5])[0],
            "payment_date":     fmt(datetime.datetime.strptime(month+"-28","%Y-%m-%d")
                                    + datetime.timedelta(days=random.randint(0,15))),
            "dispatch_status":  dispatch,
            "dispatch_date":    fmt(datetime.datetime.strptime(month+"-28","%Y-%m-%d"))
                                if dispatch == "sent" else "",
            "agent_id":         random.choice(AGENT_IDS + [""]),
        })
    billing_df = pd.DataFrame(billing)

    # -- 22. Roaming settlements ------------------------------
    print("Generating roaming settlements...")
    SKIP_SETTLE = {"L3_roaming_gap","L20_grey_voip"}
    settlements = []
    for c in cdrs:
        if not c["is_roaming"] or c["leakage_type"] in SKIP_SETTLE:
            continue
        settlements.append({
            "settlement_id":   f"SET_{c['cdr_id']}",
            "cdr_id":           c["cdr_id"],
            "subscriber_id":    c["subscriber_id"],
            "roaming_country":  c["roaming_country"],
            "roaming_iso":      c["roaming_iso"],
            "partner_operator": random.choice(OPERATORS),
            "call_type":        c["call_type"],
            "duration_sec":     c["duration_sec"],
            "data_mb":          c["data_mb"],
            "wholesale_rate":   round(random.uniform(0.5,3.0),4),
            "settlement_amount":round(c["charge_expected"]*0.6,2),
            "settlement_date":  mk(c["start_time"])+"-28",
            "status":           random.choices(["settled","pending","disputed"],[85,10,5])[0],
            "tap_file_id":      f"TAP{random.randint(100000,999999)}",
            "tap_seq_number":   random.randint(1,9999),
            "tap_status":       random.choices(["accepted","rejected","pending"],[88,7,5])[0],
            "expected_records": random.randint(1,100),
            "received_records": random.randint(1,100),
        })
    settle_df = pd.DataFrame(settlements)

    # -- Write to SQLite --------------------------------------
    print("Writing to SQLite database...")
    if os.path.exists(db):
        os.remove(db)
    conn = sqlite3.connect(db)

    table_order = [
        (plans_df,        "plans"),
        (towers_df,       "cell_towers"),
        (subscribers_df,  "subscribers"),
        (plan_changes_df, "plan_change_history"),
        (addons_df,       "subscriber_addons"),
        (promos_df,       "promotions"),
        (sim_swaps_df,    "sim_swap_events"),
        (subsidies_df,    "device_subsidies"),
        (mvno_df,         "mvno_accounts"),
        (vas_df,          "vas_subscriptions"),
        (topups_df,       "topup_events"),
        (agent_df,        "agent_actions"),
        (cn_df,           "credit_notes"),
        (wo_df,           "writeoff_events"),
        (payments_df,     "payments"),
        (api_df,          "api_usage"),
        (pr_df,           "partner_revenue_share"),
        (cdrs_df,         "cdr"),
        (med_df,          "mediation_events"),
        (rating_df,       "rating_events"),
        (billing_df,      "billing_records"),
        (settle_df,       "roaming_settlements"),
        (audit_df,        "leakage_audit"),
    ]
    for df, name in table_order:
        df.to_sql(name, conn, if_exists="replace", index=False)
        print(f"  {name:<30} {len(df):>10,} rows")

    # -- Indexes ----------------------------------------------
    print("Creating indexes...")
    for stmt in """
        CREATE INDEX IF NOT EXISTS idx_cdr_sub      ON cdr(subscriber_id);
        CREATE INDEX IF NOT EXISTS idx_cdr_time     ON cdr(start_time);
        CREATE INDEX IF NOT EXISTS idx_cdr_leak     ON cdr(leakage_flag);
        CREATE INDEX IF NOT EXISTS idx_cdr_type     ON cdr(leakage_type);
        CREATE INDEX IF NOT EXISTS idx_cdr_gt       ON cdr(ground_truth_leakage_type);
        CREATE INDEX IF NOT EXISTS idx_cdr_msisdn   ON cdr(msisdn_a);
        CREATE INDEX IF NOT EXISTS idx_cdr_tower    ON cdr(tower_id);
        CREATE INDEX IF NOT EXISTS idx_cdr_route    ON cdr(route_type);
        CREATE INDEX IF NOT EXISTS idx_cdr_device   ON cdr(device_type);
        CREATE INDEX IF NOT EXISTS idx_bill_sub     ON billing_records(subscriber_id);
        CREATE INDEX IF NOT EXISTS idx_bill_month   ON billing_records(bill_month);
        CREATE INDEX IF NOT EXISTS idx_bill_disp    ON billing_records(dispatch_status);
        CREATE INDEX IF NOT EXISTS idx_med_cdr      ON mediation_events(cdr_id);
        CREATE INDEX IF NOT EXISTS idx_rat_cdr      ON rating_events(cdr_id);
        CREATE INDEX IF NOT EXISTS idx_set_cdr      ON roaming_settlements(cdr_id);
        CREATE INDEX IF NOT EXISTS idx_audit_type   ON leakage_audit(leakage_type);
        CREATE INDEX IF NOT EXISTS idx_audit_gt     ON leakage_audit(ground_truth_leakage_type);
        CREATE INDEX IF NOT EXISTS idx_audit_sev    ON leakage_audit(severity);
        CREATE INDEX IF NOT EXISTS idx_sub_active   ON subscribers(is_active);
        CREATE INDEX IF NOT EXISTS idx_pay_status   ON payments(posting_status);
        CREATE INDEX IF NOT EXISTS idx_agent_susp   ON agent_actions(suspicious_flag);
    """.strip().split(";"):
        if stmt.strip():
            conn.execute(stmt.strip())

    conn.commit()

    # -- Export CSVs ------------------------------------------
    print("Exporting CSVs...")
    for df, name in [(cdrs_df,"cdr"),(billing_df,"billing_records"),
                     (subscribers_df,"subscribers"),(audit_df,"leakage_audit"),
                     (settle_df,"roaming_settlements"),(rating_df,"rating_events"),
                     (agent_df,"agent_actions"),(payments_df,"payments")]:
        df.to_csv(f"{out_dir}/{name}.csv", index=False)

    # -- Schema DDL -------------------------------------------
    cur = conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type DESC,name")
    with open(f"{out_dir}/schema.sql","w") as f:
        for row in cur.fetchall():
            f.write(row[0] + ";\n\n")

    # -- Summary ----------------------------------------------
    print("\n" + "="*65)
    print("  DATASET v2 -- GENERATION COMPLETE")
    print("="*65)
    for _, name in table_order:
        cur.execute(f"SELECT COUNT(*) FROM {name}")
        print(f"  {name:<30} {cur.fetchone()[0]:>10,}")

    print("\n  Top 10 leakage types by estimated loss:")
    for row in conn.execute(
            "SELECT leakage_type,COUNT(*),ROUND(SUM(estimated_loss),2) "
            "FROM leakage_audit GROUP BY leakage_type "
            "ORDER BY 3 DESC LIMIT 10"):
        print(f"    {row[0]:<30} {row[1]:>6,}  Rs.{row[2]:>12,.2f}")

    cur.execute("SELECT ROUND(SUM(estimated_loss),2) FROM leakage_audit")
    total_loss   = cur.fetchone()[0]
    cur.execute("SELECT ROUND(SUM(grand_total),2) FROM billing_records")
    total_billed = cur.fetchone()[0]
    print(f"\n  Total billed:   Rs.{total_billed:>15,.2f}")
    print(f"  Total leakage:  Rs.{total_loss:>15,.2f}")
    print(f"  Leakage %:       {round(total_loss/(total_billed or 1)*100,2):>12}%")
    print(f"\n  Output dir: {out_dir}")
    print(f"  Database:   {db}")
    print("="*65)
    conn.close()
    print("Done.")


# -------------------------------------------------------------
# ENTRY POINT -- `make data` calls `python -m src.data.generator`
# -------------------------------------------------------------
def main():
    try:
        from src.utils.config import cfg, ensure_dirs
        ensure_dirs()
        print(f"[generator] Using config: db={cfg.db_path}, "
              f"n_subs={cfg.n_subscribers}, leakage_rate={cfg.leakage_rate}")
        generate(
            output_dir   = str(cfg.db_path.parent),
            db_path      = str(cfg.db_path),
            n_subscribers = cfg.n_subscribers,
            n_towers      = cfg.n_towers,
            n_days        = cfg.n_days,
            leakage_rate  = cfg.leakage_rate,
            random_seed   = cfg.random_seed,
        )
    except ImportError:
        generate()  # Fallback with defaults


if __name__ == "__main__":
    main()
