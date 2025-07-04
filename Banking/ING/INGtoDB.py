import json
import sqlite3
import os
from datetime import datetime, timezone

# --- Configuration ---
# The JSON file generated by your original script
JSON_INPUT_FILE = 'ing_data_output.json'
# The SQLite database file to create/update
DB_FILE = 'ing_data.db'


def discover_schema(all_data):
    """
    Scans the entire JSON data object to discover all unique keys for balances and transactions.
    This creates a complete "superset" of all possible columns.
    """
    print("--- Discovering database schema from JSON data ---")
    balance_keys = set()
    transaction_keys = set()

    for data in all_data.values():
        # Discover balance keys, flattening the nested amount
        for balance_container in data.get('balances', []):
            for balance in balance_container.get('balances', []):
                if 'balanceAmount' in balance:
                    for k in balance['balanceAmount']:
                        balance_keys.add(k)
                for k in balance:
                    if k != 'balanceAmount':
                        balance_keys.add(k)

        # Discover transaction keys, handling both regular and card transactions
        for tx_container in data.get('transactions', []):
            is_card_tx = 'cardTransactions' in tx_container
            transactions_data = tx_container.get('cardTransactions') if is_card_tx else tx_container.get('transactions')

            for tx_list in transactions_data.values():
                for tx in tx_list:
                    # Flatten nested transactionAmount
                    if 'transactionAmount' in tx:
                        for k in tx['transactionAmount']:
                            transaction_keys.add(k)
                    # Flatten nested account details (for creditors/debtors)
                    if 'creditorAccount' in tx:
                        for k in tx['creditorAccount']:
                            transaction_keys.add(f"creditorAccount_{k}")
                    if 'debtorAccount' in tx:
                        for k in tx['debtorAccount']:
                            transaction_keys.add(f"debtorAccount_{k}")

                    # Add all other top-level keys
                    for k in tx:
                        if k not in ['transactionAmount', 'creditorAccount', 'debtorAccount']:
                            # Rename cardTransactionId to transactionId for consistency
                            key_to_add = 'transactionId' if k == 'cardTransactionId' else k
                            transaction_keys.add(key_to_add)

    print(f"    -> Found {len(balance_keys)} unique balance fields.")
    print(f"    -> Found {len(transaction_keys)} unique transaction fields.")
    return sorted(list(balance_keys)), sorted(list(transaction_keys))


def setup_database(db_file, balance_columns, transaction_columns):
    """Initializes the database and creates tables with a dynamically generated schema."""
    print(f"--- Setting up database at '{db_file}' ---")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # --- Accounts table (static schema is fine) ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS accounts (
        resourceId TEXT PRIMARY KEY,
        iban TEXT,
        maskedPan TEXT,
        name TEXT,
        currency TEXT,
        product TEXT,
        fetch_timestamp TEXT
    )''')

    # --- Dynamically create Balances table ---
    # Use 'TEXT' for all discovered columns for simplicity; SQLite handles type affinity.
    balance_cols_sql = ", ".join([f'"{col}" TEXT' for col in balance_columns])
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS balances (
        balance_id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_resourceId TEXT NOT NULL,
        {balance_cols_sql},
        FOREIGN KEY (account_resourceId) REFERENCES accounts (resourceId)
    )''')

    # --- Dynamically create Transactions table ---
    transaction_cols_sql = ", ".join([f'"{col}" TEXT' for col in transaction_columns])
    cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_pk INTEGER PRIMARY KEY AUTOINCREMENT,
        account_resourceId TEXT NOT NULL,
        status TEXT,
        {transaction_cols_sql},
        FOREIGN KEY (account_resourceId) REFERENCES accounts (resourceId),
        UNIQUE(transactionId)
    )''')

    conn.commit()
    print("    -> Dynamic database schema created successfully.")
    return conn, cursor


def load_json_data(json_file):
    """Loads and parses the data from the specified JSON file."""
    print(f"--- Reading data from '{json_file}' ---")
    if not os.path.exists(json_file):
        print(f"!!! ERROR: JSON file not found at '{json_file}'. Please run the main script first. !!!")
        return None
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print("    -> JSON file loaded successfully.")
        return data
    except json.JSONDecodeError as e:
        print(f"!!! ERROR: Could not parse JSON file. It may be corrupt. Error: {e} !!!")
        return None


def save_data_to_db(conn, cursor, all_data, balance_columns, transaction_columns):
    """Iterates through the data and saves it, matching records to the dynamic schema."""
    print(f"--- Saving all collected data to the database ---")
    fetch_time = datetime.now(timezone.utc).isoformat()

    # --- 1. Save Accounts and create lookup maps ---
    iban_to_resourceId = {}
    pan_to_resourceId = {}
    for iban, data in all_data.items():
        for account in data.get('accounts', []):
            resource_id = account.get('resourceId')
            if account.get('iban'):
                iban_to_resourceId[account.get('iban')] = resource_id
            if account.get('maskedPan'):
                pan_to_resourceId[account.get('maskedPan')] = resource_id

            cursor.execute('''
            INSERT OR REPLACE INTO accounts (resourceId, iban, maskedPan, name, currency, product, fetch_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                resource_id, account.get('iban'), account.get('maskedPan'), account.get('name'),
                account.get('currency'), account.get('product'), fetch_time
            ))
    conn.commit()

    # --- 2. Process and save Balances ---
    balance_placeholders = ', '.join(['?'] * (len(balance_columns) + 1))  # +1 for account_resourceId
    balance_insert_sql = f"INSERT OR IGNORE INTO balances (account_resourceId, {', '.join(balance_columns)}) VALUES ({balance_placeholders})"

    for data in all_data.values():
        for balance_container in data.get('balances', []):
            account_details = balance_container.get('account', {})
            account_id = iban_to_resourceId.get(account_details.get('iban')) or pan_to_resourceId.get(
                account_details.get('maskedPan'))
            if not account_id: continue

            for balance in balance_container.get('balances', []):
                flat_balance = {k: v for k, v in balance.items() if k != 'balanceAmount'}
                flat_balance.update(balance.get('balanceAmount', {}))

                values = [account_id] + [flat_balance.get(col) for col in balance_columns]
                cursor.execute(balance_insert_sql, values)

    # --- 3. Process and save all Transactions ---
    transaction_placeholders = ', '.join(['?'] * (len(transaction_columns) + 2))  # +2 for account_resourceId, status
    transaction_insert_sql = f"INSERT OR IGNORE INTO transactions (account_resourceId, status, {', '.join(transaction_columns)}) VALUES ({transaction_placeholders})"

    for data in all_data.values():
        for tx_container in data.get('transactions', []):
            is_card_tx = 'cardTransactions' in tx_container
            account_details = tx_container.get('cardAccount') if is_card_tx else tx_container.get('account')
            transactions_data = tx_container.get('cardTransactions') if is_card_tx else tx_container.get('transactions')

            if not account_details: continue
            account_id = pan_to_resourceId.get(
                account_details.get('maskedPan')) if is_card_tx else iban_to_resourceId.get(account_details.get('iban'))
            if not account_id: continue

            for status, tx_list in transactions_data.items():
                for tx in tx_list:
                    flat_tx = {k: v for k, v in tx.items() if
                               k not in ['transactionAmount', 'creditorAccount', 'debtorAccount']}
                    flat_tx.update(tx.get('transactionAmount', {}))
                    flat_tx.update({f"creditorAccount_{k}": v for k, v in tx.get('creditorAccount', {}).items()})
                    flat_tx.update({f"debtorAccount_{k}": v for k, v in tx.get('debtorAccount', {}).items()})

                    if 'cardTransactionId' in flat_tx:
                        flat_tx['transactionId'] = flat_tx.pop('cardTransactionId')

                    values = [account_id, status] + [flat_tx.get(col) for col in transaction_columns]
                    cursor.execute(transaction_insert_sql, values)

    conn.commit()
    print("    -> All data saved to database successfully.")


if __name__ == "__main__":
    # Step 1: Load the data from the JSON file
    retrieved_data = load_json_data(JSON_INPUT_FILE)

    if retrieved_data:
        db_conn = None
        try:
            # Step 2: Discover the complete schema from the loaded data
            balance_cols, transaction_cols = discover_schema(retrieved_data)

            # Step 3: Set up the database with the discovered schema
            db_conn, db_cursor = setup_database(DB_FILE, balance_cols, transaction_cols)

            # Step 4: Save the data to the newly created tables
            save_data_to_db(db_conn, db_cursor, retrieved_data, balance_cols, transaction_cols)

            print("\nImport process finished successfully.")
        except Exception as e:
            print(f"\n!!! An unexpected error occurred during the database operation: {e} !!!")
        finally:
            if db_conn:
                db_conn.close()
                print("Database connection closed.")
