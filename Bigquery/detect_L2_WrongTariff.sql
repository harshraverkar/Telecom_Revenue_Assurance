CREATE OR REPLACE TABLE `revenue-assurance-491605.telecom_ra.L2_output` AS
SELECT
    c.cdr_id,
    c.subscriber_id,
    c.ground_truth_leakage_type,
    c.call_type,
    c.duration,
    c.data_volume_mb,
    c.plan_id,

    r.charge_amount AS actual_charge,

    p.call_rate_per_min,
    p.data_rate_per_mb,
    p.sms_rate,

    CASE
        WHEN c.call_type = 'voice'
            THEN c.duration * p.call_rate_per_min
        WHEN c.call_type = 'data'
            THEN c.data_volume_mb * p.data_rate_per_mb
        WHEN c.call_type = 'sms'
            THEN p.sms_rate
    END AS expected_charge

FROM `revenue-assurance-491605.telecom_ra.cdr` c
JOIN `revenue-assurance-491605.telecom_ra.rating_events` r
    ON c.cdr_id = r.cdr_id
JOIN `revenue-assurance-491605.telecom_ra.plans` p
    ON c.plan_id = p.plan_id

WHERE ABS(
    r.charge_amount -
    CASE
        WHEN c.call_type = 'voice'
            THEN c.duration * p.call_rate_per_min
        WHEN c.call_type = 'data'
            THEN c.data_volume_mb * p.data_rate_per_mb
        WHEN c.call_type = 'sms'
            THEN p.sms_rate
    END
) > 0.01
AND r.charge_amount > 0
AND c.ground_truth_leakage_type = 'L2_wrong_tariff';