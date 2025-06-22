# Save this file as e.g., abnamro_auth.py
import requests
from flask import Flask, request

# --- 1. CONFIGURE YOUR SERVER AND REDIRECT URI ---
# We will use port 8080.
# Make sure this exact URI is registered in your ABN AMRO developer portal.
REDIRECT_URI = "http://localhost:8080/auth"

# This will be our web server
app = Flask(__name__)

# This global variable will hold the code after we receive it
authorization_code = None


# --- 2. DEFINE THE SERVER'S BEHAVIOR ---

# This is the route that will catch the redirect from ABN AMRO
@app.route("/auth")
def handle_auth():
    """
    This function runs when the user is redirected back to our server.
    It captures the authorization code and stores it.
    """
    global authorization_code

    # Extract the 'code' from the URL query parameters (e.g., ?code=ABCDEFG...)
    code = request.args.get('code')

    if code:
        authorization_code = code
        print("------------------------------------------------------------------")
        print(f"SUCCESS: Authorization Code received: {authorization_code}")
        print("You can now close your browser and press Ctrl+C to stop this server.")
        print("------------------------------------------------------------------")
        return "<h1>Authorization Successful!</h1><p>Code received. You can close this browser tab and return to your terminal.</p>"
    else:
        return "<h1>Error</h1><p>No authorization code was found in the redirect.</p>", 400


# --- 3. MAIN EXECUTION BLOCK ---

if __name__ == '__main__':
    # Step A: Generate the unique authorization URL
    auth_endpoint = "https://auth-sandbox.abnamro.com/as/authorization.oauth2"
    params = {
        "scope": "psd2:account:balance:read psd2:account:transaction:read psd2:account:details:read",
        "client_id": "TPP_test",
        "response_type": "code",
        "flow": "code",
        "redirect_uri": REDIRECT_URI,  # Use the URI defined above
        "state": "SilverAdministration-123"
    }
    req = requests.Request('GET', auth_endpoint, params=params)
    authorization_url = req.prepare().url

    # Step B: Print the instructions and the URL
    print("\n--- INSTRUCTIONS ---")
    print("1. A web server is about to start on your machine.")
    print("2. Copy the URL below and paste it into your browser.")
    print("3. Log in and grant consent.")
    print("4. Your browser will be redirected back to the local server, and the code will be printed here.")
    print("\n--- URL ---")
    print(authorization_url)
    print("\n------------------------------------------------------------------")

    # Step C: Start the server and wait for the redirect
    # The server will run forever until you press Ctrl+C
    app.run(port=8080)