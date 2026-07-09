from secrets import choice
from string import ascii_lowercase, ascii_uppercase, digits, punctuation


def generate_temporary_password(length: int = 12) -> str:
    if length < 8:
        length = 8
    alphabet = ascii_lowercase + ascii_uppercase + digits + punctuation
    password = [
        choice(ascii_lowercase),
        choice(ascii_uppercase),
        choice(digits),
        choice(punctuation),
    ]
    password.extend(choice(alphabet) for _ in range(length - 4))
    return "".join(password)
