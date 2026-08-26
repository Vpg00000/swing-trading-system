import os

def generate_dhan_bracket_order(
    symbol: str,
    security_id: str,
    quantity: int,
    entry_price: float,
    target_price: float,
    stop_loss_price: float,
    order_type: str = "LIMIT"
):
    margin_pct = float(os.getenv('DANH_MARGIN_PCT', '100.0'))
    verify_margin_requirement(available_cash, order_value, margin_pct)

def verify_margin_requirement(available_cash: float, order_value: float, margin_pct: float = 100.0):
    # Implementation remains the same
    pass
