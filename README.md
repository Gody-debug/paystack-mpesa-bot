# Paystack M-Pesa Prompt Bot

Upload a PDF of phone numbers, review them, and send M-Pesa payment prompts
(via Paystack's Charge API, KES) to as many people as are in the PDF, at the amount you enter each day. Each person
approves on their own phone with their own M-Pesa PIN. The bot never sees a PIN.

## Setup (Windows PowerShell)

```powershell
cd paystack-mpesa-bot
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then edit .env
```

Edit `.env`:
- `PAYSTACK_SECRET_KEY` : start with your `sk_test_...` key
- `CUSTOMER_EMAIL_TEMPLATE` : Paystack requires an email per charge; this builds one from each phone number

## Run

Terminal 1 (dashboard):
```powershell
streamlit run app.py
```

Terminal 2 (webhook receiver, recommended):
```powershell
python webhook_server.py
ngrok http 5000
```
Put `https://<ngrok-url>/paystack/webhook` in the Paystack dashboard
(Settings > API Keys & Webhooks). Without the webhook you can still press
**Refresh statuses** in the Results tab, which uses Paystack's verify API.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit dashboard |
| `pdf_reader.py` | Extracts and normalises Kenyan numbers (+254...) |
| `paystack_client.py` | Charge + verify calls to Paystack |
| `database.py` | SQLite transaction log, duplicate guard |
| `webhook_server.py` | Verifies webhook signature, confirms and records results |
| `config.py` | Settings loaded from `.env` |

## Built-in safeguards
- No recipient limit; prompts go out `CONCURRENCY` at a time (default 5) with automatic back-off on rate limits
- Numbers already prompted TODAY (Kenya time) are skipped, so daily clients are never double-prompted but can be prompted again tomorrow
- Batches over `LARGE_BATCH_CONFIRM` (25) need the recipient count typed in to confirm
- Amount is entered fresh for every batch
- Consent checkbox required before sending
- Test/live mode banner
- Webhook signature (HMAC SHA512) checked, and result re-verified with Paystack

## To finish / check
1. Confirm your Paystack account has M-Pesa (KES) enabled for Kenya.
2. Decide the email approach (`CUSTOMER_EMAIL_TEMPLATE`).
3. Test with Paystack's test numbers (see the Paystack docs) before going live.
4. Check the exact response shape of `/charge` for M-Pesa in the current docs and adjust `paystack_client.py` if needed.
