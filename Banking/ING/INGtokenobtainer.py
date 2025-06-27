import requests
import json
import uuid
import base64
import hashlib
import csv
import os
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

# --- ING Sandbox Configuration ---
CLIENT_ID = "YOUR_CLIENT_ID"
CERTIFICATE_SERIAL_NUMBER = "YOUR_CERTIFICATE_SERIAL_NUMBER"
REDIRECT_URI = "https://www.example.com/"
SANDBOX_HOST = "https://api.sandbox.ing.com"

# --- Certificate Paths ---
CERT_PATH = "certs/"
ING_SIGNING_CERT_FILE = CERT_PATH + 'example_client_signing.cer'
ING_SIGNING_KEY_FILE = CERT_PATH + 'example_client_signing.key'
ING_TLS_CERT = CERT_PATH + 'example_client_tls.cer'
ING_TLS_KEY = CERT_PATH + 'example_client_tls.key'


def create_ing_signature_header(method, endpoint, key_id, headers_to_sign, body_bytes=b''):
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

    signature_header_parts = {'keyId': f'"{key_id}"', 'algorithm': '"rsa-sha256"',
                              'headers': f'"{" ".join(headers_to_sign)}"', 'signature': f'"{base64_signature}"'}
    final_signature_header = "Signature " + ",".join([f"{k}={v}" for k, v in signature_header_parts.items()])

    final_headers = {'Date': current_date, 'Digest': digest_header, 'X-Request-ID': request_id,
                     'Signature': final_signature_header}
    return final_headers


def main():
    print("--- Starting Full ING Data Fetch Flow ---")
    try:
        # === Step 1: Get Application Access Token ===
        print("\n--- Step 1: Getting Application Access Token ---")
        app_token_endpoint = "/oauth2/token"
        app_token_payload_str = "grant_type=client_credentials&client_id=" + CLIENT_ID
        headers_to_sign_app_token = ['(request-target)', 'date', 'digest']
        app_token_headers = create_ing_signature_header("post", app_token_endpoint, CERTIFICATE_SERIAL_NUMBER,
                                                        headers_to_sign_app_token,
                                                        body_bytes=app_token_payload_str.encode('utf-8'))
        app_token_headers['Authorization'] = app_token_headers.pop('Signature')
        app_token_headers['Content-Type'] = 'application/x-www-form-urlencoded'
        with open(ING_SIGNING_CERT_FILE, 'r') as f_cert:
            app_token_headers['TPP-Signature-Certificate'] = f_cert.read().replace('-----BEGIN CERTIFICATE-----',
                                                                                   '').replace(
                '-----END CERTIFICATE-----', '').replace('\n', '')

        app_token_response = requests.post(
            f"{SANDBOX_HOST}{app_token_endpoint}", headers=app_token_headers, data=app_token_payload_str,
            cert=(ING_TLS_CERT, ING_TLS_KEY)
        )
        app_token_response.raise_for_status()
        app_token_data = app_token_response.json()
        application_access_token = app_token_data['access_token']
        client_id_from_token = app_token_data['client_id']
        print(f"   -> Success! Received Application Access Token for client_id: {client_id_from_token}")

        # === Step 2: Get User Consent and Authorization Code ===
        print("\n--- Step 2: Get User Consent ---")
        auth_url = (
            f"https://myaccount.sandbox.ing.com/authorize/v2/NL?client_id={client_id_from_token}"
            "&scope=payment-accounts%3Abalances%3Aview%20payment-accounts%3Atransactions%3Aview"
            f"&redirect_uri={REDIRECT_URI}&response_type=code&state={uuid.uuid4()}"
        )
        print(
            "\nACTION REQUIRED: Please visit the URL below, confirm consent, and paste the 'code' from the final URL back here.")
        print(f"\n   {auth_url}\n")
        authorization_code = input("Paste the 'code' from the redirect URL here and press Enter: ")

        # === Step 3: Exchange Authorization Code for Customer Access Token ===
        print("\n--- Step 3: Exchanging code for Customer Access Token ---")
        cust_token_endpoint = "/oauth2/token"
        cust_token_payload = {"grant_type": "authorization_code", "code": authorization_code}
        encoded_body_bytes = "&".join([f"{k}={v}" for k, v in cust_token_payload.items()]).encode('utf-8')
        headers_to_sign_cust_token = ['(request-target)', 'date', 'digest']
        cust_token_headers = create_ing_signature_header("post", cust_token_endpoint, client_id_from_token,
                                                         headers_to_sign_cust_token, body_bytes=encoded_body_bytes)
        cust_token_headers['Content-Type'] = 'application/x-www-form-urlencoded'
        cust_token_headers['Authorization'] = f'Bearer {application_access_token}'

        cust_token_response = requests.post(
            f"{SANDBOX_HOST}{cust_token_endpoint}", headers=cust_token_headers, data=encoded_body_bytes,
            cert=(ING_TLS_CERT, ING_TLS_KEY)
        )
        cust_token_response.raise_for_status()
        token_data = cust_token_response.json()
        customer_access_token = token_data['access_token']
        # REVISION: Capture the refresh_token from the response
        customer_refresh_token = token_data['refresh_token']
        print("   -> Success! Received Customer Access Token and Refresh Token.")

        # === Step 4: Get Account Info ===
        print("\n--- Step 4: Fetching Account Info to get IBAN ---")
        accounts_endpoint = "/v3/accounts"
        headers_for_get_accounts = ['(request-target)', 'date', 'digest', 'x-request-id']
        data_headers = create_ing_signature_header("get", accounts_endpoint, client_id_from_token,
                                                   headers_for_get_accounts)
        data_headers['Authorization'] = f'Bearer {customer_access_token}'
        data_headers['Accept'] = 'application/json'

        acc_response = requests.get(
            f"{SANDBOX_HOST}{accounts_endpoint}", headers=data_headers, cert=(ING_TLS_CERT, ING_TLS_KEY)
        )
        acc_response.raise_for_status()
        accounts = acc_response.json()['accounts']
        print("   -> Success! Account info retrieved.")

        consented_account = accounts[0]
        account_iban = consented_account.get('iban') or consented_account.get('maskedPan')
        account_name = consented_account.get('name')

        # === Step 5: Save Tokens to CSV ===
        print("\n--- Step 5: Saving tokens to CSV file ---")
        csv_file_name = 'ing_tokens.csv'
        # REVISION: Add 'refresh_token' to the CSV headers
        csv_headers = ['timestamp', 'iban', 'account_name', 'customer_access_token', 'refresh_token']

        file_exists = os.path.exists(csv_file_name)

        with open(csv_file_name, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=csv_headers)
            if not file_exists:
                writer.writeheader()

            # REVISION: Write the refresh_token to the CSV file
            writer.writerow({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'iban': account_iban,
                'account_name': account_name,
                'customer_access_token': customer_access_token,
                'refresh_token': customer_refresh_token
            })

        print(f"   -> Success! Tokens for account '{account_iban}' saved to '{csv_file_name}'.")

    except requests.exceptions.HTTPError as e:
        print(f"\n--- An HTTP Error Occurred ---")
        print(f"Error: {e}")
        print(f"Response Body: {e.response.text}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")


if __name__ == "__main__":
    main()