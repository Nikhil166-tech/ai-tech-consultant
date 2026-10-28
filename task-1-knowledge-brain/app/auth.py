import re
import secrets
import hashlib
from typing import Tuple, Optional
import argon2
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

# Production-grade Argon2id hasher (RFC 9106 recommended profile for interactive logins)
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MiB
    parallelism=2,
    hash_len=32,
    type=argon2.Type.ID
)

def hash_password(password: str) -> str:
    """Hashes a password using Argon2id."""
    return _hasher.hash(password)

def verify_and_check_rehash(password: str, stored_hash: str) -> Tuple[bool, bool]:
    """
    Verifies a password against the stored hash.
    Supports both modern Argon2id hashes and legacy PBKDF2-HMAC-SHA256 hashes.
    Returns: (is_valid: bool, needs_rehash: bool)
    """
    if not stored_hash or not password:
        return False, False

    # 1. Argon2id verification
    if stored_hash.startswith("$argon2"):
        try:
            _hasher.verify(stored_hash, password)
            needs_rehash = _hasher.check_needs_rehash(stored_hash)
            return True, needs_rehash
        except (VerifyMismatchError, InvalidHashError):
            return False, False
        except Exception:
            return False, False

    # 2. Legacy PBKDF2-HMAC-SHA256 verification (salt$key_hex)
    try:
        if "$" in stored_hash:
            salt_hex, key_hex = stored_hash.split("$", 1)
            salt_bytes = bytes.fromhex(salt_hex)
            check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 100_000)
            if secrets.compare_digest(check.hex(), key_hex):
                # Matched legacy hash; signal that it must be migrated to Argon2id
                return True, True
    except Exception:
        pass

    return False, False

def verify_password(password: str, stored_hash: str) -> bool:
    """
    Standard boolean password verification.
    Returns True if valid, False otherwise.
    """
    is_valid, _ = verify_and_check_rehash(password, stored_hash)
    return is_valid

def needs_rehash(stored_hash: str) -> bool:
    """Checks if a password hash should be upgraded to Argon2id."""
    if not stored_hash or not stored_hash.startswith("$argon2id$"):
        return True
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except Exception:
        return True

def validate_email(email: str) -> str:
    """
    Validates and normalizes email addresses.
    Raises ValueError if invalid.
    """
    if not email or not isinstance(email, str):
        raise ValueError("Email address is required.")
    
    clean = email.strip().lower()
    if len(clean) > 254 or len(clean) < 3:
        raise ValueError("Email address length must be between 3 and 254 characters.")
    
    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(email_regex, clean):
        raise ValueError("Invalid email format.")
    
    return clean

def validate_password_strength(password: str) -> Tuple[bool, Optional[str]]:
    """
    Enforces minimum security requirements for production passwords:
    - At least 8 characters
    - Must contain at least one uppercase letter, one lowercase letter, and one digit
    """
    if not password or not isinstance(password, str):
        return False, "Password is required."
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    
    if len(password) > 128:
        return False, "Password must be at most 128 characters long."
    
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)

    if not (has_upper and has_lower and has_digit):
        return False, "Password must include at least one uppercase letter, one lowercase letter, and one number."
    
    return True, None
