from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import sqlite3
import os
import json

# --- Setup ---
app = Flask(__name__)
CORS(app)

openai.api_key = "YOUR_API_KEY"
finetuned_code = "YOUR_FINETUNED_MODEL_CODE"
DB_FILE = "merged_data1.db"
MAX_RETRIES = 2


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
        return f"Error reading database schema: {e}"


def initialize_db():
    """Creates the dashboard_items table if it doesn't exist."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_items (
                slot_id INTEGER PRIMARY KEY,
                metric_name TEXT,
                metric_query TEXT
            )
        """)
        for i in range(1, 4):
            cursor.execute(
                "INSERT OR IGNORE INTO dashboard_items (slot_id, metric_name, metric_query) VALUES (?, ?, ?)",
                (i, 'Slot Available', ''))
        conn.commit()


@app.route('/dashboard_items', methods=['GET'])
def get_dashboard_items():
    items = []
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT slot_id, metric_name, metric_query FROM dashboard_items ORDER BY slot_id LIMIT 3")
            rows = cursor.fetchall()
            for row in rows:
                item = dict(row)
                value = 'N/A'
                if row['metric_query']:
                    try:
                        value_cursor = conn.cursor()
                        value_cursor.execute(row['metric_query'])
                        result = value_cursor.fetchone()
                        if result and result[0] is not None:
                            value = f"€{result[0]:,.2f}"
                    except Exception as e:
                        print(f"Error executing dashboard query for slot {row['slot_id']}: {e}")
                        value = "Error"
                item['value'] = value
                items.append(item)
        return jsonify(items)
    except Exception as e:
        print(f"Error fetching dashboard items: {e}")
        return jsonify({"error": "Could not fetch dashboard items"}), 500


# --- Main API Endpoint ---
@app.route('/ask', methods=['POST'])
def ask_agent():
    # REVISION: The backend now receives the entire conversation history from the frontend.
    messages_from_frontend = request.json.get('messages')
    if not messages_from_frontend:
        return jsonify({"answer": "Error: No messages provided."}), 400

    # The user's most recent question is the last message in the list
    user_question = messages_from_frontend[-1]['content']

    db_schema = get_db_schema(DB_FILE)
    if "Error" in db_schema:
        return jsonify({"answer": f"Error: Could not read database schema. {db_schema}"}), 500

    system_prompt = f"""
You are FinWise, a friendly and supportive financial coach. Your goal is to help users understand their finances.
Based on the user's question, decide on the best action. You have four types of responses:

1.  If the user **explicitly asks to 'track', 'show on dashboard', 'add to dashboard', or 'put in slot'** a metric, you must respond with a JSON object to call the `update_dashboard` action. This JSON must contain the `action`, the `slot_id` (1, 2, or 3), a `metric_name` for the label, and the `sql_query` needed to calculate the value. Example: {{"action": "update_dashboard", "slot_id": 1, "metric_name": "Total Balance", "sql_query": "SELECT SUM(t1.amount) FROM ... "}}
2.  If the user asks to **'clear', 'remove', or 'free up'** a slot, change the slot description to Slot Available.
2.  If the user asks for a **chart** (e.g., 'show me a pie chart'), your ONLY output must be a JSON object with a single key "chart_sql". The value should be the SQLite query needed to get the data for that chart.
3.  For **all other data questions** (e.g. "what is...", "how much..."), your default action is to generate a standard SQL query. Respond with a JSON object with the key "sql".
4.  For greetings or general advice, respond with a JSON object with the key "answer".

Here is the database schema:
{db_schema}
"""
    # The full context sent to the AI includes the system prompt and the entire chat history
    messages_for_api = [{"role": "system", "content": system_prompt}] + messages_from_frontend

    try:
        initial_response = openai.chat.completions.create(
            model="ft:gpt-3.5-turbo-0125:personal::BmnMzNSk",
            messages=messages_for_api, # REVISION: Sending the full history
            response_format={"type": "json_object"},
            temperature=0,
        )
        response_content = initial_response.choices[0].message.content
        response_json = json.loads(response_content)

        # --- The rest of your logic remains exactly the same ---
        if response_json.get("action") == "update_dashboard":
            slot_id = response_json['slot_id']
            name = response_json['metric_name']
            query = response_json['sql_query']
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE dashboard_items SET metric_name = ?, metric_query = ? WHERE slot_id = ?",
                               (name, query, slot_id))
                conn.commit()
            return jsonify({"answer": f"Okay, I've updated the dashboard. Slot {slot_id} is now tracking: {name}."})

        elif "chart_sql" in response_json:
            sql_query = response_json["chart_sql"]
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute(sql_query)
                results = cursor.fetchall()
            chart_type_prompt = f"Based on the user's question: '{user_question}', should the chart be a 'pie' chart or a 'bar' chart? Respond with only the word 'pie' or 'bar'."
            chart_type_response = openai.chat.completions.create(model="gpt-3.5-turbo", messages=[
                {"role": "user", "content": chart_type_prompt}])
            chart_type = chart_type_response.choices[0].message.content.strip().lower()
            chart_data = {"labels": [row[0] for row in results], "data": [abs(row[1]) for row in results]}
            return jsonify({"type": "chart", "chart_type": chart_type, "chart_data": chart_data,
                            "answer": "Here is the chart you requested:"})

        elif "sql" in response_json:
            sql_query = response_json["sql"]
            final_answer = "I'm sorry, I was unable to generate a working query for your request after multiple attempts."
            query_succeeded = False
            for attempt in range(MAX_RETRIES):
                if not sql_query or not sql_query.strip().upper().startswith("SELECT"):
                    final_answer = "I'm sorry, I could not generate a valid query for that request."
                    break
                try:
                    with sqlite3.connect(DB_FILE) as conn:
                        cursor = conn.cursor()
                        cursor.execute(sql_query)
                        results = cursor.fetchall()
                        column_names = [description[0] for description in cursor.description]
                    db_results_str = "[]" if not results or (
                                len(results) == 1 and results[0][0] is None) else json.dumps(
                        [dict(zip(column_names, row)) for row in results])
                    query_succeeded = True
                    break
                except sqlite3.Error as e:
                    if attempt < MAX_RETRIES - 1:
                        # For retries, we also send the history so the AI knows what it tried before
                        retry_messages = messages_for_api + [{"role": "assistant", "content": json.dumps({"sql": sql_query})}]
                        correction_prompt = f"The previous SQL query you generated failed. Failed SQL: '{sql_query}'. Error: '{e}'. Please provide a corrected SQLite query in a JSON object with the key 'sql'."
                        retry_messages.append({"role": "user", "content": correction_prompt})
                        correction_response = openai.chat.completions.create(
                            model=finetuned_code, messages=retry_messages,
                            response_format={"type": "json_object"}, temperature=0, )
                        sql_query = json.loads(correction_response.choices[0].message.content).get("sql")

            if query_succeeded:
                summarization_messages = [
                    {"role": "system", "content": "You are FinWise, a helpful financial coach. Formulate a friendly, natural language response based on the provided data. All financial amounts MUST be presented in Euros (€)."},
                    {"role": "user", "content": f"My question was: '{user_question}'. The result from the database is: {db_results_str}"}
                ]
                final_response = openai.chat.completions.create(model="gpt-3.5-turbo", messages=summarization_messages)
                final_answer = final_response.choices[0].message.content
            return jsonify({"answer": final_answer})

        elif "answer" in response_json:
            return jsonify({"answer": response_json['answer']})

    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({"answer": "I'm sorry, an unexpected error occurred."}), 500

if __name__ == '__main__':
    initialize_db()
    if not openai.api_key:
        print("ERROR: Please provide your OpenAI API key in the script.")
    else:
        app.run(debug=True, port=5001)