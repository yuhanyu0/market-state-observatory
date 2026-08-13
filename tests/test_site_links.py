import subprocess
import sys
from pathlib import Path


def test_site_links():
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/"scripts/check_site_links.py")],cwd=root,capture_output=True,text=True)
    assert result.returncode==0, result.stdout+result.stderr
