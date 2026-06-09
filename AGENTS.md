## BigBrain

Before starting meaningful work, search Rodrigo's BigBrain knowledge base for relevant context.

BigBrain location:
- Windows: `C:\Users\rodri\source\BigBrain`
- WSL/Linux: `/mnt/c/Users/rodri/source/BigBrain`

Use BigBrain to understand active project decisions, architecture, assignment requirements,
known bugs, dataset notes, tooling preferences, deployment details, previous prompts, and
handoffs. Do not rely only on the current chat when BigBrain may contain relevant context.

Update BigBrain when the task produces durable knowledge, such as a new project decision,
changed architecture, debugging discovery, useful workflow, assignment interpretation,
dataset finding, reusable prompt, TODO, or open question. Keep notes in Markdown, separate
facts/decisions/TODOs/open questions where useful, and avoid raw logs or unverified
assumptions.

At the end of the task, briefly report which BigBrain files were consulted, which were
updated, and any unresolved questions or TODOs.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- On Rodrigo's Windows machine, if `graphify` is not on PATH, use `C:\Users\rodri\.local\bin\graphify.exe`.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
