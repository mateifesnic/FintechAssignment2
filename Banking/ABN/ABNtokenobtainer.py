import requests
import os
from flask import Flask, request, redirect, session, url_for, jsonify

# --- Flask App Setup ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- ABN AMRO Sandbox Configuration (FINAL) ---
API_KEY = "YOUR_API_KEY"
CLIENT_ID = "TPP_test"
REDIRECT_URI = "https://localhost/auth"

# URLs from the documentation
AUTH_URL = "https://auth-sandbox.abnamro.com/as/authorization.oauth2"
TOKEN_URL = "https://auth-mtls-sandbox.abnamro.com/as/token.oauth2"
API_BASE_URL = "https://api-sandbox.abnamro.com"

# Paths to your ABN AMRO and local SSL certificates
ABN_CERT_FILE = '../PSD2TPPCertificate.crt'
ABN_KEY_FILE = '../PSD2TPPprivateKey.key'
LOCAL_CERT_FILE = '../../cert.pem'
LOCAL_KEY_FILE = '../../key.pem'


# --- 1. Start the Authorization Flow ---
@app.route("/")
def homepage():
    return '<a href="/login">Login with ABN AMRO</a>'


@app.route("/login")
def login():
    scopes = "psd2:account:balance:read+psd2:account:transaction:read+psd2:account:details:read"
    auth_request_url = (
        f"{AUTH_URL}?scope={scopes}&client_id={CLIENT_ID}"
        f"&response_type=code&redirect_uri={REDIRECT_URI}&flow=code"
    )
    return redirect(auth_request_url)


# --- 2. Handle the Callback and Exchange Code for a Token ---
@app.route("/auth")
def auth():
    try:
        auth_code = request.args['code']
        session['authorization_code'] = auth_code

        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        data = {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI
        }

        response = requests.post(
            TOKEN_URL,
            headers=headers,
            data=data,
            cert=(ABN_CERT_FILE, ABN_KEY_FILE)
        )
        response.raise_for_status()
        token_data = response.json()

        session['access_token'] = token_data['access_token']
        session['refresh_token'] = token_data['refresh_token']

        return redirect(url_for('get_account_data'))

    except Exception as e:
        error_text = ""
        if 'response' in locals() and hasattr(response, 'text'):
            error_text = response.text
        return f"An error occurred: {e}<br/>Response from server: {error_text}"


# --- 3. Use the Access Token to Fetch and Display ALL Data ---
@app.route("/get_account_data")
def get_account_data():
    if 'access_token' not in session:
        return "Not authorized. Please <a href='/login'>login</a> first.", 401

    access_token = session.get('access_token')
    authorization_code = session.get('authorization_code')

    headers = {
        'API-Key': API_KEY,
        'Authorization': f'Bearer {access_token}'
    }

    try:
        consent_info_url = f"{API_BASE_URL}/v1/consentinfo"
        consent_response = requests.get(consent_info_url, headers=headers, cert=(ABN_CERT_FILE, ABN_KEY_FILE))
        consent_response.raise_for_status()
        consent_data = consent_response.json()
        iban = consent_data.get('iban')

        if not iban:
            return "Could not retrieve IBAN from consent info.", 500

        transactions_url = f"{API_BASE_URL}/v1/accounts/{iban}/transactions"
        transactions_response = requests.get(transactions_url, headers=headers, cert=(ABN_CERT_FILE, ABN_KEY_FILE))
        transactions_response.raise_for_status()

        transaction_data = transactions_response.json()

        final_output = {
            "debug_information": {
                "authorization_code_from_step_1": authorization_code,
                "access_token_from_step_2": access_token
            },
            "account_data_from_step_3": transaction_data
        }

        return jsonify(final_output)

    except Exception as e:
        error_text = ""
        if 'consent_response' in locals() and hasattr(consent_response, 'text'):
            error_text = consent_response.text
        if 'transactions_response' in locals() and hasattr(transactions_response, 'text'):
            error_text = transactions_response.text
        return f"An error occurred while fetching data: {e}<br/>Response from server: {error_text}"


# --- Run the Flask App with SSL on Port 443 ---
if __name__ == "__main__":
    try:
        app.run(
            port=443,
            host='localhost',
            debug=True,
            ssl_context=(LOCAL_CERT_FILE, LOCAL_KEY_FILE)
        )
    except PermissionError:
        print("\n" + "=" * 60)
        print("PERMISSION ERROR: You must run this script with administrator")
        print("privileges to use port 443.")
        print("On macOS/Linux: sudo python your_script_name.py")
        print("On Windows: Run Command Prompt or PowerShell as Administrator.")
        print("=" * 60)
    except FileNotFoundError:
        print("\n" + "=" * 60)
        print("CERTIFICATE FILE NOT FOUND: Make sure 'cert.pem', 'key.pem',")
        print("'PSD2TPPCertificate.crt', and 'PSD2TPPprivateKey.key' are in")
        print("the same folder as this script.")
        print("=" * 60)