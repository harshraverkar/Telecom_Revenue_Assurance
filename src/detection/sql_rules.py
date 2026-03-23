"""
src/detection/sql_rules.py
--------------------------
SQL detection functions -- one per leakage type.
Currently: L1 only. Team adds more following the same pattern.

How to add your rule:
    1. Write detect_LXX() function below (copy L1 as template)
    2. Add it to ALL_SQL_DETECTORS dict at the bottom
    3. Set enabled: true in config/leakage_rules.yaml
    4. Run: python -m src.detection.rule_engine
"""

import pandas as pd
from src.utils.db import run_query


def detect_L1_unbilled(db=None) -> pd.DataFrame:
    """
    L1 -- Unbilled CDR
    -----------------
    A CDR passed mediation (mediation_status = 'success') but has
    NO matching row in rating_events. The billing engine never saw it.

    Logic:
        cdr  LEFT JOIN  rating_events  ON  cdr.cdr_id = rating_events.cdr_id
        WHERE  rating_events.rating_id IS NULL     <- no rating row
          AND  cdr.mediation_status = 'success'    <- mediation passed it
    """
    sql = """
        SELECT
            c.cdr_id,
            c.subscriber_id,
            c.call_type,
            c.start_time,
            c.charge_expected              AS estimated_loss,
            c.ground_truth_leakage_type,
            'L1_unbilled'                  AS detected_leakage_type,
            1.0                            AS detection_confidence,
            'sql_rule'                     AS detection_method
        FROM cdr c
        LEFT JOIN rating_events r ON c.cdr_id = r.cdr_id
        WHERE r.rating_id        IS NULL
          AND c.mediation_status = 'success'
        ORDER BY c.start_time DESC
    """
    return run_query(sql)


# -- Registry -------------------------------------------------
# Maps the sql_function name in leakage_rules.yaml to its function.
# rule_engine.py looks up the function name here and calls it.
ALL_SQL_DETECTORS = {
    "detect_L1_unbilled": detect_L1_unbilled,

    # Add yours below when ready:
    # "detect_L2_wrong_tariff":  detect_L2_wrong_tariff,
    # "detect_L3_roaming_gap":   detect_L3_roaming_gap,
    # "detect_L4_duplicates":    detect_L4_duplicates,
}
