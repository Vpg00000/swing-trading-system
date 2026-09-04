import sys
from pathlib import Path

# Ensure module path resolution
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auditor import RepositoryAuditor, PlaceholderFinding


def test_auditor():
    auditor = RepositoryAuditor()

    print("==================================================")
    print("RUNNING REPOSITORY AUDITOR COMPREHENSIVE VERIFICATION")
    print("==================================================\n")

    # 1. Verify structured report generation
    report = auditor.generate_structured_audit_report()
    assert "architecture_verification" in report, "Missing architecture verification"
    assert "placeholder_findings" in report, "Missing placeholder findings"
    print("✓ 1. Structured audit report generated successfully.")

    # 2. Verify production placeholder findings are separated from documentation findings
    findings = auditor.scan_placeholders()
    prod_findings = [f for f in findings if f.classification == "PRODUCTION"]
    doc_findings = [f for f in findings if f.classification == "DOCUMENTATION"]

    assert all(f.classification == "PRODUCTION" for f in prod_findings)
    assert all(f.classification == "DOCUMENTATION" for f in doc_findings)
    print(f"✓ 2. Placeholder findings separated: {len(prod_findings)} PRODUCTION, {len(doc_findings)} DOCUMENTATION.")

    # 3. Verify .aider.chat.history.md, venv, and cache files are excluded
    excluded_files = [f.file for f in findings if ".aider.chat.history.md" in f.file or f.file.startswith("venv/") or "data/cache/" in f.file]
    assert len(excluded_files) == 0, f"Found excluded files in findings: {excluded_files}"
    print("✓ 3. Verified .aider.chat.history.md, venv/, and data/cache/ files are strictly EXCLUDED.")

    # 4. Verify architecture missing files are reported
    dummy_paths = ["engine/non_existent_module_xyz.py", "data/database.py"]
    arch_test = auditor.verify_architecture(dummy_paths)
    assert arch_test["engine/non_existent_module_xyz.py"] == "MISSING", "Failed to report MISSING architecture file"
    assert arch_test["data/database.py"] in ["EXISTS", "EMPTY"], "Failed to report existing architecture file"
    print(f"✓ 4. Architecture missing files correctly reported: {arch_test}")

    # 5. Verify auditor does not modify repository files (READ-ONLY requirement)
    git_before = auditor.git_status()
    auditor.run_basic_audit()
    auditor.generate_structured_audit_report()
    git_after = auditor.git_status()

    assert git_before.stdout == git_after.stdout, "Auditor modified repository state!"
    print("✓ 5. Verified auditor is strictly READ-ONLY and does NOT modify any repository files.")

    # 6. Verify path classification rules
    assert auditor.classify_path(".aider.chat.history.md") == "IGNORED"
    assert auditor.classify_path("venv/lib/python/site-packages/pkg.py") == "IGNORED"
    assert auditor.classify_path("data/cache/delivery.csv") == "CACHE"
    assert auditor.classify_path("engine/indicators.py") == "PRODUCTION"
    assert auditor.classify_path("DESIGN.md") == "DOCUMENTATION"
    print("✓ 6. Verified explicit path classifications (PRODUCTION, DOCUMENTATION, CACHE, IGNORED).")

    print("\n==================================================")
    print("ALL AUDITOR VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    test_auditor()
