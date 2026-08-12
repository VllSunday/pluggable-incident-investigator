# Retry Service — Incident Investigator Fixture

This repository intentionally contains an off-by-one regression in `retry_delay`.
The CI failure is the ground truth input for the Incident Investigator remediation demo.

Expected autonomous fix:

```python
return min(base * (2 ** (attempt - 1)), maximum)
```

The investigator must reproduce the failure, apply only the source patch, run the
allowlisted tests and linter in its network-isolated sandbox, pause for human approval,
and create a draft pull request.
