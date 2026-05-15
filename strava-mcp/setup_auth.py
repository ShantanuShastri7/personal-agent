"""
One-time Strava OAuth setup. Run this once to get your tokens.
Usage: python setup_auth.py
"""

import httpx
import os
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv, set_key

load_dotenv("../.env")

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
ENV_PATH = "../.env"

auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Auth successful! You can close this tab.")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing code parameter.")

    def log_message(self, format, *args):
        pass


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in .env first.")
        return

    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&approval_prompt=force"
        f"&scope=read,activity:read_all"
    )

    print(f"Opening browser for Strava authorization...")
    webbrowser.open(auth_url)
    print(f"Waiting for callback on port {REDIRECT_PORT}...")

    server = HTTPServer(("localhost", REDIRECT_PORT), CallbackHandler)
    server.handle_request()

    if not auth_code:
        print("ERROR: No authorization code received.")
        return

    print("Exchanging code for tokens...")
    response = httpx.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": auth_code,
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    tokens = response.json()

    set_key(ENV_PATH, "STRAVA_ACCESS_TOKEN", tokens["access_token"])
    set_key(ENV_PATH, "STRAVA_REFRESH_TOKEN", tokens["refresh_token"])
    set_key(ENV_PATH, "STRAVA_TOKEN_EXPIRES_AT", str(tokens["expires_at"]))

    print("Tokens saved to .env successfully.")
    print(f"Athlete ID: {tokens['athlete']['id']}")
    print(f"Athlete: {tokens['athlete']['firstname']} {tokens['athlete']['lastname']}")


if __name__ == "__main__":
    main()
