"""A Run as one checkpointed LangGraph graph (ticket #11).

``build.py`` wires the nodes in run order; each node lives with its stage in
``stages/``, takes a ``RunContext`` (``context.py``) and the ``RunState``
(``state.py``), and returns the keys it changed. ``files.py`` is the run folder.
"""
