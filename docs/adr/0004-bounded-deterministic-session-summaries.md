# ADR 0004: Compact Sessions With Bounded Deterministic Summaries

- Status: Accepted
- Date: 2026-07-21

## Context

Passing an entire chat session into retrieval rewriting or local generation grows without bound, increases model
latency, and makes behavior difficult to reproduce. Keeping only the newest messages loses older constraints and
decisions that may still matter.

## Decision

Persist one incremental summary per session with a cursor through the compacted message sequence. Compact only
messages older than the configured recent window, cap each normalized message contribution, and retain only the
tail of a fixed-size 4,000-character summary. Supply both that summary and bounded recent raw turns to retrieval
and generation. Expose the summary and retrieval query in the agent-turn result.

The initial summary is deterministic formatting, not model-generated prose. A future learned summarizer must be an
explicit optional mode with the same storage and context budgets.

## Consequences

- Long sessions have a fixed context ceiling and repeatable behavior.
- Older decisions remain available after raw turns leave the recent window.
- Incremental sequence tracking makes repeated compaction idempotent.
- Tail retention can discard the oldest summarized facts; improving salience requires evaluation before adding a
  model or a more complex memory policy.
