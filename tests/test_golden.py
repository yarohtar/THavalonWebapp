"""The engine behaves exactly as recorded in golden_engine.json (deals, role
info, every step of many random games, views, errors, undo). Fails after
any behaviour change; if the change is intended, regenerate the file (see
golden_engine.py)."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def test_engine_behaves_as_recorded():
    env = dict(os.environ, PYTHONHASHSEED="0")
    out = subprocess.run([sys.executable, os.path.join(HERE, "golden_engine.py")],
                         env=env, capture_output=True, text=True, check=True).stdout
    with open(os.path.join(HERE, "golden_engine.json")) as f:
        expected = json.load(f)
    got = json.loads(out)
    changed = sorted(k for k in expected if got.get(k) != expected[k])
    assert not changed, f"engine behaviour changed in {len(changed)} cases: {changed[:10]}"
    assert got.keys() == expected.keys()
