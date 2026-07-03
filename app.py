from flask import Flask, request, jsonify
import requests
import json
import re
import os

app = Flask(__name__)

# CONFIG
META_API_URL = "https://graph.facebook.com/v18.0/{}/messages"
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "aadhyaliving2026")

# KEYWORD LISTS
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

PRICING = {
    "hitech_city": {"1": "[PRICE_1SHARE_HTC]", "2": "[PRICE_2SHARE_HTC]", "3": "[PRICE_3SHARE_HTC]", "4": "[PRICE_4SHARE_HTC]"},
    "gachibowli": {"1": "[PRICE_1SHARE_GCB]", "2": "[PRICE_2SHARE_GCB]", "3": "[PRICE_3SHARE_GCB]", "4": "[PRICE_4SHARE_GCB]"},
    "khajaguda": {"1": "[PRICE_1SHARE_KHJ]", "2": "[PRICE_2SHARE_KHJ]", "3": "[PRICE_3SHARE_KHJ]", "4": "[PRICE_4SHARE_KHJ]"},
    "financial_district": {"1": "[PRICE_1SHARE_FD]", "2": "[PRICE_2SHARE_FD]", "3": "[PRICE_3SHARE_FD]", "4": "[PRICE_4SHARE_FD]"}
}

LOCATION_NAMES = {
    "hitech_city": "HiTech City",
    "gachibowli": "Gachibowli",
    "khajaguda": "Khajaguda",
    "financial_district": "Financial District"
}

sessions = {}

def msg_enquiry_location():
    return ("Hi! Welcome to Aadhya Living!\n\n"
        "We're glad you reached out. We have hostel accommodations with:\n\n"
        "WiFi | AC | 3 Meals a Day | Washing Machine | TV\n\n"
        "We have properties in multiple locations. Which area do you prefer?\n\n"
        "1. HiTech City\n2. Gachibowli\n3. Khajaguda\n4. Financial District\n\n"
        "Please reply with the number or name of your preferred location.")

def msg_pricing(location_key):
    name = LOCATION_NAMES[location_key]
    p = PRICING[location_key]
    return (f"Great choice! Options at {name}:\n\n"
        f"1 Share - Rs.{p['1']}/month\n"
        f"2 Share - Rs.{p['2']}/month\n"
        f"3 Share - Rs.{p['3']}/month\n"
        f"4 Share - Rs.{p['4']}/month\n\n"
        "All rooms: WiFi | AC | 3 Meals | Washing Machine | TV\n\n"
        "Interested? Reply with your preferred sharing type!")

def msg_complaint():
    return ("Hi! Sorry you're facing an issue.\n\n"
        "Please raise your complaint here and our team will attend promptly:\n\n"
        "https://aadhya.rentstar.in\n\n"
        "Thank you for your patience!")

def msg_default():
    return ("Hi! Thank you for reaching out to Aadhya Living!\n\n"
        "Are you enquiring about room availability, or do you need maintenance support?\n\n"
        "Please let us know and we will assist you right away.")

def send_message(to, text):
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    url = META_API_URL.format(PHONE_NUMBER_ID)
    requests.post(url, headers=headers, json=payload)

def contains_keyword(text, keywords):
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)

def detect_location(text):
    text_lower = text.lower().strip()
    for key, location in LOCATION_KEYWORDS.items():
        if key in text_lower:
            return location
    return None

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
        if sessions.get(sender) == "awaiting_location":
            location = detect_location(text)
            if location:
                sessions.pop(sender)
                send_message(sender, msg_pricing(location))
            else:
                send_message(sender, "Sorry, I did not catch that. Please reply with:\n\n1. HiTech City\n2. Gachibowli\n3. Khajaguda\n4. Financial District")
            return jsonify({"status": "ok"}), 200
        if contains_keyword(text, COMPLAINT_KEYWORDS):
            send_message(sender, msg_complaint())
        elif contains_keyword(text, ENQUIRY_KEYWORDS):
            sessions[sender] = "awaiting_location"
            send_message(sender, msg_enquiry_location())
        else:
            send_message(sender, msg_default())
    except (KeyError, IndexError):
        pass
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
