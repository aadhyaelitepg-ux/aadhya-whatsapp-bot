from flask import Flask, request, jsonify
import requests
import json
import re

app = Flask(__name__)

# ─── CONFIG ───────────────────────────────────────────────
META_API_URL = "https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
ACCESS_TOKEN = "{YOUR_META_ACCESS_TOKEN}"
PHONE_NUMBER_ID = "{YOUR_PHONE_NUMBER_ID}"
VERIFY_TOKEN = "{YOUR_WEBHOOK_VERIFY_TOKEN}"

# ─── KEYWORD LISTS ────────────────────────────────────────
COMPLAINT_KEYWORDS = [
    "power", "electricity", "wifi", "water", "ac", "lock",
    "cleaning", "toilet", "bathroom", "noise", "maintenance",
    "repair", "washing machine", "tv", "fan", "light", "door",
    "window", "pest", "dustbin", "leakage"
]

ENQUIRY_KEYWORDS = [
    "vacancy", "available", "room", "sharing", "rent",
    "accommodation", "hostel", "bed", "single", "double",
    "triple", "1 share", "2 share", "3 share", "4 share",
    "space", "pg", "bed space", "any room", "looking for"
]

LOCATION_KEYWORDS = {
    "hitech": "hitech_city",
    "hitech city": "hitech_city",
    "1": "hitech_city",
    "gachibowli": "gachibowli",
    "2": "gachibowli",
    "khajaguda": "khajaguda",
    "3": "khajaguda",
    "financial": "financial_district",
    "financial district": "financial_district",
    "4": "financial_district"
}

# ─── PRICING PLACEHOLDERS (update with real values) ───────
PRICING = {
    "hitech_city":         {"1": "[PRICE_1SHARE_HTC]", "2": "[PRICE_2SHARE_HTC]", "3": "[PRICE_3SHARE_HTC]", "4": "[PRICE_4SHARE_HTC]"},
    "gachibowli":          {"1": "[PRICE_1SHARE_GCB]", "2": "[PRICE_2SHARE_GCB]", "3": "[PRICE_3SHARE_GCB]", "4": "[PRICE_4SHARE_GCB]"},
    "khajaguda":           {"1": "[PRICE_1SHARE_KHJ]", "2": "[PRICE_2SHARE_KHJ]", "3": "[PRICE_3SHARE_KHJ]", "4": "[PRICE_4SHARE_KHJ]"},
    "financial_district":  {"1": "[PRICE_1SHARE_FD]",  "2": "[PRICE_2SHARE_FD]",  "3": "[PRICE_3SHARE_FD]",  "4": "[PRICE_4SHARE_FD]"}
}

LOCATION_NAMES = {
    "hitech_city": "HiTech City",
    "gachibowli": "Gachibowli",
    "khajaguda": "Khajaguda",
    "financial_district": "Financial District"
}

# ─── SESSION STORE (use Redis/DB in production) ────────────
# Tracks conversation state per user
# { "phone_number": "awaiting_location" }
sessions = {}

# ─── MESSAGE TEMPLATES ────────────────────────────────────
def msg_enquiry_location():
    return (
        "Hi! 👋 Welcome to Aadhya RentStar!\n\n"
        "We're glad you reached out. We have hostel accommodations available with the following facilities:\n\n"
        "✅ WiFi\n✅ Air Conditioning (AC)\n✅ 3 Meals a Day\n✅ Washing Machine\n✅ TV\n\n"
        "We have properties in multiple locations. Which area do you prefer?\n\n"
        "1️⃣ HiTech City\n2️⃣ Gachibowli\n3️⃣ Khajaguda\n4️⃣ Financial District\n\n"
        "Please reply with the number or name of your preferred location. 😊"
    )

def msg_pricing(location_key):
    name = LOCATION_NAMES[location_key]
    p = PRICING[location_key]
    return (
        f"Great choice! Here are our available options at *{name}*:\n\n"
        f"🛏 1 Share — ₹{p['1']}/month\n"
        f"🛏 2 Share — ₹{p['2']}/month\n"
        f"🛏 3 Share — ₹{p['3']}/month\n"
        f"🛏 4 Share — ₹{p['4']}/month\n\n"
        "All rooms include:\n"
        "✅ WiFi | ✅ AC | ✅ 3 Meals | ✅ Washing Machine | ✅ TV\n\n"
        "Interested? Reply with your preferred sharing type and we'll take it from there! 😊"
    )

def msg_complaint():
    return (
        "Hi! We're sorry you're facing an issue. 🙏\n\n"
        "Please raise your complaint here and our team will attend to it promptly:\n\n"
        "👉 https://aadhya.rentstar.in\n\n"
        "Thank you for your patience!"
    )

def msg_default():
    return (
        "Hi! 👋 Thank you for reaching out to Aadhya RentStar!\n\n"
        "Are you enquiring about *room availability*, or do you need *maintenance support*?\n\n"
        "Please let us know and we'll assist you right away. 😊"
    )

# ─── SEND MESSAGE ─────────────────────────────────────────
def send_message(to, text):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    url = META_API_URL.replace("{PHONE_NUMBER_ID}", PHONE_NUMBER_ID)
    requests.post(url, headers=headers, json=payload)

# ─── KEYWORD CHECK ────────────────────────────────────────
def contains_keyword(text, keywords):
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)

def detect_location(text):
    text_lower = text.lower().strip()
    for key, location in LOCATION_KEYWORDS.items():
        if key in text_lower:
            return location
    return None

# ─── WEBHOOK ROUTES ───────────────────────────────────────
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        message = value["messages"][0]

        sender = message["from"]
        msg_type = message["type"]

        if msg_type != "text":
            return jsonify({"status": "ignored"}), 200

        text = message["text"]["body"].strip()

        # ── STATE: Awaiting location reply ──────────────────
        if sessions.get(sender) == "awaiting_location":
            location = detect_location(text)
            if location:
                sessions.pop(sender)  # clear session
                send_message(sender, msg_pricing(location))
            else:
                # Couldn't detect location, ask again
                send_message(sender, 
                    "Sorry, I didn't catch that. Please reply with:\n\n"
                    "1️⃣ HiTech City\n2️⃣ Gachibowli\n"
                    "3️⃣ Khajaguda\n4️⃣ Financial District"
                )
            return jsonify({"status": "ok"}), 200

        # ── COMPLAINT KEYWORDS ──────────────────────────────
        if contains_keyword(text, COMPLAINT_KEYWORDS):
            send_message(sender, msg_complaint())

        # ── ENQUIRY KEYWORDS ────────────────────────────────
        elif contains_keyword(text, ENQUIRY_KEYWORDS):
            sessions[sender] = "awaiting_location"
            send_message(sender, msg_enquiry_location())

        # ── DEFAULT ─────────────────────────────────────────
        else:
            send_message(sender, msg_default())

    except (KeyError, IndexError):
        pass  # Ignore non-message events (status updates, etc.)

    return jsonify({"status": "ok"}), 200

# ─── RUN ──────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(port=5000, debug=True)