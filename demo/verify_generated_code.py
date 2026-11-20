"""Independent checks, executed inside Docker with a cleared environment."""
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

project = Path(sys.argv[1]).resolve()
followup = len(sys.argv) > 2 and sys.argv[2] == 'followup'
results = {}
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    source = root/'input.csv'
    source.write_text('name,email,amount\nAlice,alice@example.com,100\nBob,,200\nAlice,alice@example.com,100\nCarol,carol@example.com,\n')
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    report = root/'report.json'
    def run(*args):
        return subprocess.run([sys.executable,'-m','csv_qc',*map(str,args)],cwd=project,text=True,capture_output=True,timeout=20)
    check = run(source,'-o',report)
    assert check.returncode == 0, check.stderr
    data = json.loads(report.read_text())
    assert data['total_rows'] == 4
    assert data['duplicate_row_count'] == 1
    assert {col['name']:col['missing_count'] for col in data['columns']} == {'name':0,'email':1,'amount':1}
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    results['missing_values_and_duplicate_count'] = True
    results['input_unchanged'] = True
    if followup:
        source.write_text('name,value\nAlice,1\n Alice,1\nAlice,1\nBob,2\n')
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        deduped = root/'deduped.csv'
        check = run(source,'-o',report,'--dedupe-output',deduped)
        assert check.returncode == 0, check.stderr
        data = json.loads(report.read_text())
        assert data['duplicate_row_count'] == 1, data
        with deduped.open(newline='') as file:
            rows = list(csv.reader(file))
        assert rows == [['name','value'],['Alice','1'],[' Alice','1'],['Bob','2']], rows
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        results['exact_dedupe_preserves_first_row_and_whitespace'] = True
        results['dedupe_keeps_original_sha256'] = True
        rejected = run(source,'--dedupe-output',source)
        assert rejected.returncode != 0
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        results['rejects_input_overwrite'] = True
print(json.dumps({'passed':True,'checks':results},ensure_ascii=False,indent=2))
