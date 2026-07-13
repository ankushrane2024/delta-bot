
import ast
import traceback

with open("web_server.py", "r") as f:
    source = f.read()

# Replace body of ares_status with try-except
new_source = source.replace("def ares_status():\n    if not ares_runner:", "def ares_status():\n    try:\n        if not ares_runner:")
new_source = new_source.replace("    return jsonify(res)", "    return jsonify(res)\n    except Exception as e:\n        import traceback\n        return jsonify({\"error\": str(e), \"traceback\": traceback.format_exc()}), 500")

# Indent all lines between "try:" and "except Exception as e:"
lines = new_source.split("\n")
in_try = False
for i, line in enumerate(lines):
    if line.strip() == "try:" and "def ares_status():" in lines[i-1]:
        in_try = True
        continue
    if line.strip() == "except Exception as e:" and in_try:
        in_try = False
    if in_try:
        lines[i] = "    " + line

with open("web_server.py", "w") as f:
    f.write("\n".join(lines))

