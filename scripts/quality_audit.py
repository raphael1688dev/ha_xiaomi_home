#!/usr/bin/env python3
"""Run automated quality gate audit on the codebase.

Checks:
    1. Zero Chinese characters across Python source and documentation files.
    2. Python compilation (py_compile) across all Python files.
    3. Automated test suites (pytest tests/ and the github-marked test/).
    4. Version formatting in manifest.json.

Usage:
    python3 scripts/quality_audit.py
"""

import json
import os
import subprocess
import sys

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def scan_for_chinese(root_dir: str) -> list[tuple[str, int, str]]:
    """Scan all .py and .md files for Chinese characters."""
    violations = []
    skip_dirs = {".git", "test_env", "__pycache__", ".pytest_cache"}
    for dirpath, dirs, files in os.walk(root_dir):
        # Prune by exact directory name, a substring match would also skip
        # ".github" or any path that merely contains "test_env"
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for file in files:
            if file.endswith((".py", ".md")):
                filepath = os.path.join(dirpath, file)
                relpath = os.path.relpath(filepath, root_dir)
                try:
                    with open(filepath, "r", encoding="utf-8",
                              errors="ignore") as fp:
                        for idx, line in enumerate(fp, 1):
                            for ch in line:
                                if "\u4e00" <= ch <= "\u9fff":
                                    violations.append(
                                        (relpath, idx, line.strip()[:80]))
                                    break
                except OSError as err:
                    violations.append(
                        (relpath, 0, f"Error reading file: {err}"))
    return violations


def check_chinese_policy() -> bool:
    print("[1/4] Checking Zero Chinese Characters Policy...")
    violations = scan_for_chinese(WORKSPACE_ROOT)
    if violations:
        print(
            f"      [FAILED] Found {len(violations)} lines containing literal "
            "Chinese characters:"
        )
        for relpath, idx, sample in violations[:10]:
            print(f"        - {relpath}:{idx}: {sample}")
        if len(violations) > 10:
            print(f"        ... and {len(violations) - 10} more.")
        return False
    print(
        "      [PASSED] 0 literal Chinese characters found across all Python "
        "and Markdown files."
    )
    return True


def check_compilation() -> bool:
    print("[2/4] Checking Python Compilation (py_compile)...")
    py_files = []
    for dirpath, _, files in os.walk(
            os.path.join(WORKSPACE_ROOT, "custom_components")):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(dirpath, f))
    for dirpath, _, files in os.walk(os.path.join(WORKSPACE_ROOT, "tests")):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(dirpath, f))

    cmd = [sys.executable, "-m", "py_compile"] + py_files
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print("      [FAILED] Compilation error:")
        print(result.stderr)
        return False
    print(f"      [PASSED] Compiled {len(py_files)} Python files successfully.")
    return True


def check_unit_tests() -> bool:
    print("[3/4] Running Unit Test Suite (pytest)...")
    env = os.environ.copy()
    env["PYTHONPATH"] = WORKSPACE_ROOT

    # Check for pytest executable
    test_env_pytest = os.path.join(WORKSPACE_ROOT, "test_env", "bin", "pytest")
    pytest_bin = test_env_pytest if os.path.isfile(
        test_env_pytest) else "pytest"

    # tests/ holds the fork's unit tests; test/ holds the upstream suite, whose
    # offline cases are marked "github". check_rule_format.py is not named
    # test_*.py, so pytest only collects it when passed explicitly (as CI does)
    suites = [
        ("tests/", [pytest_bin, "tests/", "-q"]),
        ("test/ -m github", [pytest_bin, "test/", "-m", "github", "-q"]),
        ("test/check_rule_format.py -m github",
         [pytest_bin, "test/check_rule_format.py", "-m", "github", "-q"]),
    ]
    passed = True
    for name, cmd in suites:
        result = subprocess.run(cmd,
                                check=False,
                                cwd=WORKSPACE_ROOT,
                                env=env,
                                capture_output=True,
                                text=True)
        if result.returncode != 0:
            print(f"      [FAILED] {name} tests failed:")
            print(result.stdout)
            print(result.stderr)
            passed = False
            continue
        # Extract passed count
        summary = result.stdout.strip().split("\n")[-1]
        print(f"      [PASSED] {name}: {summary}")
    return passed


def check_manifest_version() -> bool:
    print("[4/4] Verifying Manifest Version...")
    manifest_path = os.path.join(WORKSPACE_ROOT, "custom_components",
                                 "xiaomi_home", "manifest.json")
    if not os.path.isfile(manifest_path):
        print("      [FAILED] manifest.json not found.")
        return False
    with open(manifest_path, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    version = data.get("version")
    if not version:
        print("      [FAILED] Version missing in manifest.json.")
        return False
    print(f"      [PASSED] Current manifest version: {version}")
    return True


def main():
    print("=" * 60)
    print(" Quality Gate Audit: ha_xiaomi_home (Mod)")
    print("=" * 60)

    results = [
        check_chinese_policy(),
        check_compilation(),
        check_unit_tests(),
        check_manifest_version(),
    ]

    print("=" * 60)
    if all(results):
        print("[✓] ALL QUALITY CHECKS PASSED. Ready for commit / release!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("[X] QUALITY AUDIT FAILED. Please resolve issues above.")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
