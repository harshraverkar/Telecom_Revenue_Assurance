WITH L12 AS (
  SELECT
      cdr_id,
      subscriber_id
  FROM `telecom_ra.cdr`
  WHERE
        duration IS NULL
     OR duration < 0
     OR start_time IS NULL
     OR end_time IS NULL
     OR end_time < start_time
),

L13 AS (
  WITH cdr_base AS (
    SELECT
        cdr_id,
        subscriber_id,
        cell_id,
        start_time,
        end_time,
        duration,
        TIMESTAMP_DIFF(end_time, start_time, SECOND) AS actual_duration
    FROM `telecom_ra.cdr`
  ),

  cdr_net AS (
    SELECT
        c.*,
        n.event_time
    FROM cdr_base c
    LEFT JOIN `telecom_ra.network_events` n
      ON c.subscriber_id = n.subscriber_id
     AND c.cell_id = n.cell_id
     AND ABS(TIMESTAMP_DIFF(c.start_time, n.event_time, SECOND)) <= 60
  )

  SELECT
      cdr_id,
      subscriber_id
  FROM cdr_net
  WHERE
        end_time < start_time
     OR actual_duration < 0
)

-- FINAL RESULT = L12 minus L13
SELECT
    c.cdr_id,
    c.subscriber_id,
    'L12_partial' AS detected_leakage_type,
    'sql_rule' AS detection_method,
    1.0 AS detection_confidence,
    CURRENT_TIMESTAMP() AS detected_at

FROM L12 c

LEFT JOIN L13 t
ON c.cdr_id = t.cdr_id

WHERE t.cdr_id IS NULL;