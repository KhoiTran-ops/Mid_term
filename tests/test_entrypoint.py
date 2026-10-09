import json
from pathlib import Path
import subprocess
import sys

import pytest


def test_single_entrypoint_works_from_another_directory_without_downloads(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable,str(root / 'run.py'),'doctor'],
        cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=20)
    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    assert Path(status['project']) == root
    assert status['downloads_started'] is False


@pytest.mark.parametrize('command, expected', [('data', 'financials'), ('import-legacy', '--source')])
def test_unified_collection_help_is_available_without_dnse_authentication(tmp_path, command, expected):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable,str(root / 'run.py'),command,'--help'],
        cwd=tmp_path,capture_output=True,text=True,encoding='utf-8',timeout=20)
    assert result.returncode == 0
    assert expected in result.stdout
