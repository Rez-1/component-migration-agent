"""Fakes for the graph tests: a tiny target repo, a scripted toolchain and a scripted model.

- ``make_mini_repo`` writes a four-file Material UI v4 app with three planted problems
  that mirror the fixture's traps (a theme override, ``theme.spacing`` arithmetic with a
  caller in another file, and a test that needs a theme from a Test file).
- ``FakeToolchain`` answers the commands a run executes (installs, the codemods, tsc,
  ESLint, Jest) from the workspace's *contents*, so the scripted agent's edits change
  what verify reports, exactly as they would with the real tools.
- ``ScriptedChatModel`` is a LangChain chat model that plays back scripted ``AIMessage``s
  per failing file and records every request. No test calls a real model.
"""

from __future__ import annotations

import itertools
import json
import re
import shlex
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolCall
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from pydantic import PrivateAttr

PACKAGE = {
    "name": "mini-app",
    "version": "0.1.0",
    "private": True,
    "scripts": {"typecheck": "tsc --noEmit", "lint": "eslint src", "test": "jest"},
    "dependencies": {"@material-ui/core": "4.12.4", "react": "17.0.2"},
    "devDependencies": {"jest": "29.7.0", "typescript": "4.9.5", "eslint": "8.57.1"},
}

FILES = {
    "src/theme.ts": """import { createMuiTheme } from '@material-ui/core/styles';

export const theme = createMuiTheme({
  overrides: {
    MuiButton: {
      label: { textTransform: 'none' },
    },
  },
});
""",
    "src/screens/Dashboard.tsx": """import { Paper, Theme } from '@material-ui/core';

export const cardStyle = (theme: Theme) => ({
  marginTop: theme.spacing(1) * 3,
});

export const titleMinHeight = (theme: Theme): number => theme.spacing(4) + 24;

export function Dashboard() {
  return <Paper />;
}
""",
    "src/screens/UsersTable.tsx": """import { Table, Theme } from '@material-ui/core';
import { titleMinHeight } from './Dashboard';

export const tableHeight = (theme: Theme, rows: number): number =>
  titleMinHeight(theme) + 48 * rows;

export function UsersTable() {
  return <Table />;
}
""",
    "src/screens/ProfileCard.tsx": """import { Card } from '@material-ui/core';
import { makeStyles } from '@material-ui/core/styles';

const useStyles = makeStyles((theme) => ({ root: { padding: theme.spacing(2) } }));

export function ProfileCard() {
  const classes = useStyles();
  return <Card className={classes.root} />;
}
""",
    "src/App.tsx": """import { ThemeProvider } from '@material-ui/core/styles';
import { theme } from './theme';
import { Dashboard } from './screens/Dashboard';
import { UsersTable } from './screens/UsersTable';
import { ProfileCard } from './screens/ProfileCard';

export function App() {
  return (
    <ThemeProvider theme={theme}>
      <Dashboard />
      <UsersTable />
      <ProfileCard />
    </ThemeProvider>
  );
}
""",
    "src/test-utils.tsx": """import { render } from '@testing-library/react';

export function renderComponent(ui: JSX.Element) {
  return render(ui);
}
""",
    "src/screens/__tests__/Dashboard.test.tsx": """import { Dashboard } from '../Dashboard';
import { renderComponent } from '../../test-utils';

it('renders', () => {
  renderComponent(<Dashboard />);
});
""",
    "src/screens/__tests__/ProfileCard.test.tsx": """import { ProfileCard } from '../ProfileCard';
import { renderComponent } from '../../test-utils';

it('shows the card', () => {
  renderComponent(<ProfileCard />);
});
""",
    "jest.config.js": "module.exports = { testMatch: ['<rootDir>/src/**/*.test.tsx'] };\n",
}


def make_mini_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(json.dumps(PACKAGE, indent=2) + "\n")
    (root / "package-lock.json").write_text("{}\n")
    for rel, text in FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


# --------------------------------------------------------------------------- toolchain


@dataclass
class TypeRule:
    """A type error in ``file`` while ``pattern`` is in it (only once it is on v5)."""

    file: str
    pattern: str
    code: str
    message: str


@dataclass
class TestRule:
    """A Jest test that fails while ``failing(workspace)`` is true."""

    test_file: str
    name: str
    subject: str
    failing: Callable[[Path], bool]
    message: str = "Error: failed"
    deps: list[str] = field(default_factory=list)  # other files the test reaches


def _on_v5(ws: Path, rel: str) -> bool:
    path = ws / rel
    return path.is_file() and "@mui/" in path.read_text()


TYPE_RULES = [
    TypeRule("src/theme.ts", "label: {", "TS2322", "Type '{ label: ... }' is not assignable."),
    TypeRule(
        "src/screens/Dashboard.tsx",
        "theme.spacing(1) * 3",
        "TS2362",
        "The left-hand side of an arithmetic operation must be of type 'any', 'number'.",
    ),
    TypeRule(
        "src/screens/Dashboard.tsx",
        "): number => theme.spacing(4) + 24",
        "TS2322",
        "Type 'string' is not assignable to type 'number'.",
    ),
]


def _users_table_broken(ws: Path) -> bool:
    """The regression: titleMinHeight returns a string, so UsersTable's sum is a string."""
    dash = ws / "src/screens/Dashboard.tsx"
    return dash.is_file() and "): string =>" in dash.read_text()


TEST_RULES = [
    TestRule(
        "src/screens/__tests__/ProfileCard.test.tsx",
        "shows the card",
        "src/screens/ProfileCard.tsx",
        lambda ws: (
            _on_v5(ws, "src/screens/ProfileCard.tsx")
            and "ThemeProvider" not in (ws / "src/test-utils.tsx").read_text()
        ),
        "TypeError: theme.spacing is not a function",
        deps=["src/test-utils.tsx"],
    ),
    TestRule(
        "src/screens/__tests__/Dashboard.test.tsx",
        "renders",
        "src/screens/Dashboard.tsx",
        lambda ws: False,
        deps=["src/test-utils.tsx"],
    ),
]


class FakeToolchain:
    """A ``FakeRunner`` handler for installs, codemods, tsc, ESLint and Jest."""

    def __init__(
        self,
        type_rules: Sequence[TypeRule] = TYPE_RULES,
        test_rules: Sequence[TestRule] = TEST_RULES,
    ):
        self.type_rules = list(type_rules)
        self.test_rules = list(test_rules)
        self.codemods: list[str] = []
        self.related: list[list[str]] = []

    def __call__(self, command: str, cwd: Path) -> tuple[int, str]:
        argv = shlex.split(command)
        if argv[:2] in (["node", "--version"], ["npm", "--version"]):
            return 0, "v24.0.0" if argv[0] == "node" else "11.0.0"
        if argv[:2] in (["npm", "ci"], ["npm", "install"]):
            (cwd / "node_modules").mkdir(exist_ok=True)
            return 0, "added 1 package"
        if argv[0] == "node" and len(argv) > 2 and argv[2].startswith("v5.0.0/"):
            return self.codemod(argv[2].removeprefix("v5.0.0/"), argv[3:], cwd)
        if argv[:3] == ["npm", "run", "typecheck"]:
            return self.typecheck(cwd)
        if argv[:3] == ["npm", "run", "lint"]:
            out = argv[argv.index("-o") + 1]
            Path(out).write_text("[]")
            return 0, ""
        if argv[:2] == ["npm", "test"]:
            return self.jest(argv, cwd)
        raise AssertionError(f"unexpected command: {command}")

    def codemod(self, name: str, args: list[str], cwd: Path) -> tuple[int, str]:
        self.codemods.append(name)
        files = [a for a in args if a.startswith("src/")]
        lines = []
        for rel in files:
            path = cwd / rel
            text = path.read_text()
            if name == "preset-safe":
                new = text.replace("@material-ui/core/styles", "@mui/material/styles")
                new = new.replace("@material-ui/core", "@mui/material")
                new = new.replace("createMuiTheme", "createTheme")
                if new != text:
                    path.write_text(new)
                    lines.append(f" OKK {path}")
                    continue
            lines.append(f" NOC {path}")
        return 0, "Processing files...\n" + "\n".join(lines) + "\n"

    def typecheck(self, cwd: Path) -> tuple[int, str]:
        out: list[str] = []
        for rule in self.type_rules:
            path = cwd / rule.file
            if not _on_v5(cwd, rule.file):
                continue
            for i, line in enumerate(path.read_text().splitlines(), start=1):
                if rule.pattern in line:
                    out.append(f"{rule.file}({i},3): error {rule.code}: {rule.message}")
        if _users_table_broken(cwd):
            out.append(
                "src/screens/UsersTable.tsx(5,3): error TS2322: Type 'string' is not "
                "assignable to type 'number'."
            )
        return (1 if out else 0), "\n".join(out)

    def jest(self, argv: list[str], cwd: Path) -> tuple[int, str]:
        out_file = next(a.split("=", 1)[1] for a in argv if a.startswith("--outputFile="))
        related: list[str] | None = None
        if "--findRelatedTests" in argv:
            related = argv[argv.index("--findRelatedTests") + 1 :]
            self.related.append(related)
        suites = []
        failed_tests = 0
        for rule in self.test_rules:
            if related is not None and not (
                {rule.subject, rule.test_file, *rule.deps} & set(related)
            ):
                continue
            failing = rule.failing(cwd)
            failed_tests += failing
            suites.append(
                {
                    "name": str(cwd / rule.test_file),
                    "status": "failed" if failing else "passed",
                    "message": "",
                    "assertionResults": [
                        {
                            "status": "failed" if failing else "passed",
                            "title": rule.name,
                            "ancestorTitles": [],
                            "failureMessages": [rule.message] if failing else [],
                            "location": None,
                        }
                    ],
                }
            )
        report = {
            "numTotalTestSuites": len(suites),
            "numFailedTestSuites": sum(s["status"] == "failed" for s in suites),
            "numTotalTests": len(suites),
            "numPassedTests": len(suites) - failed_tests,
            "numFailedTests": failed_tests,
            "numPendingTests": 0,
            "numTodoTests": 0,
            "snapshot": {},
            "testResults": suites,
        }
        Path(out_file).write_text(json.dumps(report))
        return (1 if failed_tests else 0), ""


# --------------------------------------------------------------------------- the model


_IDS = itertools.count(1)


def call(name: str, **args: Any) -> ToolCall:
    return ToolCall(name=name, args=args, id=f"toolu_{next(_IDS):04d}")


def ai(
    *calls: ToolCall,
    text: str = "",
    model: str = "claude-opus-5-5",
    input_tokens: int = 1000,
    output_tokens: int = 100,
    cache_read: int = 0,
    cache_write: int = 0,
    stop_reason: str | None = None,
) -> AIMessage:
    """A scripted reply, with usage as langchain-anthropic reports it (cache folded in)."""
    details: dict[str, int] = {"cache_read": cache_read, "cache_creation": 0}
    if cache_write:
        details["ephemeral_5m_input_tokens"] = cache_write
        details["ephemeral_1h_input_tokens"] = 0
    total_in = input_tokens + cache_read + cache_write
    return AIMessage(
        content=text,
        tool_calls=list(calls),
        usage_metadata={
            "input_tokens": total_in,
            "output_tokens": output_tokens,
            "total_tokens": total_in + output_tokens,
            "input_token_details": details,
        },
        response_metadata={
            "model_name": model,
            "stop_reason": stop_reason or ("tool_use" if calls else "end_turn"),
        },
    )


_FILE = re.compile(r"## Failing file: `([^`]+)`")


class ScriptedChatModel(BaseChatModel):
    """Plays back scripted replies per failing file; records every request it gets."""

    script: dict[str, list[AIMessage]]
    model_id: str = "claude-opus-5-5"
    _queues: dict[str, Iterator[AIMessage]] = PrivateAttr(default_factory=dict)
    _requests: list[dict[str, Any]] = PrivateAttr(default_factory=list)
    _bound_tools: list[Any] = PrivateAttr(default_factory=list)
    _bind_kwargs: dict[str, Any] = PrivateAttr(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self._requests

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable[Any, AIMessage]:
        self._bound_tools = list(tools)
        self._bind_kwargs = dict(kwargs)
        return self.bind(bound_tool_names=[getattr(t, "name", str(t)) for t in tools])

    @property
    def bind_kwargs(self) -> dict[str, Any]:
        return self._bind_kwargs

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        first = next((m for m in messages if m.type == "human"), None)
        match = _FILE.search(str(first.content)) if first is not None else None
        path = match.group(1) if match else "?"
        self._requests.append({"file": path, "messages": list(messages), "kwargs": kwargs})
        if path not in self._queues:
            self._queues[path] = iter(self.script.get(path, []))
        reply = next(self._queues[path], None)
        if reply is None:
            reply = ai(call("hand_off", reason="script ran out"), model=self.model_id)
        return ChatResult(generations=[ChatGeneration(message=reply)])


def factory_for(model: ScriptedChatModel) -> Callable[[str, str | None, int], BaseChatModel]:
    def make(model_id: str, effort: str | None, max_tokens: int) -> BaseChatModel:
        model.model_id = model_id
        return model

    return make
