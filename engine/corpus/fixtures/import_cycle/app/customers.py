"""Customers."""

from app.orders import describe_order


def customer_name(customer_id: int) -> str:
    """Return a customer's name."""
    return f"customer {customer_id}"


def latest_order(customer_id: int) -> str:
    """Describe a customer's latest order."""
    return describe_order(customer_id)
