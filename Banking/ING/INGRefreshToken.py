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
CLIENT_ID = "YOUR_CLIENT_ID"
CERTIFICATE_SERIAL_NUMBER = "YOUR_SN"
CERT_PATH = "certs/"
SANDBOX_HOST = "https://api.sandbox.ing.com"
TOKEN_CSV_FILE = 'ing_tokens.csv'

# Filenames
ING_SIGNING_CERT_FILE = CERT_PATH + 'example_client_signing.cer'
ING_SIGNING_KEY_FILE = CERT_PATH + 'example_client_signing.key'
ING_TLS_CERT = CERT_PATH + 'example_client_tls.cer'
ING_TLS_KEY = CERT_PATH + 'example_client_tls.key'


def create_ing_signature_header(method, endpoint, key_id, headers_to_sign, body_bytes=b''):
    """Flexible function to create the complex Signature and other required headers for ING requests."""
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


def get_application_token():
    """Connects to ING and gets a new, valid Application Access Token."""
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
    signature_header_parts = {'keyId': f'"{CERTIFICATE_SERIAL_NUMBER}"', 'algorithm': '"rsa-sha256"',
                              'headers': f'"{signed_headers}"', 'signature': f'"{base64_signature}"'}
    auth_header = "Signature " + ",".join([f"{k}={v}" for k, v in signature_header_parts.items()])

    with open(ING_SIGNING_CERT_FILE, 'r') as f_cert:
        tpp_cert_header = f_cert.read().replace('-----BEGIN CERTIFICATE-----', '').replace('-----END CERTIFICATE-----',
                                                                                           '').replace('\n', '')

    headers = {
        'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded',
        'Digest': digest_header, 'Date': date_header,
        'TPP-Signature-Certificate': tpp_cert_header, 'Authorization': auth_header
    }

    response = requests.post(
        f"{SANDBOX_HOST}{endpoint}", headers=headers, data=payload, cert=(ING_TLS_CERT, ING_TLS_KEY)
    )
    response.raise_for_status()
    print("   -> Success!")
    return response.json()['access_token']


def refresh_customer_token(app_token, refresh_token):
    """Uses the Application Token and Refresh Token to get a new Customer Token."""
    print(f"\n--- Refreshing token: ...{refresh_token[-6:]} ---")

    endpoint = "/oauth2/token"
    body_params = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    encoded_body_bytes = "&".join([f"{k}={v}" for k, v in body_params.items()]).encode('utf-8')

    headers_to_sign = ['(request-target)', 'date', 'digest']
    headers = create_ing_signature_header("post", endpoint, CLIENT_ID, headers_to_sign, body_bytes=encoded_body_bytes)

    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    headers['Authorization'] = f'Bearer {app_token}'

    response = requests.post(
        f"{SANDBOX_HOST}{endpoint}",
        headers=headers,
        data=encoded_body_bytes,
        cert=(ING_TLS_CERT, ING_TLS_KEY)
    )
    response.raise_for_status()
    print("   -> Success! New access token received.")
    return response.json()


# REVISION: New function to get ALL refresh tokens from the CSV file
def get_all_refresh_tokens_from_csv(filename):
    """Reads the ing_tokens.csv file and returns a list of all refresh tokens."""
    print(f"--- Reading all refresh tokens from '{filename}' ---")
    tokens = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('refresh_token'):
                    tokens.append(row['refresh_token'])

            if not tokens:
                print(f"   -> No refresh tokens found in '{filename}'.")
                return []

            print(f"   -> Found {len(tokens)} token(s) to process.")
            return tokens

    except FileNotFoundError:
        print(f"\n--- ERROR: Could not find the token file: '{filename}' ---")
        return []


def update_token_in_csv(filename, old_refresh_token, new_token_data):
    """Finds the row with the old refresh token and updates it with the new access token."""
    print(f"--- Updating '{filename}' for token ...{old_refresh_token[-6:]} ---")
    try:
        with open(filename, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            headers = reader.fieldnames

        found = False
        for row in rows:
            if row['refresh_token'] == old_refresh_token:
                row['customer_access_token'] = new_token_data['access_token']
                row['timestamp'] = datetime.now(timezone.utc).isoformat()
                found = True
                break

        if not found:
            print(f"   -> ERROR: Could not find the old refresh token in '{filename}'. No update was made.")
            return

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

        print(f"   -> Success! File has been updated with the new access token.")

    except Exception as e:
        print(f"   -> ERROR: An error occurred while updating the CSV file: {e}")


if __name__ == "__main__":

    # REVISION: Get a list of all tokens instead of just the last one
    all_refresh_tokens = get_all_refresh_tokens_from_csv(TOKEN_CSV_FILE)

    if all_refresh_tokens:
        try:
            # Get one application token to be reused for all refreshes
            application_token = get_application_token()

            # REVISION: Loop through each token and refresh it
            for refresh_token_to_use in all_refresh_tokens:
                new_token_data = refresh_customer_token(application_token, refresh_token_to_use)
                update_token_in_csv(TOKEN_CSV_FILE, refresh_token_to_use, new_token_data)

            print("\n--- All tokens have been processed. ---")

        except requests.exceptions.HTTPError as e:
            print(f"\n--- An HTTP Error Occurred ---")
            print(f"Error: {e}")
            print(f"Response Body: {e.response.text}")
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")