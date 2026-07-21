from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PaymentRequest:
    amount: Decimal
    currency: str
    idempotency_key: str


class PaymentGateway:
    def create_charge(self, request: PaymentRequest) -> str:
        if not request.idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        return f"charge:{request.idempotency_key}"
