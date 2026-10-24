"""Streamlit dashboard: PDF -> numbers -> confirm -> Paystack M-Pesa prompts (any batch size)."""
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

import config
import database as db
import paystack_client as paystack
from pdf_reader import extract_numbers

st.set_page_config(page_title="M-Pesa Prompt Bot", page_icon="💸", layout="wide")
db.init_db()


def send_one(phone: str, amount: float, batch_id: str) -> None:
    """Worker thread: record, charge, update. Touches only the DB and Paystack."""
    reference = f"REG-{uuid.uuid4().hex[:16]}"
    email = config.CUSTOMER_EMAIL_TEMPLATE.format(phone=phone.lstrip("+"))
    db.insert_transaction(reference, batch_id, phone, email, amount)
    result = paystack.charge_mpesa(phone, email, amount, reference)
    db.update_by_reference(reference, result["status"], result["paystack_status"], result["message"])


def check_one(ref: str) -> None:
    res = paystack.verify(ref)
    if res["ok"]:
        db.update_by_reference(ref, res["status"], res["paystack_status"], res["message"])


def refresh_pending() -> int:
    refs = db.get_pending_references()
    with ThreadPoolExecutor(max_workers=config.CONCURRENCY) as pool:
        list(pool.map(check_one, refs))
    return len(refs)


# ---------- Header / safety banner ----------
st.title("💸 M-Pesa Registration Fee Prompts")

if not config.key_is_set():
    st.error("No valid Paystack key found. Copy `.env.example` to `.env` and set PAYSTACK_SECRET_KEY.")
    st.stop()

if config.is_test_mode():
    st.info("TEST MODE: using a Paystack test key. No real money moves.")
else:
    st.warning("LIVE MODE: real M-Pesa prompts will be sent to real phones.")

tab_send, tab_results = st.tabs(["Send prompts", "Results"])

# ---------- Send tab ----------
with tab_send:
    st.subheader("1. Upload today's PDF of phone numbers")
    pdf = st.file_uploader("PDF file (any number of clients)", type=["pdf"])

    if pdf is not None and st.session_state.get("pdf_key") != (pdf.name, pdf.size):
        with st.spinner("Reading PDF..."):
            st.session_state["numbers"] = extract_numbers(pdf.getvalue())
        st.session_state["pdf_key"] = (pdf.name, pdf.size)
        st.session_state.pop("sent_batch", None)

    numbers = st.session_state.get("numbers", []) if pdf is not None else []

    if pdf is not None and not numbers:
        st.warning("No valid Kenyan mobile numbers found in this PDF.")

    if numbers:
        sent_today = db.phones_prompted_today(numbers)

        st.subheader("2. Review recipients")
        st.caption(f"Found {len(numbers)} unique number(s). Untick any you want to skip.")
        resend = st.checkbox(
            f"Also re-send to the {len(sent_today)} number(s) already prompted today",
            value=False,
            disabled=not sent_today,
        )
        skip = set() if resend else sent_today

        df = pd.DataFrame(
            {
                "Include": [n not in skip for n in numbers],
                "Phone": numbers,
                "Note": ["Already prompted today, skipped" if n in skip else "" for n in numbers],
            }
        )
        edited = st.data_editor(
            df,
            hide_index=True,
            use_container_width=True,
            disabled=["Phone", "Note"],
            height=min(500, 38 + 35 * len(df)),
            key=f"recipients_{st.session_state['pdf_key']}_{resend}",
        )
        selected = [p for p, inc in zip(edited["Phone"], edited["Include"]) if inc]
        st.write(f"**Selected: {len(selected)} of {len(numbers)}**")

        st.subheader("3. Today's amount")
        amount = st.number_input(
            "Amount to prompt each person (KES)",
            min_value=1.0,
            value=float(st.session_state.get("last_amount", 100.0)),
            step=10.0,
            format="%.2f",
            help="Change this any time; it applies to the whole batch.",
        )
        st.session_state["last_amount"] = amount

        st.subheader("4. Confirm and send")
        total = amount * len(selected)
        st.write(
            f"This will send **{len(selected)}** prompt(s) of **KES {amount:,.2f}** "
            f"(total KES {total:,.2f})."
        )
        consent = st.checkbox(
            "I confirm every selected person has agreed to pay this amount, "
            "and I understand each must approve on their own phone."
        )

        confirmed_count = True
        if len(selected) > config.LARGE_BATCH_CONFIRM:
            typed = st.text_input(
                f"Large batch: type **{len(selected)}** to confirm the number of recipients"
            )
            confirmed_count = typed.strip() == str(len(selected))

        if st.button(
            "Send prompts",
            type="primary",
            disabled=not (consent and selected and confirmed_count),
        ):
            batch_id = uuid.uuid4().hex[:10]
            bar = st.progress(0.0, text=f"Sending 0 / {len(selected)}")
            done = 0
            with ThreadPoolExecutor(max_workers=config.CONCURRENCY) as pool:
                futures = [pool.submit(send_one, p, amount, batch_id) for p in selected]
                for _ in as_completed(futures):
                    done += 1
                    bar.progress(done / len(selected), text=f"Sending {done} / {len(selected)}")
            st.session_state["sent_batch"] = batch_id
            st.session_state["last_batch"] = batch_id

        if st.session_state.get("sent_batch"):
            rows = db.get_transactions(st.session_state["sent_batch"])
            failed = [r for r in rows if r["status"] == "failed"]
            st.success(
                f"Batch {st.session_state['sent_batch']}: {len(rows)} prompt(s) processed, "
                f"{len(failed)} rejected immediately. Open the Results tab to follow payments."
            )

# ---------- Results tab ----------
with tab_results:
    c1, c2, _ = st.columns([1, 2, 4])
    if c1.button("Refresh statuses"):
        n = refresh_pending()
        st.toast(f"Checked {n} pending transaction(s)")

    batches = db.get_batch_ids()
    choice = c2.selectbox("Batch", ["All"] + batches, label_visibility="collapsed")
    rows = db.get_transactions(None if choice == "All" else choice)

    if rows:
        out = pd.DataFrame(rows)[
            ["created_at", "batch_id", "phone", "amount_kes", "status", "paystack_status", "message", "reference"]
        ]
        counts = out["status"].value_counts()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Successful", int(counts.get("success", 0)))
        m2.metric("Pending", int(counts.get("pending", 0)))
        m3.metric("Failed", int(counts.get("failed", 0)))
        m4.metric("Collected (KES)", f"{out.loc[out['status'] == 'success', 'amount_kes'].sum():,.2f}")
        st.dataframe(out, hide_index=True, use_container_width=True)
        st.download_button(
            "Download report (CSV)",
            out.to_csv(index=False).encode("utf-8"),
            file_name="mpesa_report.csv",
            mime="text/csv",
        )
    else:
        st.info("No transactions yet.")
