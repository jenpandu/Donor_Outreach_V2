import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "DonorAgent"))
from dotenv import load_dotenv
load_dotenv()

from donor_memory import save_approved_exchange, load_donor_memory

save_approved_exchange("42", "1",
    "I pledged $500 last month, can I get a tax receipt? Please only email me.",
    "Thank you! We'll email your gift receipt this week.")
print("Saved. Waiting 60s for long-term extraction...")
time.sleep(60)
print(load_donor_memory("42", "receipt and contact preferences"))