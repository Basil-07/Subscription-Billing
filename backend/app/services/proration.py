from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

def calculate_proration(
    old_plan_price: int,
    new_plan_price: int,
    cycle_start: datetime,
    cycle_end: datetime,
    effective_at: datetime,
) -> tuple[int, int, int]:
    """
    Computes proration based on the exact effective timestamp.
    Formula:
        cycle_length = cycle_end - cycle_start
        remaining_time = max(0, cycle_end - effective_at)
        credit_old = old_plan_price * (remaining_time / cycle_length)
        charge_new = new_plan_price * (remaining_time / cycle_length)
        net_amount = charge_new - credit_old

    Returns:
        tuple (credit_cents, charge_cents, net_cents)
        where fractional cents are rounded using ROUND_HALF_UP at the final step.
    """
    # Ensure they are timezone-aware or comparable
    if cycle_start.tzinfo is not None and effective_at.tzinfo is None:
        effective_at = effective_at.replace(tzinfo=cycle_start.tzinfo)
    elif cycle_start.tzinfo is None and effective_at.tzinfo is not None:
        effective_at = effective_at.replace(tzinfo=None)

    # Clamp effective_at within cycle boundaries
    if effective_at < cycle_start:
        effective_at = cycle_start
    if effective_at > cycle_end:
        effective_at = cycle_end

    cycle_length_sec = Decimal((cycle_end - cycle_start).total_seconds())
    if cycle_length_sec <= 0:
        return 0, 0, 0

    remaining_sec = Decimal(max(0.0, (cycle_end - effective_at).total_seconds()))

    credit_old = Decimal(old_plan_price) * (remaining_sec / cycle_length_sec)
    charge_new = Decimal(new_plan_price) * (remaining_sec / cycle_length_sec)
    net_amount = charge_new - credit_old

    # Final rounding to integer cents
    credit_cents = int(credit_old.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    charge_cents = int(charge_new.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    net_cents = int(net_amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    return credit_cents, charge_cents, net_cents
