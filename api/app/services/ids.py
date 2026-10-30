import secrets
import string

from app.services.auth import hash_password


def check_digit(value: str) -> str:
    total = sum(int(ch) for ch in value if ch.isdigit())
    return str(total % 10)


def generate_student_number(school_code: str, seq: int) -> str:
    base = f"{school_code.upper()}{seq:05d}"
    return base + check_digit(base)


def generate_pin(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_pin(pin: str) -> str:
    return hash_password(pin)


def verify_pin(plain: str, hashed: str) -> bool:
    from app.services.auth import verify_password
    return verify_password(plain, hashed)
