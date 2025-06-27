import requests
import json
import csv
import os
import uuid
import base64
import hashlib
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

# --- ING Sandbox Configuration ---
# These are placeholder values. Replace them with your actual credentials.
CLIENT_ID = "YOUR_CLIENT_ID"
CERTIFICATE_SERIAL_NUMBER = "YOUR_SN"
REDIRECT_URI = "https://www.example.com/"
SANDBOX_HOST = "https://api.sandbox.ing.com"
TOKEN_CSV_FILE = 'ing_tokens.csv'
DATA_OUTPUT_FILE = 'ing_data_output.json'

# --- Certificate Paths ---
# Make sure these paths are correct for your local setup.
# You will need to generate these certificate files to run the script.
CERT_PATH = "certs/"
ING_SIGNING_CERT_FILE = CERT_PATH + 'example_client_signing.cer'
ING_SIGNING_KEY_FILE = CERT_PATH + 'example_client_signing.key'
ING_TLS_CERT = CERT_PATH + 'example_client_tls.cer'
ING_TLS_KEY = CERT_PATH + 'example_client_tls.key'


def create_ing_signature_header(method, endpoint, key_id, headers_to_sign, body_bytes=b''):
    """
    Flexible function to create the complex Signature and other required headers for ING API requests.

    Args:
        method (str): The HTTP method (e.g., 'get', 'post').
        endpoint (str): The API endpoint path (e.g., '/oauth2/token').
        key_id (str): The identifier for the key, usually the client ID or certificate serial number.
        headers_to_sign (list): A list of header names that should be included in the signature.
        body_bytes (bytes, optional): The request body as bytes. Defaults to b''.

    Returns:
        dict: A dictionary of headers required for the request, including the generated Signature.
    """
    current_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    request_id = str(uuid.uuid4())
    digest = hashlib.sha256(body_bytes).digest()
    digest_header = "SHA-256=" + base64.b64encode(digest).decode('utf-8')

    signing_string_parts = []
    for header_name in headers_to_sign:
        if header_name == '(request-target)':
            signing_string_parts.append(f"(request-target): {method.lower()} {endpoint}")
        elif header_name == 'date':
            signing_string_parts.append(f"date: {current_date}")
        elif header_name == 'digest':
            signing_string_parts.append(f"digest: {digest_header}")
        elif header_name == 'x-request-id':
            signing_string_parts.append(f"x-request-id: {request_id}")

    signing_string = "\n".join(signing_string_parts)

    with open(ING_SIGNING_KEY_FILE, "rb") as key_file:
        private_key = load_pem_private_key(key_file.read(), password=None)

    signature_bytes = private_key.sign(signing_string.encode('utf-8'), padding.PKCS1v15(), hashes.SHA256())
    base64_signature = base64.b64encode(signature_bytes).decode('utf-8')

    signature_header_parts = {
        'keyId': f'"{key_id}"',
        'algorithm': '"rsa-sha256"',
        'headers': f'"{" ".join(headers_to_sign)}"',
        'signature': f'"{base64_signature}"'
    }

    final_signature_header = "Signature " + ",".join([f"{k}={v}" for k, v in signature_header_parts.items()])

    final_headers = {
        'Date': current_date,
        'Digest': digest_header,
        'X-Request-ID': request_id,
        'Signature': final_signature_header
    }
    return final_headers


def get_application_token():
    """
    Connects to the ING API to acquire an Application Access Token.
    This token is used for subsequent API calls that are not customer-specific.

    Returns:
        str: The application access token.

    Raises:
        requests.exceptions.HTTPError: If the API request fails.
    """
    print("--- Getting a new Application Access Token (once for all refreshes) ---")
    endpoint = "/oauth2/token"
    payload = "grant_type=client_credentials&client_id=" + CLIENT_ID
    digest_header = "SHA-256=" + base64.b64encode(hashlib.sha256(payload.encode('utf-8')).digest()).decode('utf-8')
    date_header = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

    signing_string = (f"(request-target): post {endpoint}\n"
                      f"date: {date_header}\n"
                      f"digest: {digest_header}")

    with open(ING_SIGNING_KEY_FILE, "rb") as key_file:
        private_key = load_pem_private_key(key_file.read(), password=None)

    signature_bytes = private_key.sign(signing_string.encode('utf-8'), padding.PKCS1v15(), hashes.SHA256())
    base64_signature = base64.b64encode(signature_bytes).decode('utf-8')

    signed_headers = "(request-target) date digest"
    signature_header_parts = {
        'keyId': f'"{CERTIFICATE_SERIAL_NUMBER}"',
        'algorithm': '"rsa-sha256"',
        'headers': f'"{signed_headers}"',
        'signature': f'"{base64_signature}"'
    }
    auth_header = "Signature " + ",".join([f"{k}={v}" for k, v in signature_header_parts.items()])

    with open(ING_SIGNING_CERT_FILE, 'r') as f_cert:
        tpp_cert_header = f_cert.read().replace('-----BEGIN CERTIFICATE-----', '').replace('-----END CERTIFICATE-----',
                                                                                           '').replace('\n', '')

    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Digest': digest_header,
        'Date': date_header,
        'TPP-Signature-Certificate': tpp_cert_header,
        'Authorization': auth_header
    }

    response = requests.post(f"{SANDBOX_HOST}{endpoint}", headers=headers, data=payload,
                             cert=(ING_TLS_CERT, ING_TLS_KEY))
    response.raise_for_status()
    print("    -> Success!")
    return response.json()['access_token']


def refresh_customer_token(app_token, refresh_token):
    """
    Uses the Application Token and a customer's Refresh Token to get a new Customer Access Token.

    Args:
        app_token (str): The valid application access token.
        refresh_token (str): The customer's refresh token.

    Returns:
        dict: A dictionary containing the new access token and other related data.

    Raises:
        requests.exceptions.HTTPError: If the API request fails.
    """
    print(f"\n--- Refreshing token: ...{refresh_token[-6:]} ---")
    endpoint = "/oauth2/token"
    body_params = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    encoded_body_bytes = "&".join([f"{k}={v}" for k, v in body_params.items()]).encode('utf-8')

    headers_to_sign = ['(request-target)', 'date', 'digest']
    headers = create_ing_signature_header("post", endpoint, CLIENT_ID, headers_to_sign, body_bytes=encoded_body_bytes)
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    headers['Authorization'] = f'Bearer {app_token}'

    response = requests.post(f"{SANDBOX_HOST}{endpoint}", headers=headers, data=encoded_body_bytes,
                             cert=(ING_TLS_CERT, ING_TLS_KEY))
    response.raise_for_status()
    print("    -> Success! New customer access token received.")
    return response.json()


def fetch_data_with_token(customer_token):
    """
    Fetches account, balance, and transaction data using a customer access token.

    Args:
        customer_token (str): The customer's valid access token.

    Returns:
        dict: A dictionary containing the fetched accounts, balances, and transactions.

    Raises:
        requests.exceptions.HTTPError: If an API request fails.
    """
    print("--- Fetching account, balance, and transaction data with new token ---")
    accounts_endpoint = "/v3/accounts"

    headers = create_ing_signature_header("get", accounts_endpoint, CLIENT_ID,
                                          ['(request-target)', 'date', 'digest', 'x-request-id'])
    headers['Authorization'] = f'Bearer {customer_token}'
    headers['Accept'] = 'application/json'

    acc_response = requests.get(f"{SANDBOX_HOST}{accounts_endpoint}", headers=headers, cert=(ING_TLS_CERT, ING_TLS_KEY))
    acc_response.raise_for_status()
    accounts = acc_response.json()['accounts']
    print(f"    -> Success! Found {len(accounts)} account(s).")

    all_transactions = []
    all_balances = []

    for account in accounts:
        account_identifier = account.get('iban') or account.get('maskedPan')

        # --- Fetch Balances ---
        print(f"    -> Fetching balances for {account_identifier}...")
        try:
            if 'balances' in account['_links'] and account['_links']['balances']:
                balances_endpoint = account['_links']['balances']['href']
                balance_headers = create_ing_signature_header("get", balances_endpoint, CLIENT_ID,
                                                              ['(request-target)', 'date', 'digest', 'x-request-id'])
                balance_headers['Authorization'] = f'Bearer {customer_token}'
                balance_response = requests.get(f"{SANDBOX_HOST}{balances_endpoint}", headers=balance_headers,
                                                cert=(ING_TLS_CERT, ING_TLS_KEY))
                balance_response.raise_for_status()
                all_balances.append(balance_response.json())
                print(f"       -> Success!")
            else:
                print(f"       -> WARNING: No balances link found for account {account_identifier}.")
        except requests.exceptions.HTTPError as e:
            print(f"       -> WARNING: Could not fetch balances for {account_identifier}. Server returned error: {e}")
            print(f"       -> Skipping balances for this account and continuing.")

            # --- Fetch Transactions ---
        print(f"    -> Fetching transactions for {account_identifier}...")
        try:
            if 'transactions' in account['_links'] and account['_links']['transactions']:
                transactions_endpoint = account['_links']['transactions']['href']
                trans_headers = create_ing_signature_header("get", transactions_endpoint, CLIENT_ID,
                                                            ['(request-target)', 'date', 'digest', 'x-request-id'])
                trans_headers['Authorization'] = f'Bearer {customer_token}'
                trans_response = requests.get(f"{SANDBOX_HOST}{transactions_endpoint}", headers=trans_headers,
                                              cert=(ING_TLS_CERT, ING_TLS_KEY))
                trans_response.raise_for_status()
                all_transactions.append(trans_response.json())
                print(f"       -> Success!")
            else:
                print(f"       -> WARNING: No transactions link found for account {account_identifier}.")
        except requests.exceptions.HTTPError as e:
            print(
                f"       -> WARNING: Could not fetch transactions for {account_identifier}. Server returned error: {e}")
            print(f"       -> Skipping this account and continuing.")

    print("    -> Finished fetching data for this token.")
    return {"accounts": accounts, "balances": all_balances, "transactions": all_transactions}


def get_all_tokens_from_csv(filename):
    """
    Reads a CSV file and returns all token data as a list of dictionaries.

    Args:
        filename (str): The path to the CSV file.

    Returns:
        list: A list of dictionaries, where each dictionary represents a row from the CSV.
    """
    print(f"--- Reading all tokens from '{filename}' ---")
    if not os.path.exists(filename):
        print(f"\n--- ERROR: Could not find the token file: '{filename}' ---")
        print("Please ensure the file exists and contains your refresh tokens.")
        return []

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = list(csv.DictReader(f))
        if not reader:
            print(f"    -> No tokens found in '{filename}'.")
            return []
        print(f"    -> Found {len(reader)} token(s) to process.")
        return reader
    except Exception as e:
        print(f"    -> ERROR: An error occurred while reading the CSV file: {e}")
        return []


def update_csv_file(filename, updated_rows):
    """
    Writes a list of dictionaries back to a CSV file, overwriting the existing file.

    Args:
        filename (str): The path to the CSV file.
        updated_rows (list): A list of dictionaries to write to the file.
    """
    print(f"--- Saving all updated tokens back to '{filename}' ---")
    try:
        if not updated_rows:
            return
        headers = updated_rows[0].keys()
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(updated_rows)
        print("    -> Success! File has been updated.")
    except Exception as e:
        print(f"    -> ERROR: An error occurred while updating the CSV file: {e}")


if __name__ == "__main__":

    # Ensure the certificates directory exists
    if not os.path.exists(CERT_PATH):
        print(f"--- WARNING: Certificate directory '{CERT_PATH}' not found. ---")
        print("--- This script will fail without valid certificate files. ---")

    token_rows = get_all_tokens_from_csv(TOKEN_CSV_FILE)

    if token_rows:
        all_retrieved_data = {}
        try:
            application_token = get_application_token()

            for i, row in enumerate(token_rows):
                old_refresh_token = row['refresh_token']
                iban = row['iban']
                print("\n" + "=" * 60)
                print(f"Processing Token for account: {iban} ({i + 1} of {len(token_rows)})")
                print("=" * 60)

                new_token_data = refresh_customer_token(application_token, old_refresh_token)
                new_customer_token = new_token_data['access_token']

                # Update the row with the latest customer token and timestamp
                row['customer_access_token'] = new_customer_token
                row['timestamp'] = datetime.now(timezone.utc).isoformat()

                # Fetch all data (accounts, balances, transactions)
                retrieved_data = fetch_data_with_token(new_customer_token)
                all_retrieved_data[iban] = retrieved_data

                # After the loop, update the CSV and save the data
            update_csv_file(TOKEN_CSV_FILE, token_rows)

            print(f"\n--- Saving all retrieved data to '{DATA_OUTPUT_FILE}' ---")
            with open(DATA_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_retrieved_data, f, indent=2)
            print("    -> Success!")

        except FileNotFoundError:
            print("\n--- A FileNotFoundError occurred. ---")
            print(f"Please make sure the certificate files exist at the specified paths:")
            print(f"  - Signing Cert: {ING_SIGNING_CERT_FILE}")
            print(f"  - Signing Key:  {ING_SIGNING_KEY_FILE}")
            print(f"  - TLS Cert:     {ING_TLS_CERT}")
            print(f"  - TLS Key:      {ING_TLS_KEY}")
        except requests.exceptions.HTTPError as e:
            print(f"\n--- An HTTP Error Occurred ---")
            print(f"Error: {e}")
            print(f"Response Body: {e.response.text}")
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")
