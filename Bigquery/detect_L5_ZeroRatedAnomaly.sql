CREATE OR REPLACE TABLE `revenue-assurance-491605.telecom_ra.l5_output` AS

SELECT
    c.cdr_id,
    c.subscriber_id,
    c.start_time,
    c.call_type,
    c.data_volume_mb,
    c.duration,
    r.charge_amount,
    r.applied_rate,
    c.ground_truth_leakage_type,

    -- ✅ Expected charge (service-specific)
    CASE 
        WHEN LOWER(c.call_type) = 'data' 
            THEN SAFE_MULTIPLY(c.data_volume_mb, IFNULL(r.applied_rate, 0))
        
        WHEN LOWER(c.call_type) = 'voice' 
            THEN SAFE_MULTIPLY(c.duration, IFNULL(r.applied_rate, 0))
        
        WHEN LOWER(c.call_type) = 'sms' 
            THEN IFNULL(r.applied_rate, 0)
        
        ELSE 0
    END AS expected_charge,

    'L5_zero_rated' AS detected_leakage_type

FROM `revenue-assurance-491605.telecom_ra.cdr` c
JOIN `revenue-assurance-491605.telecom_ra.rating_events` r
    ON c.cdr_id = r.cdr_id

WHERE 
    -- 🔴 Core condition
    r.charge_amount = 0

    -- ✅ Ensure real usage exists
    AND (
        (LOWER(c.call_type) = 'data' AND c.data_volume_mb > 0.1)
        OR
        (LOWER(c.call_type) = 'voice' AND c.duration > 1)
        OR
        (LOWER(c.call_type) = 'sms')
    )

    -- ✅ Avoid free / zero-rate scenarios
    AND r.applied_rate > 0

    -- 🔥 MAIN FIX → remove "none" false positives
    AND (
        CASE 
            WHEN LOWER(c.call_type) = 'data' 
                THEN SAFE_MULTIPLY(c.data_volume_mb, r.applied_rate)
            
            WHEN LOWER(c.call_type) = 'voice' 
                THEN SAFE_MULTIPLY(c.duration, r.applied_rate)
            
            WHEN LOWER(c.call_type) = 'sms' 
                THEN r.applied_rate
            
            ELSE 0
        END
    ) > 1   -- 🔥 critical threshold
;