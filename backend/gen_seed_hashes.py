"""One-off: emit bcrypt hashes for the seeded demo users."""
import bcrypt

for name in ("dane", "nick", "priya"):
    h = bcrypt.hashpw(b"19691969", bcrypt.gensalt(rounds=10)).decode()
    assert bcrypt.checkpw(b"19691969", h.encode())
    print(f"{name}: {h}")
