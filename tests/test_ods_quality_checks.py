import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ods_quality_checks as checks  # noqa: E402

ALL_TABLES = {t for c in checks.QUALITY_CHECKS for t in c["requires"]}


class QualityCheckContractTests(unittest.TestCase):
    def test_zero_violations_pass_and_nonzero_fail(self):
        results = checks.run_quality_checks(lambda sql: [(0,)], ALL_TABLES)
        self.assertTrue(all(status == "PASS" for _, status, _ in results))
        results = checks.run_quality_checks(lambda sql: [(3,)], ALL_TABLES)
        self.assertTrue(all(status == "FAIL" and "3 violation" in detail
                            for _, status, detail in results))

    def test_query_error_fails_loudly_without_aborting_remaining_checks(self):
        def broken(sql):
            raise RuntimeError("Invalid column name 'icd_family'")

        results = checks.run_quality_checks(broken, ALL_TABLES)
        self.assertEqual(len(results), len(checks.QUALITY_CHECKS))
        self.assertTrue(all(status == "FAIL" and "could not run" in detail
                            for _, status, detail in results))

    def test_undeployed_tables_skip_and_are_never_reported_as_passing(self):
        results = checks.run_quality_checks(lambda sql: [(0,)], {"diagnoses", "icd_reference"})
        by_status = {status for _, status, _ in results}
        self.assertEqual(by_status, {"PASS", "SKIP"})
        for name, status, detail in results:
            if status == "SKIP":
                self.assertIn("ops_", detail)

    def test_module_is_self_contained_for_notebook_inlining(self):
        # The validation notebook embeds this file verbatim, so it must not
        # import anything a bare Fabric kernel would lack.
        import ast

        tree = ast.parse(Path(checks.__file__).read_text(encoding="utf-8"))
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertEqual(imports, [])


if __name__ == "__main__":
    unittest.main()
