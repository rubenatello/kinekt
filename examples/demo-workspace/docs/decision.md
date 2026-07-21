# ADR: Retry-safe payment creation

Payment creation accepts an idempotency key supplied by the caller. The key must remain stable across retries.
The gateway rejects an empty key before performing network or persistence work.

This keeps retry behavior explicit and prevents duplicate charges after ambiguous timeouts.
