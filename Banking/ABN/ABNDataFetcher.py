import requests
import json

# --- Configuration ---
# A list to hold multiple access tokens.
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

# Output file for the collected data
JSON_OUTPUT_FILE = 'abn_amro_data_output.json'


def fetch_data_for_token(access_token):
    """
    Uses a single access token to fetch account balance and transaction data,
    then returns it as a dictionary.
    """
    headers = {
        'API-Key': API_KEY,
        'Authorization': f'Bearer {access_token}'
    }

    try:
        # 1. Fetch consent info to get the authorized IBAN
        print("\nStep A: Fetching consent info to get the IBAN...")
        consent_info_url = f"{API_BASE_URL}/v1/consentinfo"
        consent_response = requests.get(consent_info_url, headers=headers, cert=(ABN_CERT_FILE, ABN_KEY_FILE))
        consent_response.raise_for_status()
        iban = consent_response.json().get('iban')

        if not iban:
            print("Error: Could not retrieve IBAN for this token. Skipping.")
            return None

        print(f"   -> Success! This token is for IBAN: {iban}")

        # 2. NEW: Use the IBAN to get balance information from the correct endpoint
        balance_data = {}
        try:
            print(f"Step B: Fetching balance for IBAN {iban}...")
            # Using the correct endpoint as per the documentation
            balances_url = f"{API_BASE_URL}/v1/accounts/{iban}/balances"
            balances_response = requests.get(balances_url, headers=headers, cert=(ABN_CERT_FILE, ABN_KEY_FILE))
            balances_response.raise_for_status()
            balance_data = balances_response.json()
            print("   -> Success! Balance data retrieved.")
        except requests.exceptions.HTTPError as e:
            print(f"   -> WARNING: Could not fetch balance. The API returned an error: {e}")
            print(f"   -> Continuing to fetch transactions...")

        # 3. Use the IBAN to get the transaction data
        print(f"Step C: Fetching transactions for IBAN {iban}...")
        transactions_url = f"{API_BASE_URL}/v1/accounts/{iban}/transactions"
        transactions_response = requests.get(transactions_url, headers=headers, cert=(ABN_CERT_FILE, ABN_KEY_FILE))
        transactions_response.raise_for_status()
        transaction_data = transactions_response.json()
        print("   -> Success! Transaction data retrieved.")

        # 4. Combine all the retrieved data into a single object
        # We merge the balance data and the transaction data.
        combined_data = {
            "account": balance_data,  # This now contains the balance info
            "transactions": transaction_data.get("transactions", [])
        }
        # Add other top-level keys from the transaction response, like nextPageKey
        for key, value in transaction_data.items():
            if key not in ["transactions", "accountNumber"]:  # accountNumber is already in the balance data
                combined_data[key] = value

        return iban, combined_data

    except requests.exceptions.HTTPError as e:
        print(f"\n--- An HTTP Error Occurred ---")
        print(f"Error: {e}")
        if e.response:
            print(f"Response Body: {e.response.text}")
        print("This might mean your access token has expired or consent is missing. Skipping token.")
        return None

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


# --- Run the Script ---
if __name__ == "__main__":
    print("--- Processing All ABN AMRO Access Tokens ---")

    # This dictionary will hold all the data from all tokens.
    all_abn_amro_data = {}

    for index, token in enumerate(ABN_ACCOUNT_ACCESS_TOKENS):
        print("\n" + "=" * 50)
        print(f"Processing Token #{index + 1}: ({token[:4]}...{token[-4:]})")
        print("=" * 50)

        # Fetch data for the current token
        result = fetch_data_for_token(token)

        # If data was fetched successfully, add it to our main dictionary
        if result:
            iban, data = result
            all_abn_amro_data[iban] = data

    # After processing all tokens, save the aggregated data to a JSON file
    if all_abn_amro_data:
        print(f"\n--- Saving all retrieved data to '{JSON_OUTPUT_FILE}' ---")
        with open(JSON_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(all_abn_amro_data, f, indent=2)
        print("    -> Success!")
    else:
        print("\n--- No data was retrieved. JSON file not created. ---")

    print("\n--- All tokens processed. ---")
