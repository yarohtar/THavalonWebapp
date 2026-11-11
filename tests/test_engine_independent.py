"""The game engine (the thavalon package) knows nothing about the website."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WEB = ["flask", "werkzeug", "jinja2", "markupsafe", "redis", "fakeredis", "dotenv",
       "webapp", "store", "events", "dev", "admin", "rules", "rule_notes", "rule_text",
       "votes", "access"]


def test_engine_imports_no_web_modules():
    code = ("import pkgutil, importlib, sys, thavalon\n"
            "for m in pkgutil.iter_modules(thavalon.__path__):\n"
            "    importlib.import_module('thavalon.' + m.name)\n"
            f"print(sorted(set({WEB!r}) & set(sys.modules)))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.strip()
    assert out == "[]"
