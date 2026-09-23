from getpass import getpass

from argon2 import PasswordHasher


password = getpass("New administrator password: ")
confirmation = getpass("Confirm password: ")
if len(password) < 10:
    raise SystemExit("Use at least 10 characters")
if password != confirmation:
    raise SystemExit("Passwords did not match")
print(PasswordHasher().hash(password))
