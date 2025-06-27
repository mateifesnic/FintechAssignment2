import csv
import json
import sqlite3
import os

# --- Configuration ---
DB_FILE = "merged_data1.db"
INPUT_CSV_FILE = "questions_sql.csv"
OUTPUT_JSONL_FILE = "finetuning_data.jsonl"


def get_db_schema(db_path: str) -> str:
    """Inspects the SQLite database and returns its schema as a string."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            schema_str = ""
            for table_name in tables:
                table_name = table_name[0]
                schema_str += f"Table '{table_name}':\n"
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()
                for column in columns:
                    schema_str += f"  - {column[1]} ({column[2]})\n"
                schema_str += "\n"
            return schema_str
    except Exception as e:
        print(f"Error reading database schema: {e}")
        return None


def create_finetuning_file():
    """
    Reads the curated CSV and formats it into a JSONL file for OpenAI fine-tuning.
    """
    db_schema = get_db_schema(DB_FILE)
    if not db_schema:
        print("Could not get DB schema. Aborting.")
        return

    # This is the exact system prompt your agent uses.
    # The fine-tuned model will learn to respond based on these instructions.
    system_prompt = f"""
You are FinWise, an expert SQL data analyst for a personal finance app.
Your task is to convert a user's question into a single, valid SQLite query based on the database schema provided below.
Your ONLY output must be a JSON object with a single key "sql", containing the query.

Database Schema:
{db_schema}
"""

    try:
        with open(INPUT_CSV_FILE, 'r', encoding='utf-8') as infile, \
                open(OUTPUT_JSONL_FILE, 'w', encoding='utf-8') as outfile:

            reader = csv.DictReader(infile)
            count = 0
            for row in reader:
                question = row['question']
                perfect_sql = row['perfect_sql']

                # We need to format the assistant's response exactly as our main script expects it.
                assistant_response = json.dumps({"sql": perfect_sql})

                # Create the final JSON structure for each line in the training file
                json_line = {
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": assistant_response}
                    ]
                }

                outfile.write(json.dumps(json_line) + '\n')
                count += 1

        print(f"Successfully created '{OUTPUT_JSONL_FILE}' with {count} examples.")
        print("\nYou are now ready for the final step: running the fine-tuning job.")

    except FileNotFoundError:
        print(f"ERROR: Make sure '{INPUT_CSV_FILE}' exists in the same directory as this script.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    if not os.path.exists(DB_FILE):
        print(f"ERROR: Database file '{DB_FILE}' not found.")
    else:
        create_finetuning_file()