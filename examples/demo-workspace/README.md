# Checkout Service

This small workspace demonstrates Kinekt retrieval without relying on Kinekt's own source tree.

The service creates payment requests through a gateway. Idempotency keys are mandatory so callers can safely
retry a timed-out request without creating a duplicate charge.
