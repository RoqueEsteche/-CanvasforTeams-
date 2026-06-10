"""Credential generation from full name + cédula."""
import re
import unicodedata


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]", "", ascii_text).lower()


def generate_credentials(full_name: str, cedula: str, domain: str, collision_suffix: str = "") -> dict:
    """
    Karen Gonzalez + 6868066 →
      email:    karen.gonzalez@usil.edu.py
      password: 6868066-Kg
      login_id: karen.gonzalez
    """
    parts = full_name.strip().split()
    first = parts[0] if parts else "user"
    last  = parts[-1] if len(parts) > 1 else parts[0] if parts else "user"

    first_norm = _normalize(first) or "user"
    last_norm  = _normalize(last) or "user"
    
    suffix = _normalize(collision_suffix)
    login_id   = f"{first_norm}.{last_norm}{suffix}"
    email      = f"{login_id}@{domain}"

    first_init = _normalize(first[0])[0].upper() if first and _normalize(first[0]) else "U"
    last_init  = _normalize(last[0])[0].lower() if last and _normalize(last[0]) else "S"
    initials   = f"{first_init}{last_init}"
    password   = f"{cedula}-{initials}"

    return {
        "full_name": full_name,
        "cedula":    cedula,
        "login_id":  login_id,
        "email":     email,
        "password":  password,
        "display_name": full_name,
    }
