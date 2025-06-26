# FinWise MVP

**FinWise** is a proof-of-concept for an AI-driven, conversational personal finance management application specifically designed for the Dutch market. It addresses the common pain points of fragmented banking and generic financial advice by leveraging a fine-tuned Large Language Model (LLM) to provide a natural language interface for users to interact with their unified financial data.

This repository contains the complete Minimum Viable Product (MVP), including data connectors for Open Banking APIs, a unified database structure, a fine-tuned AI agent for generating SQL queries, and a web-based user interface for interaction.

---

## Core Features

* **Conversational AI Advisor:** Users can ask complex questions about their finances in plain English, and the AI agent will generate the appropriate database query to find the answer.
* **Safe Text-to-SQL Architecture:** The AI's primary role is to generate read-only `SELECT` queries, which are validated before execution. This prevents destructive actions and ensures data integrity.
* **Fine-Tuned Intelligence:** The system uses a custom fine-tuned `gpt-3.5-turbo` model, trained on over 100 curated examples, making it an expert at querying our specific database schema for higher accuracy.
* **Dynamic Dashboard:** A "Financial Information" panel allows users to command the AI to track specific, custom financial metrics (e.g., "track my total balance in slot 1"), which are saved and displayed persistently.
* **In-Chat Visualizations:** The AI can generate dynamic charts (pie or bar) directly in the chat window in response to user requests (e.g., "show me a pie chart of my spending this month").
* **Multi-Bank Data Aggregation:** Includes scripts and logic to fetch and unify data from different banking institutions (ABN AMRO and ING).

---

## Technology Stack

* **Backend:** Python 3, Flask
* **AI Engine:** OpenAI (Fine-Tuned `gpt-3.5-turbo`)
* **Frontend:** HTML5, CSS3, Vanilla JavaScript
* **Data Visualization:** Chart.js
* **Database:** SQLite

---

## Project Structure

This project is organized into several key files, each with a specific purpose:

* **`app.py`**: The main backend Flask server. It exposes the `/ask` and `/dashboard_items` API endpoints and orchestrates the interaction between the UI, the AI, and the database.
* **`index.html`**: The main single-page application UI. It contains the chat interface and the dynamic dashboard.
* **`login.html`**: A simulated login screen that captures a username and redirects to the main application.
* **`merged_data1.db`**: The SQLite database file containing all unified user data.
* **Data Fetching & Fine-Tuning Scripts:**
    * `ing_full_flow.py` / `abn_amro_fetcher.py`: Scripts to connect to banks and get data.
    * `curated_examples.csv`: The source file containing question/SQL pairs for training.
    * `create_finetuning_file.py`: A utility to convert the CSV into the `JSONL` format required by OpenAI.
    * `run_finetuning.py`: The script that uploads the dataset and starts the fine-tuning job.

---

## Setup & Installation

To run this project, you will need Python 3 and the required libraries.

1.  **Clone the Repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-directory>
    ```

2.  **Install Python Dependencies:**
    ```bash
    pip install Flask Flask-Cors openai
    ```

3.  **Set Up OpenAI API Key:**
    You must set your OpenAI API key as an environment variable.
    * On macOS/Linux:
        ```bash
        export OPENAI_API_KEY='your-secret-key-here'
        ```
    * On Windows:
        ```bash
        set OPENAI_API_KEY='your-secret-key-here'
        ```

4.  **Prepare the Database:**
    * Ensure your `merged_data1.db` file is present in the root of the project directory. If it does not exist, running `app.py` for the first time will create the necessary tables.

---

## Usage

The application consists of a backend server and a frontend UI. You must run the backend first.

1.  **Start the Backend Server:**
    Open your terminal, navigate to the project directory, and run the Flask application:
    ```bash
    python app.py
    ```
    The server will start and be available at `http://127.0.0.1:5001`.

2.  **Launch the Frontend:**
    * Navigate to the project directory in your file explorer.
    * Open the **`login.html`** file in your web browser (e.g., Chrome, Firefox, Safari).
    * Enter a username and click "Login". You will be redirected to the main `index.html` application.

3.  **Interact with FinWise:**
    You can now ask questions, request charts, and command the AI to track metrics on your dashboard.
