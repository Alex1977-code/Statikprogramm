"""Alle Testsuiten nacheinander ausfuehren:  python -m tests.run_all  [--gui]"""
import os
import subprocess
import sys

SUITES = ["tests.test_verification", "tests.test_solver_ext", "tests.test_ec3",
          "tests.test_importers", "tests.test_report", "tests.test_web", "tests.test_update", "tests.test_supports", "tests.test_sections", "tests.test_rfem", "tests.test_rfem6", "tests.test_hicad", "tests.test_joints"]


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    failed = []
    suites = list(SUITES)
    if "--gui" in argv:
        suites.append("tests.test_gui_smoke")
    for s in suites:
        cmd = [sys.executable, "-m", s]
        if s.endswith("gui_smoke") and sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
            cmd = ["xvfb-run", "-a"] + cmd
        print(f"\n===== {s} =====")
        r = subprocess.run(cmd, cwd=here)
        if r.returncode != 0:
            failed.append(s)
    print("\n" + "=" * 60)
    print("ALLE TESTS BESTANDEN" if not failed else f"FEHLGESCHLAGEN: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
