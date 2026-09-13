# Guess the Word

A web-based word-guessing game built with Python and FastAPI.

## Creating the initial Admin account

Public user registration always creates standard **Player** accounts (`PLAYER` role). Admin accounts must be created through controlled CLI provisioning:

```bash
python -m app.create_admin
```

When prompted, provide:
- **Admin username**: Minimum 5 characters (case-insensitive, normalized to lowercase)
- **Admin password**: Minimum 5 characters, containing at least:
  - one alphabetic character (`a-z`, `A-Z`)
  - one numeric character (`0-9`)
  - one of the allowed special characters: `$`, `%`, or `*`
- **Password confirmation**: Must match the entered password

### Security Details
- Password input uses `getpass` to prevent shoulder surfing (input is never echoed to the screen).
- Passwords are encrypted using Argon2id password hashing via `pwdlib`. Plaintext passwords are never persisted or logged.
- Admin accounts have access to administrative reporting and system metrics. Admin credentials should be kept secure and never committed to source control.
