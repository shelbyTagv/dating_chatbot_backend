import requests
import db_manager

def run():
    pending = db_manager.get_pending_transactions()

    for tx in pending:
        try:
            r = requests.post(tx["poll_url"])
            if "Paid" in r.text:
                db_manager.mark_transaction_paid(tx["id"])
                db_manager.activate_subscription(tx["user_id"])
        except Exception:
            continue

if __name__ == "__main__":
    run()
