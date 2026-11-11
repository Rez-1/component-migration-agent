"""Karma + Jasmine (Angular's default test runner) for Verify (M7).

The repo's own ``karma.conf.js`` is never edited. Verify writes a wrapper config into
the run's log folder that loads the repo's config and then:

- runs Chrome headless with the flags a container needs (``--no-sandbox`` because the
  sandbox drops every capability), once, with no watching;
- adds a small reporter, defined inline, that writes every spec's result as JSON;
- keeps the browser's console errors, attached to the spec that was running, because
  Angular reports an unknown element or property in a test (NG0304, NG0303) only as a
  console error, not as a failure.

A failing spec is charged to the file under test: its spec file comes from the stack
trace, or else from the spec file whose top-level ``describe`` has the spec's suite
name; ``a.component.spec.ts`` is charged to ``a.component.ts``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from migrator.verify.parsers import Failure, TestTotals, clean, first_line, subject_file

KARMA_CONFIGS = ("karma.conf.js", "karma.conf.cjs", "karma.conf.mjs", "src/karma.conf.js")
# Console errors in a spec that count as failures: Angular's "not a known element /
# property" and template errors, which only log in tests.
CONSOLE_FAILURES = re.compile(r"\bNG0(300|301|303|304|8\d\d)\b|is not a known (element|property)")

WRAPPER = """\
// Written by the Migrator for one Verify run; the repo's own config is loaded unchanged.
const path = require('path');
const fs = require('fs');
const repoConfig = require(%(repo_config)s);

function MigratorJsonReporter(baseReporterDecorator) {
  baseReporterDecorator(this);
  const specs = [];
  let logs = [];
  this.onBrowserLog = (browser, log, type) => {
    if (String(type).toLowerCase() === 'error') logs.push(String(log));
  };
  this.onSpecComplete = (browser, result) => {
    specs.push({
      suite: result.suite, description: result.description, success: result.success,
      skipped: result.skipped || result.pending || false, log: result.log || [],
      console: logs,
    });
    logs = [];
  };
  this.onRunComplete = (browsers, results) => {
    fs.writeFileSync(%(out)s, JSON.stringify({
      specs, error: Boolean(results.error), exitCode: results.exitCode,
      disconnected: Boolean(results.disconnected), leftoverLogs: logs,
    }));
  };
}
MigratorJsonReporter.$inject = ['baseReporterDecorator'];

module.exports = function (config) {
  repoConfig(config);
  config.set({
    browsers: ['MigratorChromeHeadless'],
    customLaunchers: {
      MigratorChromeHeadless: {
        base: 'ChromeHeadless',
        flags: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
      },
    },
    singleRun: true,
    autoWatch: false,
    restartOnFileChange: false,
    browserNoActivityTimeout: 120000,
    captureTimeout: 120000,
    client: Object.assign({}, config.client, { captureConsole: true, clearContext: false }),
    reporters: ['migrator-json'],
    plugins: (config.plugins || []).concat([
      { 'reporter:migrator-json': ['type', MigratorJsonReporter] },
    ]),
  });
};
"""


def find_karma_config(workspace: Path) -> str | None:
    return next((name for name in KARMA_CONFIGS if (workspace / name).is_file()), None)


def write_wrapper(workspace: Path, config: str, folder: Path, label: str) -> tuple[Path, Path]:
    """The wrapper config and the JSON file its reporter will write, in ``folder``."""
    folder.mkdir(parents=True, exist_ok=True)
    wrapper = (folder / f"{label}-karma.conf.cjs").resolve()
    out = (folder / f"{label}-karma.json").resolve()
    wrapper.write_text(
        WRAPPER
        % {
            "repo_config": json.dumps(str((workspace / config).resolve())),
            "out": json.dumps(str(out)),
        },
        "utf-8",
    )
    out.unlink(missing_ok=True)
    return wrapper, out


def spec_files_for(paths: Iterable[str], exists: Callable[[str], bool]) -> list[str]:
    """The spec files that test ``paths`` (``a.component.ts`` -> ``a.component.spec.ts``;
    a template or style file counts for its component), for a narrow run."""
    found = []
    for path in paths:
        if path.endswith(".spec.ts"):
            found.append(path)
            continue
        stem = re.sub(r"\.(ts|html|scss|sass|css|less)$", "", path)
        candidate = f"{stem}.spec.ts"
        if exists(candidate):
            found.append(candidate)
    return sorted(set(found))


_STACK_SPEC = re.compile(r"((?:src|projects|apps|libs)/[\w./@-]+\.spec\.ts):(\d+)")


def _describe_index(specs: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Top-level ``describe('<name>'`` of each spec file -> the file."""
    index: dict[str, str] = {}
    pattern = re.compile(r"""^\s*describe\(\s*(['"`])(.+?)\1""", re.MULTILINE)
    for path, text in specs:
        m = pattern.search(text)
        if m and m.group(2) not in index:
            index[m.group(2)] = path
    return index


def parse_karma_json(
    text: str,
    workspace: str | None,
    exists: Callable[[str], bool | str | None],
    spec_sources: Iterable[tuple[str, str]] = (),
) -> tuple[list[Failure], TestTotals]:
    """Failures and totals from the wrapper reporter's JSON."""
    data = json.loads(text)
    describes = _describe_index(spec_sources)
    failures: list[Failure] = []
    specs = data.get("specs", [])
    passed = failed = skipped = 0
    suites: dict[str, bool] = {}
    for spec in specs:
        suite = [str(s) for s in spec.get("suite") or []]
        name = " › ".join([*suite, str(spec.get("description", ""))])
        log = clean("\n".join(str(x) for x in spec.get("log") or []), workspace)
        console = [
            clean(str(c), workspace)
            for c in spec.get("console") or []
            if CONSOLE_FAILURES.search(str(c))
        ]
        test_file = None
        line = None
        if m := _STACK_SPEC.search(log):
            test_file, line = m.group(1), int(m.group(2))
        elif suite and suite[0] in describes:
            test_file = describes[suite[0]]
        key = suite[0] if suite else name
        if spec.get("skipped"):
            skipped += 1
            continue
        ok = bool(spec.get("success")) and not console
        suites[key] = suites.get(key, True) and ok
        if ok:
            passed += 1
            continue
        failed += 1
        message = first_line(log) if log else first_line(console[0])
        failures.append(
            Failure(
                source="test",
                file=subject_file(test_file, exists) if test_file else None,
                message=message or "spec failed",
                test_file=test_file,
                test_name=name,
                line=line,
            )
        )
    if data.get("error") and not failures:
        failures.append(
            Failure(
                source="test",
                file=None,
                message="Karma reported an error outside any spec (a compile error or a "
                "crash on load; see the test log)",
                test_name="(run)",
            )
        )
    totals = TestTotals(
        suites_total=len(suites),
        suites_failed=sum(not ok for ok in suites.values()),
        tests_total=passed + failed + skipped,
        tests_passed=passed,
        tests_failed=failed,
        tests_skipped=skipped,
        snapshots_total=0,
        snapshots_unmatched=0,
        snapshots_updated=0,
        snapshots_added=0,
        snapshots_obsolete=0,
        snapshot_files_removed=0,
    )
    return failures, totals
