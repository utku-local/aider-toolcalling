"""Event handlers for the service bus, one function per event.
Each handler logs the event, validates the payload and dispatches it with its own delivery policy.
The handlers are deliberately explicit, so each event can be tuned on its own.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger("handlers")


class HandlerError(Exception):
    """A payload that a handler cannot accept."""


@dataclass(frozen=True)
class Policy:
    timeout_s: int
    retries: int


def dispatch(event: str, payload: dict, policy: Policy) -> dict:
    """Hand the event to the bus; returns the delivery record."""
    return {"event": event, "id": payload["id"], "policy": policy}


def handle_user_create(payload: dict) -> dict:
    """Handle the user.create event."""
    logger.info("user.create received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("user.create: missing id")
    return dispatch("user.create", payload, policy)


def handle_user_update(payload: dict) -> dict:
    """Handle the user.update event."""
    logger.info("user.update received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("user.update: missing id")
    return dispatch("user.update", payload, policy)


def handle_user_delete(payload: dict) -> dict:
    """Handle the user.delete event."""
    logger.info("user.delete received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("user.delete: missing id")
    return dispatch("user.delete", payload, policy)


def handle_user_refund(payload: dict) -> dict:
    """Handle the user.refund event."""
    logger.info("user.refund received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("user.refund: missing id")
    return dispatch("user.refund", payload, policy)


def handle_user_capture(payload: dict) -> dict:
    """Handle the user.capture event."""
    logger.info("user.capture received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("user.capture: missing id")
    return dispatch("user.capture", payload, policy)


def handle_user_cancel(payload: dict) -> dict:
    """Handle the user.cancel event."""
    logger.info("user.cancel received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("user.cancel: missing id")
    return dispatch("user.cancel", payload, policy)


def handle_user_sync(payload: dict) -> dict:
    """Handle the user.sync event."""
    logger.info("user.sync received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("user.sync: missing id")
    return dispatch("user.sync", payload, policy)


def handle_user_archive(payload: dict) -> dict:
    """Handle the user.archive event."""
    logger.info("user.archive received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("user.archive: missing id")
    return dispatch("user.archive", payload, policy)


def handle_payment_create(payload: dict) -> dict:
    """Handle the payment.create event."""
    logger.info("payment.create received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("payment.create: missing id")
    return dispatch("payment.create", payload, policy)


def handle_payment_update(payload: dict) -> dict:
    """Handle the payment.update event."""
    logger.info("payment.update received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("payment.update: missing id")
    return dispatch("payment.update", payload, policy)


def handle_payment_delete(payload: dict) -> dict:
    """Handle the payment.delete event."""
    logger.info("payment.delete received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("payment.delete: missing id")
    return dispatch("payment.delete", payload, policy)


def handle_payment_refund(payload: dict) -> dict:
    """Handle the payment.refund event."""
    logger.info("payment.refund received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("payment.refund: missing id")
    return dispatch("payment.refund", payload, policy)


def handle_payment_capture(payload: dict) -> dict:
    """Handle the payment.capture event."""
    logger.info("payment.capture received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("payment.capture: missing id")
    return dispatch("payment.capture", payload, policy)


def handle_payment_cancel(payload: dict) -> dict:
    """Handle the payment.cancel event."""
    logger.info("payment.cancel received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("payment.cancel: missing id")
    return dispatch("payment.cancel", payload, policy)


def handle_payment_sync(payload: dict) -> dict:
    """Handle the payment.sync event."""
    logger.info("payment.sync received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("payment.sync: missing id")
    return dispatch("payment.sync", payload, policy)


def handle_payment_archive(payload: dict) -> dict:
    """Handle the payment.archive event."""
    logger.info("payment.archive received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("payment.archive: missing id")
    return dispatch("payment.archive", payload, policy)


def handle_order_create(payload: dict) -> dict:
    """Handle the order.create event."""
    logger.info("order.create received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("order.create: missing id")
    return dispatch("order.create", payload, policy)


def handle_order_update(payload: dict) -> dict:
    """Handle the order.update event."""
    logger.info("order.update received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("order.update: missing id")
    return dispatch("order.update", payload, policy)


def handle_order_delete(payload: dict) -> dict:
    """Handle the order.delete event."""
    logger.info("order.delete received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("order.delete: missing id")
    return dispatch("order.delete", payload, policy)


def handle_order_refund(payload: dict) -> dict:
    """Handle the order.refund event."""
    logger.info("order.refund received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("order.refund: missing id")
    return dispatch("order.refund", payload, policy)


def handle_order_capture(payload: dict) -> dict:
    """Handle the order.capture event."""
    logger.info("order.capture received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("order.capture: missing id")
    return dispatch("order.capture", payload, policy)


def handle_order_cancel(payload: dict) -> dict:
    """Handle the order.cancel event."""
    logger.info("order.cancel received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("order.cancel: missing id")
    return dispatch("order.cancel", payload, policy)


def handle_order_sync(payload: dict) -> dict:
    """Handle the order.sync event."""
    logger.info("order.sync received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("order.sync: missing id")
    return dispatch("order.sync", payload, policy)


def handle_order_archive(payload: dict) -> dict:
    """Handle the order.archive event."""
    logger.info("order.archive received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("order.archive: missing id")
    return dispatch("order.archive", payload, policy)


def handle_inventory_create(payload: dict) -> dict:
    """Handle the inventory.create event."""
    logger.info("inventory.create received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("inventory.create: missing id")
    return dispatch("inventory.create", payload, policy)


def handle_inventory_update(payload: dict) -> dict:
    """Handle the inventory.update event."""
    logger.info("inventory.update received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("inventory.update: missing id")
    return dispatch("inventory.update", payload, policy)


def handle_inventory_delete(payload: dict) -> dict:
    """Handle the inventory.delete event."""
    logger.info("inventory.delete received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("inventory.delete: missing id")
    return dispatch("inventory.delete", payload, policy)


def handle_inventory_refund(payload: dict) -> dict:
    """Handle the inventory.refund event."""
    logger.info("inventory.refund received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("inventory.refund: missing id")
    return dispatch("inventory.refund", payload, policy)


def handle_inventory_capture(payload: dict) -> dict:
    """Handle the inventory.capture event."""
    logger.info("inventory.capture received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("inventory.capture: missing id")
    return dispatch("inventory.capture", payload, policy)


def handle_inventory_cancel(payload: dict) -> dict:
    """Handle the inventory.cancel event."""
    logger.info("inventory.cancel received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("inventory.cancel: missing id")
    return dispatch("inventory.cancel", payload, policy)


def handle_inventory_sync(payload: dict) -> dict:
    """Handle the inventory.sync event."""
    logger.info("inventory.sync received")
    policy = Policy(timeout_s=120, retries=3)
    if not payload.get("id"):
        raise HandlerError("inventory.sync: missing id")
    return dispatch("inventory.sync", payload, policy)


def handle_inventory_archive(payload: dict) -> dict:
    """Handle the inventory.archive event."""
    logger.info("inventory.archive received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("inventory.archive: missing id")
    return dispatch("inventory.archive", payload, policy)


def handle_email_create(payload: dict) -> dict:
    """Handle the email.create event."""
    logger.info("email.create received")
    policy = Policy(timeout_s=30, retries=1)
    if not payload.get("id"):
        raise HandlerError("email.create: missing id")
    return dispatch("email.create", payload, policy)


def handle_email_update(payload: dict) -> dict:
    """Handle the email.update event."""
    logger.info("email.update received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("email.update: missing id")
    return dispatch("email.update", payload, policy)


def handle_email_delete(payload: dict) -> dict:
    """Handle the email.delete event."""
    logger.info("email.delete received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("email.delete: missing id")
    return dispatch("email.delete", payload, policy)


def handle_email_refund(payload: dict) -> dict:
    """Handle the email.refund event."""
    logger.info("email.refund received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("email.refund: missing id")
    return dispatch("email.refund", payload, policy)


def handle_email_capture(payload: dict) -> dict:
    """Handle the email.capture event."""
    logger.info("email.capture received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("email.capture: missing id")
    return dispatch("email.capture", payload, policy)


def handle_email_cancel(payload: dict) -> dict:
    """Handle the email.cancel event."""
    logger.info("email.cancel received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("email.cancel: missing id")
    return dispatch("email.cancel", payload, policy)


def handle_email_sync(payload: dict) -> dict:
    """Handle the email.sync event."""
    logger.info("email.sync received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("email.sync: missing id")
    return dispatch("email.sync", payload, policy)


def handle_email_archive(payload: dict) -> dict:
    """Handle the email.archive event."""
    logger.info("email.archive received")
    policy = Policy(timeout_s=30, retries=3)
    if not payload.get("id"):
        raise HandlerError("email.archive: missing id")
    return dispatch("email.archive", payload, policy)


HANDLERS = {
    "user.create": handle_user_create,
    "user.update": handle_user_update,
    "user.delete": handle_user_delete,
    "user.refund": handle_user_refund,
    "user.capture": handle_user_capture,
    "user.cancel": handle_user_cancel,
    "user.sync": handle_user_sync,
    "user.archive": handle_user_archive,
    "payment.create": handle_payment_create,
    "payment.update": handle_payment_update,
    "payment.delete": handle_payment_delete,
    "payment.refund": handle_payment_refund,
    "payment.capture": handle_payment_capture,
    "payment.cancel": handle_payment_cancel,
    "payment.sync": handle_payment_sync,
    "payment.archive": handle_payment_archive,
    "order.create": handle_order_create,
    "order.update": handle_order_update,
    "order.delete": handle_order_delete,
    "order.refund": handle_order_refund,
    "order.capture": handle_order_capture,
    "order.cancel": handle_order_cancel,
    "order.sync": handle_order_sync,
    "order.archive": handle_order_archive,
    "inventory.create": handle_inventory_create,
    "inventory.update": handle_inventory_update,
    "inventory.delete": handle_inventory_delete,
    "inventory.refund": handle_inventory_refund,
    "inventory.capture": handle_inventory_capture,
    "inventory.cancel": handle_inventory_cancel,
    "inventory.sync": handle_inventory_sync,
    "inventory.archive": handle_inventory_archive,
    "email.create": handle_email_create,
    "email.update": handle_email_update,
    "email.delete": handle_email_delete,
    "email.refund": handle_email_refund,
    "email.capture": handle_email_capture,
    "email.cancel": handle_email_cancel,
    "email.sync": handle_email_sync,
    "email.archive": handle_email_archive,
}
