"""
Receives Paystack webhooks and updates the database.

Run:  python webhook_server.py
Expose it publicly (e.g. `ngrok http 5000`) and set the URL
https://<your-public-url>/paystack/webhook
as the Webhook URL in your Paystack dashboard (Settings > API Keys & Webhooks).
"""
import hashlib
import hmac

from flask import Flask, abort, request

import config
import database as db
import paystack_client as paystack

app = Flask(__name__)
db.init_db()

HANDLED = {"charge.success", "charge.failed"}


def _valid_signature(raw: bytes, signature: str | None) -> bool:
    if not signature or not config.PAYSTACK_SECRET_KEY:
        return False
    expected = hmac.new(config.PAYSTACK_SECRET_KEY.encode(), raw, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/paystack/webhook")
def webhook():
    raw = request.get_data()
    if not _valid_signature(raw, request.headers.get("x-paystack-signature")):
        abort(401)

    event = request.get_json(silent=True) or {}
    if event.get("event") in HANDLED:
        reference = (event.get("data") or {}).get("reference")
        if reference:
            # Don't trust the payload alone: confirm with Paystack's verify API.
            result = paystack.verify(reference)
            if result["ok"]:
                db.update_by_reference(
                    reference, result["status"], result["paystack_status"], result["message"]
                )
    return "", 200


@app.get("/health")
def health():
    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.WEBHOOK_PORT)
