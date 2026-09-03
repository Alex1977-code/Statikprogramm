"""Build-Stempel schreiben (GitHub Actions):  python packaging/write_build.py [sha] [datum]"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from statik3d.update import write_build_stamp  # noqa: E402

sha = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_SHA", "")
date = sys.argv[2] if len(sys.argv) > 2 else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
print(write_build_stamp(sha, date), sha[:7], date)
