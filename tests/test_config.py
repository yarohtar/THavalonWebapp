"""The session signing key comes from SECRET_KEY.  Run: python -m pytest"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE = "import sys; sys.path.insert(0, '.'); import webapp; print(webapp.app.secret_key)"


def run(**env):
    base = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "REDIS_URL")}
    # A local .env must not interfere: run from a copy of the environment only.
    base["PYTHON_DOTENV_DISABLED"] = "1"
    return subprocess.run([sys.executable, "-c", CODE], cwd=ROOT, env={**base, **env},
                          capture_output=True, text=True)


def test_uses_secret_key_from_environment():
    r = run(SECRET_KEY="k" * 64)
    assert r.returncode == 0 and r.stdout.strip() == "k" * 64


def test_refuses_to_start_without_key_on_the_server():
    r = run(REDIS_URL="redis://localhost:6379/0")
    assert r.returncode != 0 and "SECRET_KEY is not set" in r.stderr


def test_random_key_locally():
    a, b = run(), run()
    assert a.returncode == 0 and len(a.stdout.strip()) == 64
    assert a.stdout != b.stdout and a.stdout.strip() != "secret"
