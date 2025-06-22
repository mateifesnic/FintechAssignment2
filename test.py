import requests
import webbrowser

# --- Configuration ---
# IMPORTANT: Replace these placeholder values with your actual credentials
# from the ABN AMRO Developer Portal. For production applications, it is
# strongly recommended to load credentials securely instead of hardcoding them.

CLIENT_ID = "4LTHwZWEbKwEpnLeR25Gx45R4EvdOczA"
CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE"

# --- ABN AMRO Sandbox URLs ---
REDIRECT_URI = "https://localhost/auth"
SCOPES = "psd2:account:balance:read psd2:account:transaction:read"
AUTH_BASE_URL = "https://auth-sandbox.abnamro.com/as/authorization.oauth2"
TOKEN_URL = "https://api-sandbox.abnamro.com/v1/oauth/token"
API_BASE_URL = "https://api-sandbox.abnamro.com"


def main():
    """
    Main function to run the ABN AMRO API flow.
    """
    if CLIENT_ID == "YOUR_API_KEY_HERE" or CLIENT_SECRET == "YOUR_CLIENT_SECRET_HERE":
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! PLEASE REPLACE THE PLACEHOLDER CREDENTIALS FIRST !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
        return

    # --- Step 1: Generate Authorization URL and Get Code ---
    auth_params = {
        'scope': SCOPES,
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'state': 'myapplication123'  # Use a random string in a real app
    }

    # Use requests to properly build the URL with encoded parameters
    request_builder = requests.Request('GET', AUTH_BASE_URL, params=auth_params)
    auth_url = request_builder.prepare().url

    print("=" * 80)
    print("STEP 1: GET USER CONSENT")
    print("=" * 80)
    print("A browser window will now open.")
    print("1. Log in with your sandbox credentials.")
    print("2. Grant consent to the application.")
    print("3. Your browser will be redirected to a URL like 'https://localhost/auth?code=...'.")
    print("4. Copy the entire 'code' value from that URL.\n")

    webbrowser.open(auth_url)

    authorization_code = input("Please paste the 'code' from your browser's address bar here and press Enter: ")

    if not authorization_code:
        print("No authorization code provided. Exiting.")
        return

    # --- Step 2: Exchange Authorization Code for an Access Token ---
    print("\n" + "=" * 80)
    print("STEP 2: EXCHANGING CODE FOR ACCESS TOKEN")
    print("=" * 80)

    token_data = {
        'grant_type': 'authorization_code',
        'code': authorization_code.strip(),
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }

    try:
        response = requests.post(TOKEN_URL, data=token_data)
        response.raise_for_status()  # This will raise an exception for HTTP errors (4xx, 5xx)

        token_info = response.json()
        access_token = token_info.get('access_token')

        if not access_token:
            print("Error: Could not retrieve access token.")
            print("Response:", response.text)
            return

        print("Successfully obtained access token!")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while requesting the token: {e}")
        if e.response:
            print("Response content:", e.response.text)
        return

    # --- Step 3: Make a Request to the Account Information API ---
    print("\n" + "=" * 80)
    print("STEP 3: CALLING THE API TO GET ACCOUNTS")
    print("=" * 80)

    api_headers = {
        'Authorization': f'Bearer {access_token}',
        'API-Key': CLIENT_ID,
        'Accept': 'application/json'
    }

    try:
        accounts_url = f"{API_BASE_URL}/v1/accounts"
        api_response = requests.get(accounts_url, headers=api_headers)
        api_response.raise_for_status()

        account_data = api_response.json()

        print("SUCCESS! Received account data from the API:\n")
        print(account_data)

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the API call: {e}")
        if e.response:
            print("Response content:", e.response.text)


if __name__ == "__main__":
    main()