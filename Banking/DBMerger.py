import sqlite3
import os
from datetime import datetime

# --- Configuration ---
# Source database files
ING_DB = 'ing_data.db'
ABN_DB = 'abn_amro_data.db'

# The new, merged database file that will be created
MERGED_DB = 'merged_data1.db'


def to_float(value):
    """
    Helper function to safely convert a value to a float.
    Returns None if the value is None or cannot be converted.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def to_datetime_iso(date_string):
    """
    Helper function to safely convert a date string from various formats
    to a standardized ISO 8601 format (YYYY-MM-DD HH:MM:SS).
    Returns None if the string is empty or cannot be parsed.
    """
    if not date_string:
        return None

    parsable_string = str(date_string)

    # Pre-process for the specific 'YYYY-MM-DD-HH:MM:SS:ms' format.
    if parsable_string.count(':') == 3 and parsable_string.count('-') == 3:
        try:
            # This is a more robust way to handle 'YYYY-MM-DD-HH:MM:SS:ms'
            parts = parsable_string.split('-')
            if len(parts) == 4:
                date_part = '-'.join(parts[:3])
                time_part = parts[3]

                # Replace the last colon in the time part with a period
                time_part_fixed = '.'.join(time_part.rsplit(':', 1))

                # Reassemble the string in a standard format
                parsable_string = f"{date_part} {time_part_fixed}"
        except Exception:
            # If transformation fails, proceed with the original string and let it be handled below
            pass

    # List of common date/time formats to try parsing
    formats_to_try = [
        '%Y-%m-%dT%H:%M:%S.%f%z',  # ISO 8601 with microseconds and timezone
        '%Y-%m-%dT%H:%M:%S%z',  # ISO 8601 with timezone
        '%Y-%m-%dT%H:%M:%S.%f',  # ISO 8601 with microseconds, no timezone
        '%Y-%m-%dT%H:%M:%S',  # ISO 8601, no microseconds or timezone
        '%Y-%m-%d %H:%M:%S.%f',  # Space separator with microseconds
        '%Y-%m-%d %H:%M:%S',  # Space separator
        '%Y-%m-%d',  # Date only
    ]

    # Clean the string for parsing: handle 'Z' for UTC
    if isinstance(parsable_string, str) and parsable_string.endswith('Z'):
        parsable_string = parsable_string[:-1] + '+0000'

    for fmt in formats_to_try:
        try:
            # Parse the string into a datetime object
            dt_obj = datetime.strptime(parsable_string, fmt)
            # Return it in a standard format recognized by SQLite's DATETIME type
            return dt_obj.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            continue

    # If no format matched after trying all of them
    print(f"Warning: Could not parse the date '{date_string}'. It will be stored as NULL.")
    return None


def create_unified_database(db_file):
    """
    Creates the new merged database with a unified schema designed
    to hold data from both the current ING and ABN AMRO databases.
    """
    if os.path.exists(db_file):
        os.remove(db_file)
        print(f"--- Removed existing merged database: '{db_file}' ---")

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    print(f"--- Creating new unified database: '{db_file}' ---")

    # 1. Create unified_accounts table with updated schema
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS unified_accounts (
        account_id TEXT PRIMARY KEY,
        source_bank TEXT NOT NULL,
        iban TEXT,
        account_holder_name TEXT DEFAULT 'john doe',
        currency TEXT DEFAULT 'EUR',
        product_name TEXT DEFAULT 'debit account'
    )''')

    # 2. Create unified_balances table with DATETIME type for timestamp
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS unified_balances (
        balance_pk INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id_fk TEXT NOT NULL,
        source_bank TEXT NOT NULL,
        amount REAL,
        currency TEXT NOT NULL DEFAULT 'EUR',
        timestamp DATETIME,
        FOREIGN KEY (account_id_fk) REFERENCES unified_accounts (account_id)
    )''')

    # 3. Create unified_transactions table with DATETIME types
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS unified_transactions (
        transaction_pk INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT,
        account_id_fk TEXT NOT NULL,
        source_bank TEXT NOT NULL,
        amount REAL,
        currency TEXT,
        booking_date DATETIME,
        execution_timestamp DATETIME,
        description TEXT,
        counterparty_name TEXT,
        counterparty_iban TEXT,
        type_code TEXT,
        UNIQUE (transaction_id, account_id_fk)
    )''')

    conn.commit()
    print("    -> Unified schema created successfully.")
    return conn, cursor


def merge_ing_data(ing_conn, merged_cursor):
    """Reads data from the ING database, maps it, and inserts it into the merged database."""
    print("\n--- Merging data from ING ---")
    ing_conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    ing_cursor = ing_conn.cursor()

    # 1. Merge accounts with new logic
    ing_cursor.execute("SELECT * FROM accounts")
    for row in ing_cursor.fetchall():
        data = dict(row)
        # If iban is missing, use the maskedPan value instead.
        iban_value = data.get('iban') or data.get('maskedPan')

        merged_cursor.execute('''
        INSERT INTO unified_accounts 
        (account_id, source_bank, iban, account_holder_name, currency, product_name) 
        VALUES (:resourceId, 'ING', :iban, :name, :currency, :product)
        ''', {**data, 'iban': iban_value})

    # 2. Merge balances
    ing_cursor.execute("SELECT * FROM balances")
    for row in ing_cursor.fetchall():
        data = dict(row)
        data['amount'] = to_float(data.get('amount'))
        data['currency'] = data.get('currency') or 'EUR'
        # Parse and standardize the timestamp
        data['timestamp'] = to_datetime_iso(data.get('lastChangeDateTime'))

        merged_cursor.execute('''
        INSERT INTO unified_balances 
        (account_id_fk, source_bank, amount, currency, timestamp) 
        VALUES (:account_resourceId, 'ING', :amount, :currency, :timestamp)
        ''', data)

    # 3. Merge transactions with updated fields
    ing_cursor.execute("SELECT * FROM transactions")
    for row in ing_cursor.fetchall():
        data = dict(row)
        data['amount'] = to_float(data.get('amount'))
        data['description'] = data.get('remittanceInformationUnstructured') or data.get('transactionDetails')
        data['currency'] = data.get('currency') or 'EUR'
        # Parse and standardize date fields
        data['booking_date'] = to_datetime_iso(data.get('bookingDate') or data.get('transactionDate'))
        data['execution_timestamp'] = to_datetime_iso(data.get('executionDateTime'))

        merged_cursor.execute('''
        INSERT OR IGNORE INTO unified_transactions 
        (account_id_fk, transaction_id, source_bank, amount, currency, booking_date, execution_timestamp, 
         description, type_code) 
        VALUES (:account_resourceId, :transactionId, 'ING', :amount, :currency, :booking_date, :execution_timestamp, 
         :description, :transactionType)
        ''', data)

    print("    -> ING data merged successfully.")


def merge_abn_data(abn_conn, merged_cursor):
    """Reads data from the new ABN AMRO database schema, maps it, and inserts it."""
    print("\n--- Merging data from ABN AMRO ---")
    abn_conn.row_factory = sqlite3.Row
    abn_cursor = abn_conn.cursor()

    # 1. Merge accounts into the new simplified table
    abn_cursor.execute("SELECT * FROM accounts")
    for row in abn_cursor.fetchall():
        merged_cursor.execute('''
        INSERT OR IGNORE INTO unified_accounts (account_id, source_bank, iban) 
        VALUES (:accountNumber, 'ABN_AMRO', :accountNumber)
        ''', dict(row))

    # 2. Merge balances
    abn_cursor.execute("SELECT * FROM balances")
    for row in abn_cursor.fetchall():
        data = dict(row)
        data['balance'] = to_float(data.get('balance'))
        # Parse and standardize the timestamp
        data['timestamp'] = to_datetime_iso(data.get('sourceTransactionTimestamp'))

        merged_cursor.execute('''
        INSERT INTO unified_balances 
        (account_id_fk, source_bank, amount, timestamp) 
        VALUES (:accountNumber, 'ABN_AMRO', :balance, :timestamp)
        ''', data)

    # 3. Merge transactions with updated fields
    abn_cursor.execute("SELECT * FROM transactions")
    for row in abn_cursor.fetchall():
        data = dict(row)
        data['amount'] = to_float(data.get('amount'))
        data['currency'] = data.get('currency') or 'EUR'
        # Parse and standardize date fields
        data['booking_date'] = to_datetime_iso(data.get('bookDate'))
        data['execution_timestamp'] = to_datetime_iso(data.get('transactionTimestamp'))

        merged_cursor.execute('''
        INSERT OR IGNORE INTO unified_transactions 
        (account_id_fk, transaction_id, source_bank, amount, currency, booking_date, execution_timestamp, 
         description, counterparty_name, counterparty_iban, type_code) 
        VALUES (:account_iban, :transactionId, 'ABN_AMRO', :amount, :currency, :booking_date, :execution_timestamp, 
         :description, :counterPartyName, :counterPartyAccountNumber, :mutationCode)
        ''', data)

    print("    -> ABN AMRO data merged successfully.")


if __name__ == "__main__":
    if not os.path.exists(ING_DB) or not os.path.exists(ABN_DB):
        # Create dummy files for testing if they don't exist
        print(f"--- NOTE: Creating dummy source databases for demonstration. ---")
        sqlite3.connect(ING_DB).close()
        sqlite3.connect(ABN_DB).close()

    merged_conn, ing_connection, abn_connection = None, None, None
    try:
        merged_conn, merged_curs = create_unified_database(MERGED_DB)
        ing_connection = sqlite3.connect(ING_DB)
        abn_connection = sqlite3.connect(ABN_DB)

        merge_ing_data(ing_connection, merged_curs)
        merge_abn_data(abn_connection, merged_curs)

        merged_conn.commit()

        print("\n--- Database merge complete! ---")
        print(f"All data has been merged into '{MERGED_DB}'")

    except sqlite3.Error as e:
        print(f"\n!!! A database error occurred: {e} !!!")
    finally:
        if ing_connection: ing_connection.close()
        if abn_connection: abn_connection.close()
        if merged_conn: merged_conn.close()
