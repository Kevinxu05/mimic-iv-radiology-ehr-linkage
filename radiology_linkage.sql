-- Equivalent relational join for tables already imported into a SQL database.
-- Adapt schema names to your database. One row per radiology source row,
-- provided patients.subject_id and admissions.hadm_id are unique.
SELECT
    r.*,
    p.gender,
    p.anchor_age,
    p.anchor_year,
    p.anchor_year_group,
    a.admittime,
    a.dischtime,
    a.admission_type,
    a.hospital_expire_flag,
    CASE
        WHEN p.subject_id IS NULL THEN 'patient_not_in_ehr'
        WHEN r.hadm_id IS NULL THEN 'patient_only_missing_hadm_id'
        WHEN a.hadm_id IS NULL THEN 'patient_only_unmatched_or_conflicting_hadm_id'
        ELSE 'patient_and_admission_matched'
    END AS linkage_status
FROM mimiciv_note.radiology AS r
LEFT JOIN mimiciv_hosp.patients AS p
    ON p.subject_id = r.subject_id
LEFT JOIN mimiciv_hosp.admissions AS a
    ON a.hadm_id = r.hadm_id
   AND a.subject_id = r.subject_id;
