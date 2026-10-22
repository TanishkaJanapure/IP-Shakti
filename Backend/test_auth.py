"""Basic password-hash smoke test; run from Backend with: python test_auth.py"""
import hashlib
import hmac
import secrets

def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    return salt.hex() + ":" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000).hex()

def verify(password, stored):
    salt_hex, digest_hex = stored.split(":", 1)
    candidate = password_hash(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
    return hmac.compare_digest(candidate, digest_hex)

if __name__ == "__main__":
    saved = password_hash("correct horse battery staple")
    assert verify("correct horse battery staple", saved)
    assert not verify("wrong password", saved)
    print("Password hashing smoke test passed.")
