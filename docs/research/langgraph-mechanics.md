# LangGraph mechanics: interrupt resume, checkpointer, LangSmith and token usage

Research for [Rez-1/component-migration-agent#3](https://github.com/Rez-1/component-migration-agent/issues/3). Checked 2026-11-09 against PyPI's JSON API, the docs at docs.langchain.com (raw `.md` pages), the langchain.com pricing page, and source files on GitHub (`langchain-ai/langgraph` `main`, `langchain-ai/langchain` `master`).

## Recommendation

Compile the graph with **`SqliteSaver`** from `langgraph-checkpoint-sqlite`, pointed at a file inside the project being migrated (for example `.mui-migrate/checkpoints.sqlite`). Use **one `thread_id` per migration run** and write it to disk next to the database, so that `mui-migrate resume` can reopen the same thread and call `graph.invoke(Command(resume=...), config)`. Eval/CI runs can use `InMemorySaver` (`langgraph.checkpoint.memory`): they auto-answer "hand off" in the same process and never need to survive a restart. Keep the code before `interrupt()` in the human-review node free of side effects, and keep LLM calls out of it. Read token usage from `AIMessage.usage_metadata` on every call, through our own callback or wrapper. LangChain's Anthropic integration already folds cached tokens into `input_tokens`, so subtract them before pricing.

## 1. `interrupt()` and `Command(resume=...)`

Source: [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts.md), [Checkpointers / threads](https://docs.langchain.com/oss/python/langgraph/checkpointers.md).

**Requirements:** a checkpointer passed to `compile(checkpointer=...)`, a `thread_id` in `config["configurable"]`, and a call to `interrupt(payload)` inside a node. The payload must be JSON-serialisable.

**Within one process**

```python
from langgraph.types import interrupt, Command

def human_review(state):
    decision = interrupt({"file": state["path"], "diff": state["diff"]})  # pauses here
    ...  # runs only after resume; `decision` is the resume value

config = {"configurable": {"thread_id": run_id}}
result = graph.invoke(inputs, config)
if "__interrupt__" in result:            # tuple of Interrupt(value=..., id=...)
    answer = prompt_user(result["__interrupt__"][0].value)
    result = graph.invoke(Command(resume=answer), config)
```

- `invoke()` returns pending interrupts under `result["__interrupt__"]`. The docs now *recommend* `graph.stream_events(..., version="v3")`, which exposes `stream.interrupted`, `stream.interrupts` and `stream.output`. Plain `invoke()` is documented as still supported.
- `Command(resume=...)` is the only `Command` form meant as graph input.
- **Several pending interrupts** (parallel branches): resume them all at once with `Command(resume={intr.id: value, ...})`.
- **Typed answers** (`langgraph>=1.2.12`): `interrupt(payload, response_schema=Decision)` takes a Pydantic model, TypedDict or dataclass. It validates the resume value (raising `pydantic.ValidationError`) and returns the parsed object. This suits `accept | edit | hand_off`.

**Across a process restart** (the user quits and reruns the CLI later)

LangGraph has no separate resume API. Resuming works because the checkpointer keeps the state, keyed by `thread_id`. The checkpointers page says the checkpointer "uses `thread_id` as the primary key", and that without it the graph cannot "resume execution after an interrupt". So the new process needs to:

1. Open the **same SQLite file** and compile the **same graph**. Node names must match, because the checkpoint stores the next task by node name.
2. Use the **same `thread_id`**, which the CLI has to store itself (for example in `.mui-migrate/run.json`). To list threads, `checkpointer.list(None)` returns one row per checkpoint, so group by `thread_id`. It must be `None`, not `{}`: `SqliteSaver` raises if the config is non-`None` and has no `thread_id`.
3. Find out what is pending: `snap = graph.get_state(config)`. `snap.next` lists the nodes due to run, and `snap.tasks[i].interrupts` holds the pending `Interrupt` objects with their `.value` and `.id`. Re-show those to the user.
4. Call `graph.invoke(Command(resume=answer), config)`.

The checkpointers page gives the rules for continuing a thread:

| Goal | Call |
|---|---|
| Answer an interrupt | `graph.invoke(Command(resume=answer), config)`. The interrupted node starts again from its beginning. |
| Continue after a crash or error | `graph.invoke(None, config)` retries unfinished work from the latest checkpoint. |
| New input on the same thread | `graph.invoke(input, config)` applies the input through reducers and starts from the entry point. **It does not resume, and it does not clear state.** |
| Fresh start | Use a new `thread_id`. |

**Gotchas** ([Rules of interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts.md#rules-of-interrupts))

- **The node re-runs from its first line on resume.** Everything before `interrupt()` runs again: file writes, LLM calls, log lines, cost counting. Put side effects after `interrupt()` or in a separate node, and make anything that has to run before it idempotent. For us: compute the diff and payload in an upstream node and store them in state. The review node should contain only `interrupt()` followed by applying the decision.
- `interrupt()` pauses by **raising an exception**. A bare `try/except` (or `except Exception`) around it swallows the pause.
- Within a node, interrupts are matched to resume values **by position**. Don't call `interrupt()` conditionally or in a non-deterministic order. Don't loop over it with `while True` either: each resume replays all earlier iterations. To re-prompt, store the question in state and loop back with a conditional edge.
- When a file is handed off, review is per file. One interrupt per graph step that targets one file keeps this simple. If review runs as parallel per-file branches (`Send`), several interrupts can be pending at once, and they have to be resumed by id.
- Durability: checkpoints are written per super-step. The `durability` argument is `"exit"`, `"async"` or `"sync"`. `"exit"` writes only when the run exits, which includes exiting on an interrupt. A crash in the middle of a run then loses all progress. For a long repair loop on a laptop, pass `durability="sync"` (or keep the default async) so that Ctrl-C or a crash doesn't throw away finished files. Even if a crash arrives before the first checkpoint, `invoke(None, config)` raises `EmptyInputError`. ([Durability modes](https://docs.langchain.com/oss/python/langgraph/checkpointers.md#durability-modes))
- When a node fails, the writes of the other nodes that succeeded in the same super-step are kept as "pending writes", so a resume does not re-run them.

## 2. Which checkpointer

Source: [Checkpointer libraries](https://docs.langchain.com/oss/python/langgraph/checkpointers.md#checkpointer-libraries), [integrations table](https://docs.langchain.com/oss/python/integrations/checkpointers/index.md), [`checkpoint-sqlite` README](https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-sqlite), [`sqlite/__init__.py`](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py).

| Saver | Package | Import | Use |
|---|---|---|---|
| `InMemorySaver` | `langgraph-checkpoint` (installed with `langgraph`) | `langgraph.checkpoint.memory` | "for experimentation". Lost when the process exits. **Fine for eval/CI**: interrupts are auto-answered in the same process. |
| `SqliteSaver` | `langgraph-checkpoint-sqlite` (separate install) | `langgraph.checkpoint.sqlite` | Sync only. "Ideal for experimentation and local workflows." **Pick this one for the CLI.** |
| `AsyncSqliteSaver` | same package (uses `aiosqlite`) | `langgraph.checkpoint.sqlite.aio` | Only needed if the graph runs with `ainvoke`/`astream`. |

Usage:

```python
from langgraph.checkpoint.sqlite import SqliteSaver

with SqliteSaver.from_conn_string(str(project / ".mui-migrate" / "checkpoints.sqlite")) as cp:
    graph = builder.compile(checkpointer=cp)
    ...
# or: SqliteSaver(sqlite3.connect(path, check_same_thread=False))
```

- `from_conn_string` is a **context manager**. It opens the connection with `check_same_thread=False` (the saver guards access with a lock) and closes it on exit. `setup()` creates the tables lazily and switches on `PRAGMA journal_mode=WAL`.
- Calling `SqliteSaver`'s async methods raises an error pointing to `AsyncSqliteSaver`. Make one choice for the whole CLI: sync `invoke` with `SqliteSaver`, or async with `AsyncSqliteSaver`.
- The docstring describes the class as "meant for lightweight, synchronous use cases (demos and small projects)", and says it "does not scale to multiple threads". That is fine for a single-user CLI.
- **Where the file lives:** the library sets no default. We choose it. Putting it inside the target repo, gitignored, ties the run to that codebase. A user cache directory would be the alternative.
- **Security:** the README asks for `LANGGRAPH_STRICT_MSGPACK=true` or an explicit `allowed_msgpack_modules`, because the default serializer will deserialise any Python type it finds in a checkpoint. Optional encryption is available through `EncryptedSerializer.from_pycryptodome_aes()` (key in `LANGGRAPH_AES_KEY`). Neither is needed for a local file.
- State must serialise with `JsonPlusSerializer` (msgpack/JSON). Keep it to plain dicts, strings, Pydantic models and LangChain messages. Pass `pickle_fallback=True` only if that becomes necessary.
- Checkpoints pile up: one per super-step, each holding every channel value in full. Big file contents in state make the database grow fast. Store paths and diffs, not whole files, or consider `DeltaChannel`.

## 3. LangSmith tracing

Sources: [LangGraph observability](https://docs.langchain.com/oss/python/langgraph/observability.md), [Trace with LangGraph](https://docs.langchain.com/langsmith/trace-with-langgraph.md), [Trace with LangChain](https://docs.langchain.com/langsmith/trace-with-langchain.md), [Observability concepts](https://docs.langchain.com/langsmith/observability-concepts.md), [Billing](https://docs.langchain.com/langsmith/billing.md), [Usage & billing](https://docs.langchain.com/langsmith/usage-and-billing.md), [Pricing](https://www.langchain.com/pricing).

**Switching it on** (environment variables only; LangGraph and LangChain trace with no code changes):

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=...
# New "agent-based" workspaces:
export LANGSMITH_AGENT_ID=<agent-id>        # register the agent once in the UI
export LANGSMITH_AGENT_ENVIRONMENT=local    # one of Production/Staging/Development/Local
# Older "project-based" workspaces and self-hosted LangSmith instead use:
export LANGSMITH_PROJECT=mui-migrate
# Non-US region, e.g. EU:
export LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
# Only when the API key covers several workspaces:
export LANGSMITH_WORKSPACE_ID=...
```

`ls.tracing_context(enabled=True|False, ...)` turns tracing on or off for a block of code.

**What gets recorded:** every unit of work is a *run* (similar to an OTel span): each graph node, each LLM call, each tool call. All the runs from one `invoke` form a *trace*, with inputs, outputs, errors, timing and, for LLM runs, token counts and cost. Traces that share a `thread_id` metadata value are grouped into a *thread*. A trace holds at most 25,000 runs. LangSmith **computes LLM cost automatically** for LangChain model calls, from token counts and its model price table ([cost tracking](https://docs.langchain.com/langsmith/cost-tracking.md)). That gives us a cross-check against our own count, but not a hard cap.

**Every `invoke()` is a separate trace.** The first run and each resume produce separate traces. LangGraph's `configurable.thread_id` is not the same thing as LangSmith's `thread_id` metadata key. To group a migration run in the UI, also pass `metadata={"thread_id": run_id}`.

**Tagging runs:**

```python
graph.invoke(inputs, config={
    "configurable": {"thread_id": run_id},
    "run_name": "mui-migrate",
    "tags": ["eval", "exp:baseline-v1"],
    "metadata": {"experiment": "baseline-v1", "case_id": case.id, "thread_id": run_id,
                 "model": "claude-...", "git_sha": sha},
})
```

Or wrap the call in `with ls.tracing_context(tags=[...], metadata={...}):`. Inside `@traceable` code, `ls.get_current_run_tree().metadata[...]` works too. Tags and metadata can be filtered in the UI. For formal experiments over a LangSmith dataset, `langsmith.evaluate(target, data=..., evaluators=..., experiment_prefix="baseline-v1", metadata={...}, max_concurrency=4)` names the experiment and links each example's run to it ([evaluate guide](https://docs.langchain.com/langsmith/evaluate-llm-application.md)).

**Flushing in a short-lived CLI:** LangChain uploads traces from a background thread, so the process can exit before they are sent. Call `langchain_core.tracers.langchain.wait_for_all_tracers()` in a `finally` before exit, or set `LANGCHAIN_CALLBACKS_BACKGROUND=false`.

**Free tier (Developer plan):** 1 seat. 5k base traces/month are included. A personal organisation **without a card is hard-limited to 5,000 traces/month** (rate-limited, not charged). With a card on file, extra traces are pay-as-you-go. The pricing calculator shows 0.005 LSU per extra trace at $1/LSU, about $5 per 1k; that figure comes from the page's JS, not from a documented rate. Base retention is 14 days; extended is 180 days (from 2026-09-14) and costs extra. Ingest limit: 50,000 events/hour without a card, 250,000 with one. An event is a run create or update. Plus costs $39/seat/month and includes 10k traces. **For the €20 cap, don't add a card**, so tracing can never cost money.

## 4. Token usage per LLM call and cost

Sources: [Messages → Token usage](https://docs.langchain.com/oss/python/langchain/messages.md), [Models → Token usage](https://docs.langchain.com/oss/python/langchain/models.md), [`langchain_core/messages/ai.py`](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/messages/ai.py), [`langchain_core/callbacks/usage.py`](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/callbacks/usage.py), [`langchain_anthropic/chat_models.py` `_create_usage_metadata`](https://github.com/langchain-ai/langchain/blob/master/libs/partners/anthropic/langchain_anthropic/chat_models.py).

- **Per call:** `msg.usage_metadata` on the returned `AIMessage` is a `UsageMetadata` TypedDict: `input_tokens`, `output_tokens`, `total_tokens`, `input_token_details` (`cache_read`, `cache_creation`, `audio`, plus provider-specific keys) and `output_token_details` (`reasoning`, ...). `msg.response_metadata["model_name"]` gives the model to price.
- **Aggregated:** `with get_usage_metadata_callback() as cb:` (or `UsageMetadataCallbackHandler()` passed in `config["callbacks"]`) collects `cb.usage_metadata`, a dict **keyed by model name** that sums usage with `add_usage`. It is thread-safe and propagates through context vars. It gives **totals, not one row per call**. For a per-call cost ledger (and to check the budget before the next call), write a small `BaseCallbackHandler.on_llm_end` modelled on it that records one row per call, or read `usage_metadata` straight off each `AIMessage` in the repair node.
- **Anthropic specifics (langchain-anthropic):**
  - Anthropic's own `input_tokens` *excludes* cached tokens. LangChain **adds them back**: `usage_metadata.input_tokens = raw_input + cache_read + cache_creation`. Uncached input is `input_tokens - cache_read - cache_creation_total`.
  - `input_token_details.cache_read` maps to `cache_read_input_tokens`. `cache_creation` maps to `cache_creation_input_tokens`.
  - If the API returns the TTL breakdown, LangChain copies `ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens` into `input_token_details` and **sets `cache_creation` to 0** so the tokens aren't counted twice. Cost code must use `ephemeral_5m + ephemeral_1h` when they are present and `cache_creation` otherwise. The 5-minute and 1-hour writes have different prices.
  - `output_token_details.reasoning` holds thinking tokens. They are **part of** `output_tokens`, not extra.
- Cost formula: `uncached_in × p_in + cache_read × p_cache_read + cache_5m × p_write_5m + cache_1h × p_write_1h + output × p_out`. Keep the per-model price table in our config, and check current prices before we fix it.
- Streaming: Anthropic returns usage on stream chunks without extra settings. OpenAI chat completions needs opt-in (`stream_usage`), which only matters if we add OpenAI later.
- The usage counts only exist after the response arrives. To enforce the €20 cap *before* a call, estimate from `max_tokens` and the prompt size, then reconcile with the actual figures afterwards.

## 5. Packages, versions, Python

From PyPI JSON on 2026-11-09:

| Package | Latest | Released | `requires_python` | Notable pins |
|---|---|---|---|---|
| `langgraph` | **1.2.20** | 2026-11-05 | >=3.10 | `langchain-core>=1.4.7,<2`, `langgraph-checkpoint>=4.3.0,<5`, `langgraph-prebuilt>=1.1,<1.2`, `langgraph-sdk>=0.4.6,<0.5` |
| `langgraph-checkpoint` | 4.3.1 | — | >=3.10 | `ormsgpack>=1.12` |
| `langgraph-checkpoint-sqlite` | **3.1.3** | 2026-10-30 | >=3.10 | `aiosqlite>=0.20`, `langgraph-checkpoint>=4.3.1,<5`, `sqlite-vec>=0.1.6` |
| `langsmith` | **0.14.17** | 2026-11-02 | >=3.10 | `httpx2`, `orjson`, `pydantic>=2,<3` |
| `langchain-core` | **1.7.6** | 2026-11-05 | >=3.10,<4.0 | `langsmith>=0.14.9,<1.0` |
| `langchain-anthropic` | 1.7.10 | — | >=3.10,<4.0 | `anthropic>=0.120.0`, `langchain-core>=1.7.5,<2` |

**Minimum Python: 3.10** for the whole stack. Suggested constraints: `langgraph>=1.2.12,<2` (for `response_schema`), `langgraph-checkpoint-sqlite>=3.1,<4`, `langchain-anthropic>=1.7,<2`, `langsmith>=0.14,<1`. `langchain-core` comes in transitively.

## Surprises and risks

- **The SQLite package's major version (3.x) differs from the checkpoint base (4.x) and from langgraph (1.x).** Pin each one separately.
- **The docs now steer toward `stream_events(version="v3")`.** `invoke()` + `__interrupt__` still works, but newer examples won't show it.
- **LangSmith has moved to "agent-based workspaces"** (`LANGSMITH_AGENT_ID` / `LANGSMITH_AGENT_ENVIRONMENT`). Older guides only mention `LANGSMITH_PROJECT`, and which variables apply depends on how the user's workspace is set up. Document both.
- **LangChain's `input_tokens` for Anthropic already includes cache tokens**, and `cache_creation` can be 0 while the `ephemeral_*` keys hold the real number. A naive formula will overcount input or undercount cache writes.
- `get_usage_metadata_callback` aggregates by model, so on its own it cannot produce a per-call ledger.
- Re-running the node before `interrupt()` is the biggest trap. Any LLM call left in the review node is paid for twice on every resume.
- The checkpoint database can be read without the CLI and contains file contents and diffs. Gitignore it.
