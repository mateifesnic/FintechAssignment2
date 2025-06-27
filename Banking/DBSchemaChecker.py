import sqlite3
import os

# --- Configuration ---
# Point the inspector to our final merged database file.
DATABASE_FILE = '../merged_data1.db'


def print_db_schema(db_file):
    """
    Connects to the specified SQLite database file and prints its full schema.
    """
    if not os.path.exists(db_file):
        print(f"!!! ERROR: Database file not found at '{db_file}'. Please run the merger script first. !!!\n")
        return

    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        print("\n" + "=" * 50)
        print(f"Schema for: {db_file}")
        print("=" * 50)

        # Get a list of all tables in the database
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print(" -> No tables found in this database.")
            return

        # For each table, get and print its column information
        for table_name_tuple in tables:
            table_name = table_name_tuple[0]
            # Skip the internal sqlite_sequence table for a cleaner output
            if table_name == 'sqlite_sequence':
                continue

            print(f"\n--- Table: {table_name} ---")

            # Use PRAGMA to get table info (column details)
            cursor.execute(f"PRAGMA table_info('{table_name}');")
            columns = cursor.fetchall()

            # Print each column's name and data type
            for column in columns:
                # Column details are in a tuple: (id, name, type, notnull, default_value, pk)
                col_name = column[1]
                col_type = column[2]
                print(f"    - {col_name} ({col_type})")

    except sqlite3.Error as e:
        print(f"!!! A database error occurred for '{db_file}': {e} !!!")
    finally:
        # Make sure the connection is closed
        if conn:
            conn.close()


if __name__ == "__main__":
    print("--- Inspecting the Final Merged Database Schema ---")
    print_db_schema(DATABASE_FILE)
    print("\n--- Inspection complete. ---")

