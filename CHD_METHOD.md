# MIMIC-IV to a code-defined CHD cohort

## Selection method

Use MIMIC-IV v3.1 `hosp/diagnoses_icd.csv.gz` and `hosp/patients.csv.gz`. Include a patient when at least one hospital diagnosis in any sequence position satisfies either rule:

- `icd_version == 9` and the normalized ICD category is 745, 746, or 747.
- `icd_version == 10` and the normalized ICD category is Q20 through Q28, inclusive.

Normalize codes by stripping whitespace, converting to uppercase, and removing periods. Match the first three characters, checking ICD version explicitly. Require the selected `subject_id` to exist in the EHR patients table, then deduplicate to one cohort row per patient. No minimum number of codes, principal-diagnosis restriction, age restriction, or date restriction is applied.

```python
def matches(code, version):
    code = code.strip().upper().replace('.', '')
    return (
        version == '9' and code[:3] in {'745', '746', '747'}
    ) or (
        version == '10' and code[:3] in {f'Q{i}' for i in range(20, 29)}
    )
```

These user-specified ranges include congenital vascular malformations. The output is a broad code-defined congenital cardiovascular-malformation cohort; it has not been clinically adjudicated. A single billing diagnosis establishes eligibility under this method, but does not establish a validated clinical phenotype.

## Run locally

Python 3.10+; standard library only. Obtain credentialed access to both source releases through PhysioNet before running. From the repository directory in PowerShell:

```powershell
py -3 .\build_chd_cohort.py --data-root "D:\Hang\SVP_project\MIMIC_data" --output-dir ".\results\CHD"
```

Replace the data path as needed. On other systems use `python3` or `python` in place of `py -3`. The output directory must not already exist for a fresh run. The EHR extraction directory may contain an extra nested folder; the script resolves a unique compressed patients table. The note release is expected under `mimic-iv-note-deidentified-free-text-clinical-notes-2.2/note`.

The script reads compressed source tables and streams the note exports. If the extracted file `note/discharge.csv/discharge.csv` exists, it uses that discharge copy with a 16 MiB buffer; otherwise it uses `discharge.csv.gz`. Dictionary joins use both `icd_code` and `icd_version`.

`--resume` is intended only for the same source versions and cohort definition. It reuses existing export CSVs after checking subject membership and counting rows. This does **not** prove completeness: move any known incomplete CSV out of the output directory before resuming. A new output directory is preferable when source data or selection rules change. Do not run concurrent extractions into the same output directory.

## Output grain and scope

The cohort is patient-level. Export all available records for each selected patient, including admissions without a qualifying CHD diagnosis and notes with missing admission IDs. Use `chd_qualifying_admission_ids.csv` when a downstream analysis requires only the admissions carrying qualifying codes. The extraction itself does not apply that narrower restriction.

| File generated locally | Contents |
|---|---|
| `chd_cohort_ids.csv` | Unique selected subject IDs |
| `chd_cohort.csv` | One row per subject with qualifying code and admission summaries |
| `chd_qualifying_admission_ids.csv` | Distinct subject/admission pairs carrying qualifying codes |
| `chd_qualifying_diagnoses.csv` | Inclusion diagnosis rows and dictionary descriptions |
| `demographics.csv` | Selected rows from the patients table |
| `admissions.csv` | All hospital admissions for cohort subjects |
| `diagnoses.csv` | All diagnoses for cohort subjects, descriptions, and qualifying-code flag |
| `procedures.csv` | All billed ICD procedures for cohort subjects and dictionary descriptions |
| `icu_procedure_events.csv` | ICU procedure events, in their original event schema |
| `radiology_reports.csv` | Complete radiology notes for cohort subjects |
| `radiology_details.csv` | Radiology metadata; potentially multiple rows per note |
| `discharge_summaries.csv` | Complete discharge summaries for cohort subjects |
| `consultation_reports.csv` | Header-only placeholder: consultation notes unavailable in the source release |
| `cohort_audit.json` | Versions, definition, record scope, source paths, row counts and patient coverage |
| `README.md` | Explanation saved with the local exports |

Standalone consultation reports are not distributed in MIMIC-IV-Note v2.2. The empty placeholder means unavailable data, not an absence of clinical consultations. Discharge summaries are not relabeled as consultations.

Match patients by `subject_id`, admissions by `subject_id` plus `hadm_id`, and radiology details by `note_id`. Avoid unrestricted joins across these event tables, which can multiply rows. Patient `anchor_age` is age in `anchor_year`, not age at each admission. Admission-specific race, insurance, language and marital status remain in admissions. Do not assume note v2.2 covers all EHR v3.1 admissions.

## Local run results

The local extraction identified **4,528 unique patients** among 364,627 EHR subjects, with 6,492 qualifying diagnosis rows in 6,276 admissions.

| Export | Rows | Unique patients |
|---|---:|---:|
| Demographics | 4,528 | 4,528 |
| Admissions | 17,760 | 4,528 |
| All diagnoses | 264,801 | 4,528 |
| ICD procedures | 33,809 | 3,845 |
| ICU procedure events | 47,103 | 2,509 |
| Radiology reports | 73,913 | 3,608 |
| Radiology details | 202,448 | 3,649 |
| Discharge summaries | 11,758 | 3,541 |

Radiology details and report text have different patient coverage in the source; details do not establish that a corresponding report text is available. Only source records actually distributed are exported.

Validation checked unique cohort IDs, membership of every exported subject in the cohort, agreement between CSV counts and the audit, and a qualifying diagnosis for every selected patient. ICD-category and version boundary checks covered inclusion and exclusion examples. Aggregate counts are provided for reproducibility; no patient-level examples are published.

For manuscript methods: “We identified a patient-level cohort in MIMIC-IV v3.1 using at least one hospital diagnosis, in any diagnosis position, with ICD-9 categories 745–747 or ICD-10 categories Q20–Q28. We normalized diagnosis codes by removing periods and matched category prefixes with ICD version checked explicitly. Selected patients were required to appear in the patients table. We extracted all available hospital diagnoses, billed ICD procedures, ICU procedure events, patient demographics, hospital admissions, and MIMIC-IV-Note v2.2 radiology reports and discharge summaries for these subjects. Eligibility was not restricted by age, date, or principal diagnosis. This broad code-defined cohort included congenital vascular malformations.”

## Data access and citation

This repository distributes code and documentation only. Keep patient IDs, clinical text and derived CSVs within your authorized environment. Do not upload the generated CHD folder, audit files containing local paths, or clinical data to public GitHub. Cite both source releases using their PhysioNet citation information:

- [MIMIC-IV v3.1](https://physionet.org/content/mimiciv/3.1/)
- [MIMIC-IV-Note v2.2](https://physionet.org/content/mimic-iv-note/2.2/)
- [Note module and linkage](https://mimic.mit.edu/docs/iv/modules/note/)
