WITH cdr_base AS (
  SELECT
      cdr_id,
      subscriber_id,
      cell_id,
      call_type,
      start_time,
      end_time,
      duration,
      ground_truth_leakage_type,
      TIMESTAMP_DIFF(end_time, start_time,SECOND ) AS actual_duration
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
    subscriber_id,
    start_time,
    end_time,
    duration,
    actual_duration,
    event_time,
    call_type,
    ground_truth_leakage_type,

    -- Final label
    'L13_timestamp_fraud' AS detected_leakage_type

FROM cdr_net

WHERE
      end_time < start_time                          -- invalid time
   OR actual_duration < 0
   