# Ex5 — Edinburgh research loop scenario

## Your answer

The planner produced two subgoals (research near Haymarket, then write an HTML
flyer). In offline mode the executor called `venue_search`, `get_weather`, and
`calculate_cost` in one turn (all `parallel_safe=True`), then `generate_flyer`
(not parallel-safe), then `complete_task`.

For `haymarket_tap`, party 6, three hours, `bar_snacks`, `calculate_cost`
returns subtotal £324, service £32, venue fees £200, total £556, deposit £71
(deposit computed on food subtotal + service only). The flyer is HTML with
`data-testid` on every fact so `verify_dataflow` can match values in
`_TOOL_CALL_LOG`.

`verify_dataflow` also handles markdown-style probes (grader plants like
£9999 or fictitious venue names) via labeled lines and money/temperature
extractors.

## Citations

- `sessions/sess_48405dd66ad6/logs/trace.jsonl`
- `sessions/sess_48405dd66ad6/workspace/flyer.html`
