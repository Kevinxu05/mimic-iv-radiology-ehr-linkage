"""Extract a patient-level cohort using ICD-9 745–747 / ICD-10 Q20–Q28."""
import argparse
import csv
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(2**31 - 1)


def read(path):
    if path.name == 'discharge.csv.gz':
        expanded = path.parent / 'discharge.csv' / 'discharge.csv'
        if expanded.is_file():
            path = expanded
    if path.suffix == '.gz':
        handle = gzip.open(path, 'rt', encoding='utf-8', newline='')
    else:
        handle = open(path, 'rt', encoding='utf-8', newline='', buffering=16 * 1024 * 1024)
    with handle as f:
        yield from csv.DictReader(f)


def matches(code, version):
    code = code.strip().upper().replace('.', '')
    return (version == '9' and code[:3] in {'745', '746', '747'}) or (
        version == '10' and code[:3] in {f'Q{i}' for i in range(20, 29)})


def export(source, target, cohort, dictionary=None, flag=False):
    if target.exists():
        subjects = set()
        count = 0
        with target.open(encoding='utf-8', newline='') as f:
            for row in csv.DictReader(f):
                if row['subject_id'] not in cohort:
                    raise ValueError(f'Unexpected subject in {target}')
                subjects.add(row['subject_id']); count += 1
        print(f'Verified existing {target.name}: {count:,} rows', flush=True)
        return {'rows': count, 'unique_patients': len(subjects), 'source': str(source)}
    count = 0
    subjects = set()
    iterator = read(source)
    first = next(iterator)
    fields = list(first)
    if dictionary is not None:
        fields += ['long_title']
    if flag:
        fields += ['is_chd_qualifying_diagnosis']
    import itertools
    with target.open('x', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in itertools.chain([first], iterator):
            if row['subject_id'] not in cohort:
                continue
            if dictionary is not None:
                row['long_title'] = dictionary.get((row['icd_code'], row['icd_version']), '')
            if flag:
                row['is_chd_qualifying_diagnosis'] = int(matches(row['icd_code'], row['icd_version']))
            writer.writerow(row)
            count += 1
            subjects.add(row['subject_id'])
    print(f'{target.name}: {count:,} rows, {len(subjects):,} patients', flush=True)
    return {'rows': count, 'unique_patients': len(subjects), 'source': str(source)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root', type=Path, default=Path(r'D:\Hang\SVP_project\MIMIC_data'))
    ap.add_argument('--output-dir', type=Path, required=True)
    ap.add_argument('--resume', action='store_true', help='Reuse completed CSVs; remove known incomplete CSVs before resuming')
    args = ap.parse_args()
    out = args.output_dir
    if out.exists() and not args.resume:
        raise FileExistsError('Choose a new output directory; existing results are not overwritten.')
    hosp_candidates = list((args.data_root / 'mimic-iv-3.1').rglob('patients.csv.gz'))
    if len(hosp_candidates) != 1:
        raise ValueError('Cannot resolve unique EHR hospital directory')
    hosp = hosp_candidates[0].parent
    note = args.data_root / 'mimic-iv-note-deidentified-free-text-clinical-notes-2.2' / 'note'
    patients = {r['subject_id'] for r in read(hosp / 'patients.csv.gz')}
    titles = {(r['icd_code'], r['icd_version']): r['long_title'] for r in read(hosp / 'd_icd_diagnoses.csv.gz')}
    qualifying = []
    missing = 0
    for row in read(hosp / 'diagnoses_icd.csv.gz'):
        if matches(row['icd_code'], row['icd_version']):
            if row['subject_id'] not in patients:
                missing += 1
                continue
            row['long_title'] = titles.get((row['icd_code'], row['icd_version']), '')
            qualifying.append(row)
    by_subject = defaultdict(list)
    for row in qualifying:
        by_subject[row['subject_id']].append(row)
    cohort = set(by_subject)
    out.mkdir(parents=True, exist_ok=args.resume)
    qfields = ['subject_id', 'hadm_id', 'seq_num', 'icd_code', 'icd_version', 'long_title']
    mode = 'w' if args.resume else 'x'
    with (out / 'chd_qualifying_diagnoses.csv').open(mode, encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=qfields)
        w.writeheader(); w.writerows(qualifying)
    with (out / 'chd_cohort_ids.csv').open(mode, encoding='utf-8', newline='') as f:
        w = csv.writer(f); w.writerow(['subject_id'])
        w.writerows((s,) for s in sorted(cohort, key=int))
    with (out / 'chd_cohort.csv').open(mode, encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['subject_id', 'qualifying_diagnosis_count', 'qualifying_admission_count', 'has_icd9_chd', 'has_icd10_chd', 'qualifying_icd9_codes', 'qualifying_icd10_codes'])
        for sid in sorted(cohort, key=int):
            rs = by_subject[sid]
            c9 = sorted({r['icd_code'] for r in rs if r['icd_version'] == '9'})
            c10 = sorted({r['icd_code'] for r in rs if r['icd_version'] == '10'})
            w.writerow([sid, len(rs), len({r['hadm_id'] for r in rs}), int(bool(c9)), int(bool(c10)), ';'.join(c9), ';'.join(c10)])
    audit = {'ehr_version': '3.1', 'note_version': '2.2', 'definition': 'Any diagnosis position: ICD-9 745–747 or ICD-10 Q20–Q28; normalized prefix matching with explicit ICD version', 'record_scope': 'All available records for selected patients, including non-CHD admissions and notes with missing hadm_id; no date restriction', 'ehr_patients': len(patients), 'cohort_patients': len(cohort), 'qualifying_diagnosis_rows': len(qualifying), 'qualifying_admissions': len({(r['subject_id'], r['hadm_id']) for r in qualifying}), 'qualifying_rows_missing_ehr_patient': missing, 'files': {}, 'consultation_reports': {'status': 'not_available_in_source_release', 'rows': None}}
    print(f'CHD cohort: {len(cohort):,} unique patients', flush=True)
    proc_titles = {(r['icd_code'], r['icd_version']): r['long_title'] for r in read(hosp / 'd_icd_procedures.csv.gz')}
    tasks = [
        ('demographics.csv', hosp / 'patients.csv.gz', None, False),
        ('admissions.csv', hosp / 'admissions.csv.gz', None, False),
        ('diagnoses.csv', hosp / 'diagnoses_icd.csv.gz', titles, True),
        ('procedures.csv', hosp / 'procedures_icd.csv.gz', proc_titles, False),
        ('radiology_reports.csv', note / 'radiology.csv.gz', None, False),
        ('discharge_summaries.csv', (note / 'discharge.csv' / 'discharge.csv') if (note / 'discharge.csv' / 'discharge.csv').is_file() else note / 'discharge.csv.gz', None, False),
        ('radiology_details.csv', note / 'radiology_detail.csv.gz', None, False),
        ('icu_procedure_events.csv', hosp.parent / 'icu' / 'procedureevents.csv.gz', None, False),
    ]
    for filename, source, dictionary, flag in tasks:
        audit['files'][filename] = export(source, out / filename, cohort, dictionary, flag)
    with (out / 'consultation_reports.csv').open(mode, encoding='utf-8', newline='') as f:
        csv.writer(f).writerow(['note_id', 'subject_id', 'hadm_id', 'charttime', 'text'])
    audit['files']['consultation_reports.csv'] = {'rows': 0, 'status': 'header_only_placeholder_not_available_in_source'}
    with (out / 'chd_qualifying_admission_ids.csv').open(mode, encoding='utf-8', newline='') as f:
        w = csv.writer(f); w.writerow(['subject_id', 'hadm_id'])
        w.writerows(sorted({(r['subject_id'], r['hadm_id']) for r in qualifying}, key=lambda x: (int(x[0]), int(x[1]))))
    audit['files']['chd_cohort_ids.csv'] = {'rows': len(cohort), 'unique_patients': len(cohort)}
    (out / 'cohort_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    (out / 'README.md').write_text('''# CHD cohort

Inclusion: at least one hospital diagnosis in ICD-9 745–747 or ICD-10 Q20–Q28, in any diagnosis position. Codes are normalized by removing periods and matched by category prefix, with ICD version checked explicitly. This is a broad code-defined cardiovascular congenital-malformation cohort, not a clinically adjudicated phenotype.

Each selected subject must exist in MIMIC-IV 3.1 patients. The exports include all available records for selected subjects, across all admissions and report dates. They are not restricted to qualifying CHD admissions. chd_qualifying_admission_ids.csv provides that narrower admission set if needed.

chd_cohort_ids.csv and chd_cohort.csv contain one row per patient. demographics.csv preserves the patients table: anchor_age is age in anchor_year, not age at every admission. Admission-specific race, insurance, language and marital status remain in admissions.csv. diagnoses.csv contains all diagnoses, their dictionary descriptions and a qualifying-code flag; chd_qualifying_diagnoses.csv contains only inclusion diagnoses. procedures.csv contains billed ICD procedures and dictionary descriptions; icu_procedure_events.csv contains ICU procedure events in a separate schema. radiology_reports.csv and discharge_summaries.csv preserve complete multiline report text and original identifiers. radiology_details.csv preserves the note metadata; it can have multiple rows per note.

MIMIC-IV-Note v2.2 has no standalone consultation notes. consultation_reports.csv is a header-only placeholder indicating unavailable source data, not evidence that no consultations occurred. Discharge summaries are supplied separately and are not relabeled as consultations. Note v2.2 coverage differs from EHR v3.1, so some selected patients may have no notes. Match patients by subject_id and admissions by subject_id plus hadm_id; do not drop notes solely because hadm_id is missing.

All CSVs use UTF-8 and standard quoted CSV syntax. Read with a proper CSV parser because text may contain embedded commas and newlines. Keep patient IDs and clinical text within the authorized local research environment. Do not upload this folder to public GitHub. Consult cohort_audit.json for source paths, row counts and note coverage.

Sources: https://physionet.org/content/mimiciv/3.1/ and https://physionet.org/content/mimic-iv-note/2.2/
''', encoding='utf-8')
    print(json.dumps(audit, indent=2), flush=True)


if __name__ == '__main__':
    main()
