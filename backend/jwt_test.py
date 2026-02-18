import os, time, jwt
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

ak = os.getenv("KLING_ACCESS_KEY")
sk = os.getenv("KLING_SECRET_KEY")

print("DEBUG env_path:", env_path)
print("DEBUG AK:", repr(ak), type(ak))
print("DEBUG SK_set:", bool(sk))

if not ak or not sk:
    raise SystemExit("Brak KLING_ACCESS_KEY lub KLING_SECRET_KEY w .env (albo .env źle sformatowany).")

now = int(time.time())
headers = {"alg": "HS256", "typ": "JWT"}
payload = {
    "iss": str(AK),
    "iat": now,
    "nbf": now,
    "exp": now + 300,
}


token = jwt.encode(payload, sk, algorithm="HS256", headers=headers)
print(token)
