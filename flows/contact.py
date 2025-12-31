from whatsapp import send_text
from db import db_manager

BRANCHES = {
    "1": {
        "name": "Head Office",
        "details": (
            "🏢 *Head Office*\n\n"
            "📍 19 Dan Judson Rd,\n"
            "Milton Park, Harare, Zimbabwe\n\n"
            "📞 +263 242-750-377/9\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "2": {
        "name": "Main Branch (Kaguvi)",
        "details": (
            "🏢 *Main Branch – Kaguvi*\n\n"
            "📍 61 Kaguvi Street,\n"
            "Harare, Zimbabwe\n\n"
            "📞 +263 242-750-377/9\n"
            "📱 +263 788 369 595\n\n"
            "📧 hellokaguvi@microhub.co.zw"
        )
    },
    "3": {
        "name": "Chitungwiza Branch",
        "details": (
            "🏢 *Chitungwiza Branch*\n\n"
            "📍 Shop No 6, Vintage Mall,\n"
            "Makoni, Chitungwiza\n\n"
            "📞 +263 242-750-377/9\n"
            "📱 +263 789 562 534\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "4": {
        "name": "Karoi Branch",
        "details": (
            "🏢 *Karoi Branch*\n\n"
            "📍 757 Chifamba Complex, Karoi\n\n"
            "📱 +263 789 562 592\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "5": {
        "name": "Chegutu Branch",
        "details": (
            "🏢 *Chegutu Branch*\n\n"
            "📍 72 King Street, Chegutu\n\n"
            "📱 +263 789 562 589\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "6": {
        "name": "Bindura Branch",
        "details": (
            "🏢 *Bindura Branch*\n\n"
            "📍 Shop No 4, First Floor,\n"
            "Bindura Mall, Robert Mugabe St\n\n"
            "📱 +263 789 562 549\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "7": {
        "name": "Kadoma Branch",
        "details": (
            "🏢 *Kadoma Branch*\n\n"
            "📍 5 & 6 Herbert Chitepo St,\n"
            "Sam Levy Building, Kadoma\n\n"
            "📱 +263 789 562 540\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "8": {
        "name": "Marondera Branch",
        "details": (
            "🏢 *Marondera Branch*\n\n"
            "📍 Shop 103, Corncode Building,\n"
            "39 Pine Street, Marondera\n\n"
            "📱 +263 789 562 538\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "9": {
        "name": "Chinhoyi Branch",
        "details": (
            "🏢 *Chinhoyi Branch*\n\n"
            "📍 5246 Midway Street,\n"
            "Skyjuice House, Chinhoyi\n\n"
            "📱 +263 789 562 590\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "10": {
        "name": "Murehwa Branch",
        "details": (
            "🏢 *Murehwa Branch*\n\n"
            "📍 Shop No 4, Mapfumo Complex,\n"
            "Murehwa\n\n"
            "📱 +263 789 562 591\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "11": {
        "name": "Chivhu Branch",
        "details": (
            "🏢 *Chivhu Branch*\n\n"
            "📍 262 Cloete Street, Chivhu\n\n"
            "📱 +263 789 562 593\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "12": {
        "name": "Mutare Branch",
        "details": (
            "🏢 *Mutare Branch*\n\n"
            "📍 1018 Herbert Chitepo Street,\n"
            "Sunrise Complex, First Floor, Shop 6\n\n"
            "📱 +263 789 562 540\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "13": {
        "name": "Masvingo Branch",
        "details": (
            "🏢 *Masvingo Branch*\n\n"
            "📍 113 Hellet Street,\n"
            "Junior Complex, Office No. 9,\n"
            "First Floor, Masvingo\n\n"
            "📱 +263 774 552 231\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "14": {
        "name": "Gweru Branch",
        "details": (
            "🏢 *Gweru Branch*\n\n"
            "📍 Shop No. 10, 62 Musopero Building,\n"
            "7th Street, Gweru\n\n"
            "📱 +263 776 426 687\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
    "15": {
        "name": "Bulawayo Branch",
        "details": (
            "🏢 *Bulawayo Branch*\n\n"
            "📍 Shop 5, MZ Mall,\n"
            "89 Robert Mugabe Way,\n"
            "Between 8th & 9th Avenue\n\n"
            "📱 +263 786 522 442\n"
            "📱 +263 788 369 595\n\n"
            "📧 hello@microhub.co.zw"
        )
    },
}


def handle_contact_menu(phone, text, sender_name, payload, user):
    db_manager.update_user(user["id"], "chat_state", "CONTACT_BRANCH")

    send_text(
        phone,
        "📍 *Microhub Branches*\n\n"
        "1️⃣ Head Office\n"
        "2️⃣ Main Branch (Kaguvi)\n"
        "3️⃣ Chitungwiza\n"
        "4️⃣ Karoi\n"
        "5️⃣ Chegutu\n"
        "6️⃣ Bindura\n"
        "7️⃣ Kadoma\n"
        "8️⃣ Marondera\n"
        "9️⃣ Chinhoyi\n"
        "🔟 Murehwa\n"
        "1️⃣1️⃣ Chivhu\n"
        "1️⃣2️⃣ Mutare\n"
        "1️⃣3️⃣ Masvingo\n"
        "1️⃣4️⃣ Gweru\n"
        "1️⃣5️⃣ Bulawayo"
    )


def handle_contact_selection(phone, text, sender_name, payload, user):
    if text in BRANCHES:
        send_text(phone, BRANCHES[text]["details"])
        return

    send_text(phone, "❌ Invalid branch. Please choose a number from the list.")


