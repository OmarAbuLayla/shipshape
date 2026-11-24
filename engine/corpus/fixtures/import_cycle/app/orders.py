"""Orders."""

from app.customers import customer_name


def describe_order(order_id: int) -> str:
    """Describe an order."""
    return f"order {order_id} for {customer_name(order_id)}"
