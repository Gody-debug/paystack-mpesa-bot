import os
from dotenv import load_dotenv

load_dotenv()

PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
PAYSTACK_BASE_URL = "https://api.paystack.co"
CURRENCY = "KES"
CUSTOMER_EMAIL_TEMPLATE = os.getenv("CUSTOMER_EMAIL_TEMPLATE", "{phone}@yourdomain.com")
DB_PATH = os.getenv("DB_PATH", "transactions.db")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5000"))

# No cap on recipients. Prompts are sent a few at a time to respect Paystack rate limits.
CONCURRENCY = int(os.getenv("CONCURRENCY", "5"))
# Batches bigger than this require typing the recipient count to confirm.
LARGE_BATCH_CONFIRM = int(os.getenv("LARGE_BATCH_CONFIRM", "25"))


def is_test_mode() -> bool:
    return PAYSTACK_SECRET_KEY.startswith("sk_test_")


def key_is_set() -> bool:
    return PAYSTACK_SECRET_KEY.startswith(("sk_test_", "sk_live_"))
