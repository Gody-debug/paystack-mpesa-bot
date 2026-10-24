"""Thin wrapper around Paystack's Charge and Verify APIs (M-Pesa, KES)."""
import time

import requests

import config


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def map_status(paystack_status: str | None) -> str:
    """Collapse Paystack statuses into pending / success / failed."""
    s = (paystack_status or "").lower()
    if s == "success":
        return "success"
    if s in {"failed", "abandoned", "reversed", "timeout", "cancelled"}:
        return "failed"
    return "pending"  # pay_offline, pending, ongoing, send_otp, etc.


def charge_mpesa(phone: str, email: str, amount_kes: float, reference: str) -> dict:
    """
    Trigger an M-Pesa STK prompt. Returns a dict:
    {ok, status, paystack_status, message}
    Amount is sent in subunits (KES x 100).
    """
    payload = {
        "email": email,
        "amount": int(round(amount_kes * 100)),
        "currency": config.CURRENCY,
        "reference": reference,
        "mobile_money": {"phone": phone, "provider": "mpesa"},
    }
    try:
        # Retry only on rate limiting (429); same reference, so no double charge.
        for attempt in range(4):
            r = requests.post(
                f"{config.PAYSTACK_BASE_URL}/charge", headers=_headers(), json=payload, timeout=30
            )
            if r.status_code != 429:
                break
            time.sleep(2 ** attempt)
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "status": "failed", "paystack_status": None, "message": f"Request error: {exc}"}

    data = body.get("data") or {}
    if not body.get("status"):
        return {
            "ok": False,
            "status": "failed",
            "paystack_status": data.get("status"),
            "message": body.get("message", "Paystack rejected the request"),
        }
    ps = data.get("status")
    return {
        "ok": True,
        "status": map_status(ps),
        "paystack_status": ps,
        "message": data.get("display_text") or body.get("message"),
    }


def verify(reference: str) -> dict:
    """Ask Paystack for the current state of a transaction."""
    try:
        r = requests.get(
            f"{config.PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=_headers(),
            timeout=30,
        )
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "status": "pending", "paystack_status": None, "message": str(exc)}

    data = body.get("data") or {}
    if not body.get("status"):
        return {"ok": False, "status": "pending", "paystack_status": None, "message": body.get("message")}
    ps = data.get("status")
    return {
        "ok": True,
        "status": map_status(ps),
        "paystack_status": ps,
        "message": data.get("gateway_response"),
    }
