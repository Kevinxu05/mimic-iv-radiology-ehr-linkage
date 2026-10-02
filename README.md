# MIMIC radiology–EHR linkage

Python pipeline linking **MIMIC-IV-Note v2.2 radiology reports** to **MIMIC-IV v3.1 patients and hospital admissions**, with one output row per source report and an audit of linkage outcomes.

## Data access

This repository contains code only. Researchers must obtain authorized access to [MIMIC-IV v3.1](https://physionet.org/content/mimiciv/3.1/) and [MIMIC-IV-Note v2.2](https://physionet.org/content/mimic-iv-note/2.2/) through PhysioNet and run the pipeline locally. Patient-level records, report text, and derived data are not distributed in this repository. Their use remains governed by the applicable PhysioNet license and data-use agreement.

## Requirements and layout

Python 3.10 or later; no third-party packages required.

```text
MIMIC_data/
  mimic-iv-3.1/
    hosp/
      patients.csv.gz
      admissions.csv.gz
  mimic-iv-note-deidentified-free-text-clinical-notes-2.2/
    note/
      radiology.csv.gz
```

An extra nested EHR extraction directory is supported. Each required table must resolve to exactly one compressed file, or one uncompressed CSV if a compressed file is absent.

## Run

From this repository directory in PowerShell:

```powershell
py -3 .\link_mimic_radiology.py --data-root "D:\Hang\SVP_project\MIMIC_data" --output-dir ".\results\radiology_test" --limit 1000
```

Full run:

```powershell
py -3 .\link_mimic_radiology.py --data-root "D:\Hang\SVP_project\MIMIC_data" --output-dir ".\results\radiology_full"
```

Replace the data path with your local location. On systems without the Windows Python launcher, use `python` or `python3` instead of `py -3`. Use a new output directory for each run; existing results are not overwritten.

## Linkage rules

- Match patients on `subject_id`.
- Match admissions on both `hadm_id` and `subject_id`.
- Preserve reports with missing or unmatched keys and record `linkage_status`.
- Never infer an admission from date proximity.
- Preserve source note columns, including multiline report text. Prefix patient and admission context columns with `patient_` and `admission_`.
- Flag whether `charttime` lies within inclusive `admittime` and `dischtime` bounds. This is a quality-control flag and does not override the recorded admission identifier.

## Generated outputs

- `radiology_ehr.csv.gz`: compressed CSV of reports and linked context.
- `linkage_audit.json`: versions, source paths, reference row counts, linkage counts, and timestamp quality-control counts.
- `ehr_index.sqlite`: indexed patient and admission reference tables.

To extract an uncompressed CSV, replace the path below with your actual output file:

```powershell
py -3 -c "import gzip, shutil; from pathlib import Path; p=Path(r'results/radiology_full/radiology_ehr.csv.gz'); source=gzip.open(p,'rb'); target=p.with_suffix('').open('xb'); shutil.copyfileobj(source,target); source.close(); target.close()"
```

The target CSV must not already exist. Full datasets can exceed Excel's worksheet row limit.

## Validation and limitations

The pipeline was run locally on all 2,321,355 source radiology reports. The generated CSV was read back to confirm that row and linkage-status counts matched its audit and report text was nonempty. No patient-level validation examples are published.

Reference primary keys are checked during SQLite loading. Sample runs check note-ID duplicates; the full run does not independently check full-source note-ID uniqueness. The first N reports form a smoke sample, not a random sample. Failed runs may leave incomplete files; use results only after a successful run with a completed audit.

Note v2.2 and EHR v3.1 have different coverage. Not every EHR admission has a radiology report, and some note keys may be absent from EHR v3.1. Inspect the audit before defining your cohort.

Labs, diagnoses, medications, ICU stays, and radiology details are not incorporated by this pipeline. They can contain multiple rows per admission or note. Aggregate to the intended analytical grain or keep separate event tables before joining to avoid multiplying report rows. `radiology_detail` links by `note_id`. ICU attribution requires a prespecified time-window rule in addition to matching patient and admission IDs.

`radiology_linkage.sql` provides an illustrative relational equivalent for already imported tables; adapt schema names to your database. Its unmatched-admission status combines missing references and subject conflicts, while Python distinguishes those cases.

## Documentation and citation

- [MIMIC note module and linking keys](https://mimic.mit.edu/docs/iv/modules/note/)
- [Radiology detail](https://mimic.mit.edu/docs/iv/modules/note/radiology_detail.html)
- [MIMIC-IV v3.1 citation and access](https://physionet.org/content/mimiciv/3.1/)
- [MIMIC-IV-Note v2.2 citation and access](https://physionet.org/content/mimic-iv-note/2.2/)

Cite both dataset releases in research using this pipeline. Keep all generated patient-level files within your authorized research environment.
