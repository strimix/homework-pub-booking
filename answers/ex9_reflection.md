# Ex9 — Reflection

## Q1 — Planner handoff decision

### Your answer

In session `sess_6cce0b9df548` (Ex7 handoff bridge, offline run), round 1 ends
with `handoff_to_structured` after `venue_search` for twelve guests near
Haymarket. The scripted planner subgoal in `tk_8ab07eab/raw_output.json`
describes committing the booking under policy rules; the executor never
plans a separate “talk to manager” subgoal because the task text names
deterministic caps (party size, deposit) that belong in the structured half.

The trace shows the bridge moving state `loop → structured` on line 6 of
`logs/trace.jsonl`, then `structured → loop` on line 7 with
`rejection_reason: party_too_large`. Round 2’s planner call (line 9) receives
the rejection text explicitly (“Produce an alternative”), which is why the
second handoff targets `The Royal Oak` with `party_size: 6` and succeeds.

The signal is therefore twofold: subgoal wording that references policy/rules,
and the availability of `handoff_to_structured` in the tool registry. Without
the bridge archiving `ipc/handoff_to_structured.json` after a reject, the loop
half would not get a clean retry path.

### Citation

- `sessions/sess_6cce0b9df548/logs/trace.jsonl` lines 5–14
- `sessions/sess_6cce0b9df548/logs/tickets/tk_8ab07eab/raw_output.json`

---

## Q2 — Dataflow integrity catch

### Your answer

While testing Ex5 in session `sess_48405dd66ad6`, `verify_dataflow` uses
`data-testid` values from `workspace/flyer.html`. The offline scripted run
logs `calculate_cost` with `total_gbp: 556` and `deposit_required_gbp: 71`
(trace line 5), matching the catering formula (subtotal £324, 10% service,
£200 minimum spend at Haymarket Tap).

If the flyer had still advertised £540 / £0 from an older template while the
tool log showed £556 / £71, the integrity check would flag `£540` and `£0` as
unverified because they never appeared in `_TOOL_CALL_LOG`. That is exactly the
failure mode the grader plants with £9999: plausible prose that does not trace
to tool output. Manual review often accepts round numbers; the check does not.

To reproduce: run `make ex5`, edit `workspace/flyer.html` so
`data-testid="total"` reads £9999, call `verify_dataflow` on the file — it
should return `ok=False` with `unverified_facts` containing `9999`.

### Citation

- `sessions/sess_48405dd66ad6/logs/trace.jsonl` line 5–6
- `sessions/sess_48405dd66ad6/workspace/flyer.html`
- `starter/edinburgh_research/integrity.py` — `verify_dataflow`

---

## Q3 — Removing one framework primitive

### Your answer

The first production failure I would expect is **stale handoff state**: a
structured-half rejection written to `ipc/handoff_to_structured.json` while
the loop half still believes it may complete locally, so the next planner
turn contradicts the on-disk handoff.

The sovereign-agent primitive that surfaces this is the **session directory
with append-only `logs/trace.jsonl` plus IPC files under `ipc/`**. Operators
can diff `session.state_changed` events (as in Ex7 round 1 line 7) against
whatever is still in `ipc/`; without a single session folder per run, those
signals would be scattered across process logs and impossible to reconcile
under load.

Concrete failure mode: customer sees “booking confirmed” in the flyer while
Rasa rejected party size twelve; support opens `sessions/<id>/` and finds
`handoff_to_structured.json` still present with `party_size: 12` after the
bridge should have archived it — a **fail-closed IPC rule** violation, not an
LLM typo.

### Citation

- `sessions/sess_6cce0b9df548/logs/trace.jsonl` lines 6–7
- `sessions/sess_6cce0b9df548/ipc/handoff_to_structured.json`
- Course slides: session directories as the audit backbone (Week 5)
