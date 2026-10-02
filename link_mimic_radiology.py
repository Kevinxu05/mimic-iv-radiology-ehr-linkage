"""Stream MIMIC-IV-Note 2.2 reports into an audited MIMIC-IV 3.1 join.

Python 3.10+, standard library only. Output grain: one row per source report.
Missing admission identifiers are never inferred from dates.
"""
import argparse
import csv
import gzip
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def rows(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as handle:
        yield from csv.DictReader(handle)


def find(root, name):
    candidates = sorted(root.rglob(name + '.csv.gz'))
    if not candidates:
        candidates = sorted(p for p in root.rglob(name + '.csv') if p.is_file())
    if len(candidates) != 1:
        raise ValueError(f'Expected exactly one {name} table under {root}: {candidates}')
    return candidates[0]


def load_table(db, name, path, keys):
    iterator = rows(path)
    first = next(iterator)
    columns = list(first)
    if not set(keys).issubset(columns):
        raise ValueError(f'Missing keys in {path}')
    quoted = ', '.join('"' + c + '" TEXT' for c in columns)
    db.execute(f'CREATE TABLE {name} ({quoted}, PRIMARY KEY ({",".join(keys)}))')
    insert = f'INSERT INTO {name} VALUES ({",".join("?" for _ in columns)})'
    batch = [tuple(first[c] for c in columns)]
    count = 1
    for row in iterator:
        batch.append(tuple(row[c] for c in columns))
        count += 1
        if len(batch) == 10000:
            db.executemany(insert, batch)
            batch.clear()
    db.executemany(insert, batch)
    db.commit()
    return columns, count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path(r'D:\Hang\SVP_project\MIMIC_data'))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=0, help='0: full dataset; positive: first N reports')
    args = parser.parse_args()
    if args.limit < 0:
        parser.error('--limit must be nonnegative')
    ehr = args.data_root / 'mimic-iv-3.1'
    note = args.data_root / 'mimic-iv-note-deidentified-free-text-clinical-notes-2.2'
    inputs = {name: find(root, name) for name, root in [('patients', ehr), ('admissions', ehr), ('radiology', note)]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / 'radiology_ehr.csv.gz'
    audit_path = args.output_dir / 'linkage_audit.json'
    index = args.output_dir / 'ehr_index.sqlite'
    if any(p.exists() for p in (output, audit_path, index)):
        raise FileExistsError('Use a new output directory; existing results are not overwritten.')
    db = sqlite3.connect(index)
    db.row_factory = sqlite3.Row
    try:
        pc, pn = load_table(db, 'patients', inputs['patients'], ['subject_id'])
        ac, an = load_table(db, 'admissions', inputs['admissions'], ['hadm_id'])
        statuses = Counter()
        outside = 0
        seen = set() if args.limit else None
        iterator = rows(inputs['radiology'])
        first = next(iterator)
        rc = list(first)
        required = {'note_id', 'subject_id', 'hadm_id', 'charttime', 'text'}
        if not required.issubset(rc):
            raise ValueError('Radiology columns do not match the expected schema')
        patient_cols = [c for c in pc if c != 'subject_id']
        admission_cols = [c for c in ac if c not in ('subject_id', 'hadm_id')]
        fields = rc + ['patient_' + c for c in patient_cols] + ['admission_' + c for c in admission_cols] + ['linkage_status', 'charttime_within_admission']
        import itertools
        with gzip.open(output, 'wt', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for n, row in enumerate(itertools.chain([first], iterator), 1):
                patient = db.execute('SELECT * FROM patients WHERE subject_id=?', (row['subject_id'],)).fetchone()
                admission = db.execute('SELECT * FROM admissions WHERE hadm_id=?', (row['hadm_id'],)).fetchone() if row['hadm_id'] else None
                if admission and admission['subject_id'] != row['subject_id']:
                    status = 'admission_subject_mismatch'
                    admission = None
                elif not patient:
                    status = 'patient_not_in_ehr'
                elif not row['hadm_id']:
                    status = 'patient_only_missing_hadm_id'
                elif not admission:
                    status = 'patient_only_unmatched_hadm_id'
                else:
                    status = 'patient_and_admission_matched'
                within = ''
                if admission and all((row['charttime'], admission['admittime'], admission['dischtime'])):
                    within = str(admission['admittime'] <= row['charttime'] <= admission['dischtime']).lower()
                    outside += within == 'false'
                row.update({'patient_' + c: patient[c] if patient else '' for c in patient_cols})
                row.update({'admission_' + c: admission[c] if admission else '' for c in admission_cols})
                row.update(linkage_status=status, charttime_within_admission=within)
                writer.writerow(row)
                statuses[status] += 1
                if seen is not None:
                    if row['note_id'] in seen:
                        raise ValueError('Duplicate note_id in sample')
                    seen.add(row['note_id'])
                if n % 100000 == 0:
                    print(f'Processed {n:,} reports', flush=True)
                if args.limit and n >= args.limit:
                    break
        audit = {'ehr_version': '3.1', 'note_version': '2.2', 'inputs': {k: str(v) for k, v in inputs.items()}, 'sample_limit': args.limit, 'patients_rows': pn, 'admissions_rows': an, 'report_rows': sum(statuses.values()), 'linkage_status_counts': dict(statuses), 'matched_reports_outside_admission_interval': outside, 'output': str(output)}
        audit_path.write_text(json.dumps(audit, indent=2), encoding='utf-8')
        print(json.dumps(audit, indent=2))
    finally:
        db.close()


if __name__ == '__main__':
    main()
