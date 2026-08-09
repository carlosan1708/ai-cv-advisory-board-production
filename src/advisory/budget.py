from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from threading import RLock
from typing import Protocol
from uuid import uuid4


class BudgetExceededError(RuntimeError):
    pass


@dataclass(frozen=True)
class Pricing:
    model: str = "gemini-3.5-flash-lite"
    version: str = "2026-07-21"
    input_micro_usd_per_million: int = 300_000
    output_micro_usd_per_million: int = 2_500_000

    def cost(self, input_tokens: int, output_tokens: int) -> int:
        input_cost = ceil(input_tokens * self.input_micro_usd_per_million / 1_000_000)
        output_cost = ceil(output_tokens * self.output_micro_usd_per_million / 1_000_000)
        return input_cost + output_cost


@dataclass(frozen=True)
class Reservation:
    id: str
    owner_id: str
    month: str
    amount_micro_usd: int


@dataclass(frozen=True)
class BudgetSnapshot:
    limit_micro_usd: int
    used_micro_usd: int
    reserved_micro_usd: int

    @property
    def remaining_micro_usd(self) -> int:
        return max(0, self.limit_micro_usd - self.used_micro_usd - self.reserved_micro_usd)


class BudgetLedger(Protocol):
    def snapshot(self, owner_id: str, month: str | None = None) -> BudgetSnapshot: ...
    def reserve(self, owner_id: str, amount_micro_usd: int, month: str | None = None) -> Reservation: ...
    def reconcile(self, reservation: Reservation, actual_micro_usd: int) -> BudgetSnapshot: ...
    def release(self, reservation: Reservation) -> BudgetSnapshot: ...


class InMemoryBudgetLedger:
    """Atomic reservation ledger; the Firestore adapter follows this contract."""

    def __init__(self, monthly_limit_micro_usd: int = 5_000_000) -> None:
        self.monthly_limit_micro_usd = monthly_limit_micro_usd
        self._used: dict[tuple[str, str], int] = {}
        self._reservations: dict[str, Reservation] = {}
        self._lock = RLock()

    @staticmethod
    def month(now: datetime | None = None) -> str:
        return (now or datetime.now(UTC)).strftime("%Y-%m")

    def snapshot(self, owner_id: str, month: str | None = None) -> BudgetSnapshot:
        active_month = month or self.month()
        with self._lock:
            used = self._used.get((owner_id, active_month), 0)
            reserved = sum(
                item.amount_micro_usd
                for item in self._reservations.values()
                if item.owner_id == owner_id and item.month == active_month
            )
        return BudgetSnapshot(self.monthly_limit_micro_usd, used, reserved)

    def reserve(self, owner_id: str, amount_micro_usd: int, month: str | None = None) -> Reservation:
        if amount_micro_usd <= 0:
            raise ValueError("Reservation amount must be positive")
        active_month = month or self.month()
        with self._lock:
            snapshot = self.snapshot(owner_id, active_month)
            if amount_micro_usd > snapshot.remaining_micro_usd:
                raise BudgetExceededError("Monthly AI budget reached")
            reservation = Reservation(uuid4().hex, owner_id, active_month, amount_micro_usd)
            self._reservations[reservation.id] = reservation
            return reservation

    def reconcile(self, reservation: Reservation, actual_micro_usd: int) -> BudgetSnapshot:
        if actual_micro_usd < 0 or actual_micro_usd > reservation.amount_micro_usd:
            raise ValueError("Actual cost must fit within the reservation")
        with self._lock:
            active = self._reservations.pop(reservation.id, None)
            if active != reservation:
                raise ValueError("Reservation is not active")
            key = (reservation.owner_id, reservation.month)
            self._used[key] = self._used.get(key, 0) + actual_micro_usd
            return self.snapshot(reservation.owner_id, reservation.month)

    def release(self, reservation: Reservation) -> BudgetSnapshot:
        with self._lock:
            active = self._reservations.pop(reservation.id, None)
            if active != reservation:
                raise ValueError("Reservation is not active")
            return self.snapshot(reservation.owner_id, reservation.month)
