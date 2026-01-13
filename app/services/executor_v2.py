"""
Executor V2 - sprejme odločitev routerja in izvede ustrezno akcijo.
Ne vsebuje FSM; obstoječo logiko dobimo prek funkcijskih parametrov.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def execute_decision(
    decision: Dict[str, Any],
    message: str,
    state: Dict[str, Any],
    translate_fn: Callable[[str], str],
    info_responder: Callable[[str, bool], str],
    product_responder: Callable[[str], str],
    reservation_flow_fn: Callable[[str, Dict[str, Any]], str],
    reset_fn: Callable[[Dict[str, Any]], None],
    continuation_fn: Callable[[Optional[str], Dict[str, Any]], str],
    general_handler: Optional[Callable[[str], str]] = None,
) -> Optional[str]:
    routing = decision.get("routing", {})
    context = decision.get("context", {})
    intent = routing.get("intent") or "GENERAL"
    is_interrupt = routing.get("is_interrupt", False)

    if intent == "INFO":
        info_key = context.get("info_key")
        reply = info_responder(info_key, context.get("needs_soft_sell", False))
        if is_interrupt and state.get("step"):
            cont = continuation_fn(state.get("step"), state)
            reply = f"{reply}\n\n---\n\n📝 **Nadaljujemo z rezervacijo:**\n{cont}"
        return translate_fn(reply)

    if intent == "PRODUCT":
        prod_key = context.get("product_category") or "izdelki_splosno"
        reply = product_responder(prod_key)
        if is_interrupt and state.get("step"):
            cont = continuation_fn(state.get("step"), state)
            reply = f"{reply}\n\n---\n\n📝 **Nadaljujemo z rezervacijo:**\n{cont}"
        return translate_fn(reply)

    if intent == "SYSTEM":
        reset_fn(state)
        return translate_fn("Rezervacijo sem ponastavil. Kako lahko pomagam?")

    if intent == "BOOKING_ROOM":
        reset_fn(state)
        state["type"] = "room"
        return translate_fn(reservation_flow_fn(message, state))

    if intent == "BOOKING_TABLE":
        reset_fn(state)
        state["type"] = "table"
        return translate_fn(reservation_flow_fn(message, state))

    if intent == "BOOKING_CONTINUE":
        return translate_fn(reservation_flow_fn(message, state))

    # GENERAL ali neznano → prepusti klicatelju (None = fallback na staro pot)
    if general_handler:
        return translate_fn(general_handler(message))
    return None
