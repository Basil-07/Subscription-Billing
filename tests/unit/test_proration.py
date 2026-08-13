from datetime import datetime, timedelta, timezone
from app.services.proration import calculate_proration

def test_proration_midpoint_upgrade():
    # Basic (1000 cents) -> Pro (3000 cents) halfway
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=30)
    effective = start + timedelta(days=15)

    credit, charge, net = calculate_proration(1000, 3000, start, end, effective)
    assert credit == 500
    assert charge == 1500
    assert net == 1000

def test_proration_midpoint_downgrade():
    # Pro (3000 cents) -> Basic (1000 cents) halfway
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=30)
    effective = start + timedelta(days=15)

    credit, charge, net = calculate_proration(3000, 1000, start, end, effective)
    assert credit == 1500
    assert charge == 500
    assert net == -1000

def test_proration_midpoint_cancel():
    # Pro (3000 cents) -> Cancel (0 cents) halfway
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=30)
    effective = start + timedelta(days=15)

    credit, charge, net = calculate_proration(3000, 0, start, end, effective)
    assert credit == 1500
    assert charge == 0
    assert net == -1500

def test_proration_boundary_cycle_start():
    # Pro (3000 cents) -> Premium (5000 cents) at start
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=30)
    effective = start

    credit, charge, net = calculate_proration(3000, 5000, start, end, effective)
    assert credit == 3000
    assert charge == 5000
    assert net == 2000

def test_proration_boundary_cycle_end():
    # Pro (3000 cents) -> Premium (5000 cents) at end
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=30)
    effective = end

    credit, charge, net = calculate_proration(3000, 5000, start, end, effective)
    assert credit == 0
    assert charge == 0
    assert net == 0

def test_proration_rounding():
    # Rounding check: test case with odd decimals
    # old_price = 1000, new_price = 3000
    # remaining / cycle_length = 0.3333333333333333
    # credit = 333.3333333333333 -> rounds to 333 (ROUND_HALF_UP)
    # charge = 999.9999999999999 -> rounds to 1000
    # net = 1000 - 333.33333 = 666.66666 -> rounds to 667
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=3)
    effective = start + timedelta(days=2) # 1/3 remaining time

    credit, charge, net = calculate_proration(1000, 3000, start, end, effective)
    assert credit == 333
    assert charge == 1000
    assert net == 667
