"""A Run as one checkpointed LangGraph graph (ticket #11, split into this package in #27).

- ``build.py``: the wiring, nodes and edges in run order.
- ``state.py``: ``RunState``, and which node writes each key.
- ``context.py``: ``RunContext`` (the deps, the run folder, and what nodes rebuild
  from the state) and ``RunDeps``.
- ``files.py``: ``RunFiles``, the run folder.
- ``evidence.py``: a finished run's Scoring evidence.
- ``stages/``: the nodes, one module per stage.

``migrator.pipeline`` starts, drives and resumes the graph.
"""
