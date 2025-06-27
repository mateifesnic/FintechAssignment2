import json
import sqlite3
import os
from datetime import datetime, timezone

# --- Configuration ---
JSON_INPUT_FILE = 'abn_amro_data_output.json'
DB_FILE = 'abn_amro_data.db'


def discover_schema(all_data):
    """
    Scans the JSON data to discover all unique keys for a unified accounts table
    (which now excludes balance fields) and a transactions table.
    """
    print("--- Discovering database schema from JSON data ---")
    account_keys = set()
    transaction_keys = set()

    for data in all_data.values():
        # Discover top-level keys for the 'accounts' table (e.g., nextPageKey)
        for key in data.keys():
            if key not in ['account', 'transactions']:
                account_keys.add(key)

        # Also include 'accountNumber' from the nested object if it exists
        if data.get("account", {}).get("accountNumber"):
            account_keys.add("accountNumber")

        # Discover transaction keys
        for tx in data.get("transactions", []):
            for key in tx.keys():
                if key == "descriptionLines":
                    transaction_keys.add("description")
                else:
                    transaction_keys.add(key)

    print(f"    -> Found {len(account_keys)} unique account fields.")
    print(f"    -> Found {len(transaction_keys)} unique transaction fields.")
    return sorted(list(account_keys)), sorted(list(transaction_keys))


def setup_database(db_file, account_columns, transaction_columns):
    """
    Initializes the database and creates tables for accounts and transactions,
    plus a new separate table for balances with a fixed schema.
    """
    print(f"--- Setting up database at '{db_file}' ---")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # --- Dynamically create Accounts table (without balance info) ---
    # The primary key is the 'accountNumber'.
    filtered_account_cols = [col for col in account_columns if col != 'accountNumber']
    create_accounts_sql = "CREATE TABLE IF NOT EXISTS accounts (accountNumber TEXT PRIMARY KEY"
    if filtered_account_cols:
        account_cols_sql = ", ".join([f'"{col}" TEXT' for col in filtered_account_cols])
        create_accounts_sql += f", {account_cols_sql}"
    create_accounts_sql += ")"
    cursor.execute(create_accounts_sql)

    # --- Statically create Balances table ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS balances (
        balance_pk INTEGER PRIMARY KEY AUTOINCREMENT,
        accountNumber TEXT NOT NULL,
        balance REAL,
        sourceTransactionTimestamp TEXT,
        lastUpdatedTimestamp TEXT,
        UNIQUE(accountNumber),
        FOREIGN KEY (accountNumber) REFERENCES accounts (accountNumber)
    )''')

    # --- Dynamically create Transactions table ---
    filtered_transaction_cols = [col for col in transaction_columns if col != 'transactionId']
    create_transactions_sql = "CREATE TABLE IF NOT EXISTS transactions (transactionId TEXT, account_iban TEXT NOT NULL"
    if filtered_transaction_cols:
        transaction_cols_sql = ", ".join([f'"{col}" TEXT' for col in filtered_transaction_cols])
        create_transactions_sql += f", {transaction_cols_sql}"
    create_transactions_sql += ", PRIMARY KEY (transactionId, account_iban), FOREIGN KEY (account_iban) REFERENCES accounts (accountNumber))"
    cursor.execute(create_transactions_sql)

    conn.commit()
    print("    -> Dynamic database schema created successfully.")
    return conn, cursor


def load_json_data(json_file):
    """Loads and parses the data from the specified JSON file."""
    print(f"--- Reading data from '{json_file}' ---")
    if not os.path.exists(json_file):
        print(f"!!! ERROR: JSON file not found at '{json_file}'. Please run the main script first. !!!")
        return None
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print("    -> JSON file loaded successfully.")
    return data


def save_data_to_db(conn, cursor, all_data, account_columns, transaction_columns):
    """
    Iterates through the data, saves account info and transactions,
    and derives the latest balance to save into the new separate balances table.
    """
    print(f"--- Saving all collected data to the database ---")
    script_timestamp = datetime.now(timezone.utc).isoformat()

    for iban, data in all_data.items():
        # --- 1. Insert into Accounts table ---
        if account_columns:
            # Prepare data only from top-level and ensure 'accountNumber' is present
            flat_account_data = {k: v for k, v in data.items() if k not in ['account', 'transactions']}
            if 'accountNumber' not in flat_account_data:
                # Use the nested 'accountNumber' or fall back to the top-level IBAN
                flat_account_data['accountNumber'] = data.get('account', {}).get('accountNumber', iban)

            acc_values = [flat_account_data.get(col) for col in account_columns]
            acc_placeholders = ', '.join(['?'] * len(account_columns))
            acc_insert_sql = f"INSERT OR IGNORE INTO accounts ({', '.join(f'\"{c}\"' for c in account_columns)}) VALUES ({acc_placeholders})"
            cursor.execute(acc_insert_sql, acc_values)

        # --- 2. Insert into Transactions table ---
        transactions = data.get("transactions", [])
        if transaction_columns and transactions:
            tx_cols_for_sql = ['account_iban'] + transaction_columns
            tx_placeholders = ', '.join(['?'] * len(tx_cols_for_sql))
            tx_insert_sql = f"INSERT OR IGNORE INTO transactions ({', '.join(f'\"{c}\"' for c in tx_cols_for_sql)}) VALUES ({tx_placeholders})"

            for tx in transactions:
                flat_tx = tx.copy()
                if "descriptionLines" in flat_tx:
                    flat_tx["description"] = "\n".join(flat_tx.pop("descriptionLines"))

                tx_values = [iban] + [flat_tx.get(col) for col in transaction_columns]
                cursor.execute(tx_insert_sql, tx_values)

        # --- 3. Derive latest balance and insert into Balances table ---
        if transactions:
            # Find the transaction with the maximum (latest) timestamp
            latest_tx = max(transactions, key=lambda x: x.get('transactionTimestamp', ''))

            balance_amount = latest_tx.get('balanceAfterMutation')
            source_timestamp = latest_tx.get('transactionTimestamp')

            if balance_amount is not None:
                # Use INSERT OR REPLACE to ensure the balance is always up-to-date for that account
                cursor.execute('''
                INSERT OR REPLACE INTO balances (accountNumber, balance, sourceTransactionTimestamp, lastUpdatedTimestamp)
                VALUES (?, ?, ?, ?)
                ''', (iban, balance_amount, source_timestamp, script_timestamp))

    conn.commit()
    print("    -> All data saved to database successfully.")


if __name__ == "__main__":
    retrieved_data = load_json_data(JSON_INPUT_FILE)

    if retrieved_data:
        db_conn = None
        try:
            account_cols, transaction_cols = discover_schema(retrieved_data)
            # We don't need balance_cols from discover_schema anymore
            db_conn, db_cursor = setup_database(DB_FILE, account_cols, transaction_cols)
            save_data_to_db(db_conn, db_cursor, retrieved_data, account_cols, transaction_cols)
            print("\nImport process finished successfully.")
        except Exception as e:
            print(f"\n!!! An unexpected error occurred during the database operation: {e} !!!")
        finally:
            if db_conn:
                db_conn.close()
                print("Database connection closed.")
