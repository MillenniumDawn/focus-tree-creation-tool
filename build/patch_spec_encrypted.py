"""
patch_spec_encrypted.py
Called by build_encrypted.bat to generate an AES-encrypted spec file.
Do NOT run this directly — use build_encrypted.bat instead.
"""
import sys, os

# ── Change this to your own secret string before building ──────────────
ENCRYPTION_KEY = "HOI4CM_BLAZER_2025"
# ───────────────────────────────────────────────────────────────────────

spec_in  = os.path.join(os.path.dirname(__file__), "hoi4_content_maker.spec")
spec_out = os.path.join(os.path.dirname(__file__), "hoi4_content_maker_enc.spec")

try:
    with open(spec_in, "r", encoding="utf-8") as f:
        spec = f.read()
except FileNotFoundError:
    print(f"[patch_spec] ERROR: Could not find {spec_in}")
    sys.exit(1)

old = (
    "block_cipher = None   # set a string key here if you want bytecode encryption\n"
    "                      # e.g. block_cipher = 'YOUR_SECRET_KEY_HERE'\n"
    "                      # Requires: pip install pyinstaller[encryption]"
)
new = f"block_cipher = '{ENCRYPTION_KEY}'"

if old not in spec:
    # Already patched or different format — just set it at the top
    spec = f"block_cipher = '{ENCRYPTION_KEY}'\n" + spec

spec = spec.replace(old, new)

with open(spec_out, "w", encoding="utf-8") as f:
    f.write(spec)

print(f"[patch_spec] Encrypted spec written: {spec_out}")
print(f"[patch_spec] Encryption key: {ENCRYPTION_KEY}")
