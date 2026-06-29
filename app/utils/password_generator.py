from secrets import choice
from string import ascii_letters, digits


def generate_temporary_password(length: int = 12) -> str:
    alphabet = ascii_letters + digits
    return "".join(choice(alphabet) for _ in range(length))
