"""Pre-action guard: judge a coding agent's proposed edit before it runs.

The Failproof AI policy in `live/failproof/` calls `python -m greenwash.guard` with the hook
payload on stdin. The guard reuses the PR scanner's checks, so both ask the same questions.
"""
