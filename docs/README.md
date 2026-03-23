# Telecom Revenue Assurance -- MySQL Edition

Detects telecom billing leakages using SQL rules against a MySQL database.

---

## Setup -- do this once per team member

### Step 1 -- Clone the repo
```bash
git clone https://github.com/YOUR_ORG/telecom-ra.git
cd telecom-ra
```

### Step 2 -- Install dependencies
```bash
pip install -r requirements.txt
```

### Step 3 -- Configure MySQL connection
Open `config/config.yaml` and fill in your MySQL details:
```yaml
mysql:
  host:     "localhost"      # your MySQL server IP
  port:     3306
  user:     "root"           # your username
  password: "your_password"  # <- CHANGE THIS
  database: "telecom_ra"     # will be created automatically
```

### Step 4 -- Generate the SQLite dataset
```bash
python -m src.data.generator
```
This creates `data/raw/telecom_ra.db` (432 MB).
Everyone gets the **exact same data** because `random_seed: 42` is fixed.

### Step 5 -- Migrate to MySQL and verify
```bash
python scripts/setup.py
```
This:
- Tests your MySQL connection
- Creates `telecom_ra` database in MySQL
- Copies all 9 tables and ~760K rows from SQLite to MySQL
- Verifies row counts match

---

## Run L1 leakage detection
```bash
python -m src.detection.rule_engine
```

Expected output:
```
[rule_engine] Enabled: ['L1']
[L1] Running detect_L1_unbilled()... -> 9,922 records flagged
-> Wrote sql_detected_leakage_type='L1_unbilled' for 9,922 rows in MySQL.

RESULTS -- L1_unbilled
Detected by SQL rule  :      9,922
True positives  (TP)  :      9,922
False positives (FP)  :          0
Precision             :     100.0%
Recall                :     100.0%
Estimated loss (Rs.)    :  180,797.96
```

---

## Query the database

### From terminal
```bash
python scripts/query.py --run summary
python scripts/query.py --run l1_results
python scripts/query.py --run l1_accuracy
python scripts/query.py --run detection_status
python scripts/query.py --list                     # all available queries
python scripts/query.py --sql "SELECT COUNT(*) FROM cdr"
python scripts/query.py --run l1_results --export results/l1.csv
```

### From MySQL Workbench / DBeaver
Connect to: `host:port` with your username and password.
Select database: `telecom_ra`

Key queries to run:

```sql
-- Check detection results
SELECT sql_detected_leakage_type, COUNT(*)
FROM cdr
GROUP BY sql_detected_leakage_type;

-- L1 accuracy
SELECT ground_truth_leakage_type, sql_detected_leakage_type,
       COUNT(*), ROUND(SUM(charge_expected), 2) AS loss_inr
FROM cdr
WHERE sql_detected_leakage_type = 'L1_unbilled'
   OR ground_truth_leakage_type = 'L1_unbilled'
GROUP BY 1, 2;

-- Proof: L1 CDRs have no rating row
SELECT c.cdr_id, c.mediation_status, r.rating_id
FROM cdr c
LEFT JOIN rating_events r ON c.cdr_id = r.rating_id
WHERE c.sql_detected_leakage_type = 'L1_unbilled'
LIMIT 10;
```

---

## Add your leakage rule (team guide)

### 1. Write your detect function in `src/detection/sql_rules.py`
```python
def detect_L4_duplicates(db=None) -> pd.DataFrame:
    sql = """
        SELECT a.cdr_id, a.subscriber_id, a.call_type, a.start_time,
               a.charge_expected AS estimated_loss,
               a.ground_truth_leakage_type,
               'L4_duplicate' AS detected_leakage_type,
               1.0 AS detection_confidence, 'sql_rule' AS detection_method
        FROM cdr a
        JOIN cdr b ON a.subscriber_id = b.subscriber_id
                   AND a.call_type = b.call_type
                   AND a.cdr_id < b.cdr_id
        WHERE ABS(TIMESTAMPDIFF(SECOND, a.start_time, b.start_time)) <= 60
    """
    return run_query(sql)
```

### 2. Register it in `ALL_SQL_DETECTORS`
```python
ALL_SQL_DETECTORS = {
    "detect_L1_unbilled":   detect_L1_unbilled,
    "detect_L4_duplicates": detect_L4_duplicates,   # <- add this
}
```

### 3. Enable it in `config/leakage_rules.yaml`
```yaml
L4_duplicate:
  enabled: true    # <- change from false to true
```

### 4. Run and commit
```bash
python -m src.detection.rule_engine

git add src/detection/sql_rules.py config/leakage_rules.yaml
git commit -m "feat: add L4 duplicate CDR detection"
git push
```

---

## What is committed to git

```
src/           <- all Python source code         OK committed
config/        <- config.yaml, leakage_rules.yaml OK committed
scripts/       <- setup.py, query.py              OK committed
docs/          <- this README                     OK committed
requirements.txt                                 OK committed
.gitignore                                       OK committed

data/raw/      <- SQLite DB (432 MB)              X gitignored
*.csv          <- CSV exports                     X gitignored
```
