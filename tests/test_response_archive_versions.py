import hashlib
import json
from pathlib import Path
from stock_reports.data_sources.archive import ResponseArchive


def test_changed_response_at_same_url_does_not_destroy_earlier_evidence(tmp_path):
    archive=ResponseArchive(tmp_path)
    for payload in (b'first published version',b'restated version',b'restated version'):
        archive.save('cafef','https://cafef.vn/report',payload,'.html')
    receipts=[json.loads(line) for line in (tmp_path/'receipts.jsonl').read_text().splitlines()]
    assert receipts[0]['path']!=receipts[1]['path']
    assert receipts[1]['path']==receipts[2]['path']
    for item in receipts:
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
