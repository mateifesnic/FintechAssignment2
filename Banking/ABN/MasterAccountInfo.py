import requests
import json

# --- Configuration ---
# The variable is now a list to hold multiple tokens.
# Add new tokens to this list as you get them for different accounts.
ABN_ACCOUNT_ACCESS_TOKENS = [
    "YOUR_TOKEN_1", "YOUR_TOKEN_2"
]

# Your API Key for the application.
API_KEY = "YOUR_API_KEY"

# ABN AMRO Sandbox API endpoint
API_BASE_URL = "https://api-sandbox.abnamro.com"

# Paths to your ABN AMRO-provided certificates
ABN_CERT_FILE = '../PSD2TPPCertificate.crt'
ABN_KEY_FILE = '../PSD2TPPprivateKey.key'


def fetch_data_for_token(access_token):
    """
    Uses a single access token to fetch account data.
    This function contains the logic from the previous script.
    """
    # 1. Set up the required headers for the API calls
    headers = {
        'API-Key': API_KEY,
        'Authorization': f'Bearer {access_token}'
    }

    try:
        # 2. First, call the /consentinfo endpoint to get the authorized IBAN
        print("\nStep A: Fetching consent info to get the IBAN...")
        consent_info_url = f"{API_BASE_URL}/v1/consentinfo"

        consent_response = requests.get(
            consent_info_url,
            headers=headers,
            cert=(ABN_CERT_FILE, ABN_KEY_FILE)
        )
        consent_response.raise_for_status()
        consent_data = consent_response.json()
        iban = consent_data.get('iban')

        if not iban:
            print("Error: Could not retrieve IBAN for this token.")
            return

        print(f"   -> Success! This token is for IBAN: {iban}")

        # 3. Now, use the IBAN to get the transaction data
        print(f"\nStep B: Fetching transactions for IBAN {iban}...")
        transactions_url = f"{API_BASE_URL}/v1/accounts/{iban}/transactions"

        transactions_response = requests.get(
            transactions_url,
            headers=headers,
            cert=(ABN_CERT_FILE, ABN_KEY_FILE)
        )
        transactions_response.raise_for_status()
        transaction_data = transactions_response.json()

        print("   -> Success! Transaction data retrieved.")

        # 4. Display the final data for this specific token
        print("\n--- Final Account Data ---")
        print(json.dumps(transaction_data, indent=2))


    except requests.exceptions.HTTPError as e:
        print(f"\n--- An HTTP Error Occurred ---")
        print(f"Error: {e}")
        print(f"Response Body: {e.response.text}")
        print("This might mean your access token has expired.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")


# --- Run the Script ---
if __name__ == "__main__":
    print("--- Processing All ABN AMRO Access Tokens ---")

    # We now loop through each token in the list and process it.
    for index, token in enumerate(ABN_ACCOUNT_ACCESS_TOKENS):
        print("\n" + "=" * 50)
        # Use token's start and end to identify it without printing the whole thing
        print(f"Processing Token #{index + 1}: ({token[:4]}...{token[-4:]})")
        print("=" * 50)
        fetch_data_for_token(token)

    print("\n--- All tokens processed. ---")