"""Reports import orders lazily, which does not create a load-time cycle."""

from app.customers import customer_name


def report(order_id: int) -> str:
    """Build a one-line report."""
    from app.orders import describe_order

    return f"{customer_name(order_id)}: {describe_order(order_id)}"
