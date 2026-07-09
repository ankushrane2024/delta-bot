import os
with open("config.py", "a") as f:
    f.write("\n# --- Hedge Provider Override ---\n")
    f.write("SMART_HEDGE_PROVIDER = os.getenv('SMART_HEDGE_PROVIDER', 'ARES')\n")
print("Updated config.py")
