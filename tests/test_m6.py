"""M6: real-repo cases, the worst-case reservation, coverage, snapshots, reference scoring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migrator.config import CaseConfig, load_case
from migrator.configuration import find_configuration
from migrator.evals.reference import (
    JudgeCache,
    Judgement,
    judge_key,
    normalise,
    select_items,
)
from migrator.graph import snapshot_belongs
from migrator.rules import apply_extra_dependencies
from migrator.verify import (
    Failure,
    VerifyResult,
    is_snapshot_failure,
    read_coverage,
    snapshot_only_test_files,
)
from tests.conftest import REPO_ROOT

CONFIGS = REPO_ROOT / "evals" / "configs"


def test_older_configuration_digests_are_unchanged() -> None:
    # The M6 cost field is left out of the digest while unset (M2-M5 results stay attached).
    assert (
        find_configuration("opus-low", CONFIGS).digest() == "d81d48a907d0"
    )  # as recorded in .claude/hillclimb/dev/v3
    m6 = find_configuration("m6-opus-low", CONFIGS)
    assert (m6.cost.max_run_usd, m6.cost.max_month_usd, m6.cost.reserve_attempt_usd) == (
        8.0,
        50.0,
        0.15,
    )
    assert m6.repair == find_configuration("opus-low", CONFIGS).repair


def test_real_repo_cases_load_with_an_upstream() -> None:
    case = load_case(REPO_ROOT / "evals" / "m6-cases" / "opossum-ui" / "case.toml")
    assert case.upstream is not None and case.source == ""
    assert case.repo.node == "16" and case.repo.coverage and case.repo.update_snapshots
    with pytest.raises(ValueError, match="either a fixture"):
        CaseConfig.model_validate(
            {"id": "x", "migration": "m", "split": "dev", "runner": "jest", "reference": "none"}
        )


def test_extra_dependencies_set_and_remove() -> None:
    package: dict[str, object] = {
        "dependencies": {"@devexpress/dx-react-grid": "^2.7.0", "@material-ui/pickers": "3"},
        "devDependencies": {"jest": "27"},
    }
    notes = apply_extra_dependencies(
        package, {"@devexpress/dx-react-grid": "3.0.0", "@material-ui/pickers": "", "x": "1"}
    )
    assert package["dependencies"] == {"@devexpress/dx-react-grid": "3.0.0", "x": "1"}
    assert len(notes) == 3


def test_coverage_labels(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "src").mkdir(parents=True)
    summary = {
        "total": {},
        str(ws / "src/A.tsx"): {"functions": {"total": 2, "covered": 1}, "lines": {}},
        str(ws / "src/B.tsx"): {"functions": {"total": 3, "covered": 0}, "lines": {"covered": 4}},
        str(ws / "src/c.ts"): {"functions": {"total": 0}, "lines": {"covered": 2}},
    }
    (tmp_path / "cov").mkdir()
    (tmp_path / "cov" / "coverage-summary.json").write_text(json.dumps(summary))
    assert read_coverage(tmp_path / "cov", ws) == {
        "src/A.tsx": True,
        "src/B.tsx": False,
        "src/c.ts": True,
    }


def _test_failure(test_file: str, message: str) -> Failure:
    return Failure(source="test", file="src/X.tsx", message=message, test_file=test_file)


def test_snapshot_only_test_files() -> None:
    snap = "expect(received).toMatchSnapshot()"
    result = VerifyResult(
        commands=[],
        failures=[
            _test_failure("src/a.test.tsx", snap),
            _test_failure("src/b.test.tsx", snap),
            _test_failure("src/b.test.tsx", "expect(element).toBeVisible()"),
            _test_failure("src/c.test.tsx", "Snapshot `C > renders 1` mismatched"),
            _test_failure("src/d.test.tsx", "expect(x).toMatchInlineSnapshot()"),
        ],
    )
    assert snapshot_only_test_files(result) == ["src/a.test.tsx", "src/c.test.tsx"]
    assert not is_snapshot_failure(Failure(source="lint", file="a", message=snap))
    assert snapshot_belongs("src/__snapshots__/a.test.tsx.snap", "src/a.test.tsx")
    assert not snapshot_belongs("src/x/__snapshots__/a.test.tsx.snap", "src/a.test.tsx")


def test_reference_items_and_normalising() -> None:
    assert normalise('import { a, } from "x";\n') == normalise("import { a } from 'x'\n")
    base = {
        "src/A.tsx": "import B from '@material-ui/core/Button';\n",
        "src/fmt.tsx": "import B from '@material-ui/core/Button';\n",
        "src/util.ts": "export const x = 1;\n",
        "src/A.test.tsx": "import A from './A';\n",
    }
    ref = {
        "src/A.tsx": "import B from '@mui/material/Button';\n",
        "src/fmt.tsx": 'import B from "@material-ui/core/Button"\n',
        "src/util.ts": "export const x = 2;\n",
        "src/A.test.tsx": "import A from './A'; // v5\n",
        "yarn.lock": "",
    }
    changes = dict.fromkeys(ref, "M")
    sel = select_items(changes, base, ref.get, {"src/A.test.tsx"})
    assert sel.items == ["src/A.tsx"]
    assert sel.formatting_only == ["src/fmt.tsx"]
    assert sel.test_files == ["src/A.test.tsx"]
    assert sel.other == ["src/util.ts", "yarn.lock"]


def test_judge_cache_round_trip(tmp_path: Path) -> None:
    cache = JudgeCache(tmp_path)
    key = judge_key("a.tsx", "old", "ref", "new")
    assert key != judge_key("a.tsx", "old", "ref", "other") and cache.get(key) is None
    cache.put(key, Judgement(verdict="wrong", reason="r", out_of_scope_changes=[]), "prompt")
    got = cache.get(key)
    assert got is not None and got.verdict == "wrong"
