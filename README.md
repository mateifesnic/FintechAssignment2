# FinWise MVP - Technical Documentation

FinWise is a proof-of-concept for an AI-driven, conversational personal finance management application specifically designed for the Dutch market. It addresses the common pain points of fragmented banking and generic financial advice by leveraging a fine-tuned Large Language Model (LLM) to provide a natural language interface for users to interact with their unified financial data.

This repository contains the complete Minimum Viable Product (MVP), including data connectors for Open Banking APIs, a unified database structure, a fine-tuned AI agent for generating SQL queries, and a web-based user interface for interaction.

## Table of Contents
- [Core Features](#1-core-features)
- [System Architecture](#2-system-architecture)
- [Technology Stack](#3-technology-stack)
- [Setup and Installation](#4-setup-and-installation)
- [Fine-Tuning Your Custom AI Model](#5-fine-tuning-your-custom-ai-model)
- [Usage Workflow](#6-usage-workflow)
- [Project Components](#7-project-components)
- [API Endpoints](#8-api-endpoints)
- [Future Development](#9-future-development)

---

## 1. Core Features

* **Conversational AI Advisor**: Users can ask complex questions about their finances in plain English. The AI agent understands the user's intent and generates the appropriate database query to find the answer.
* **Safe Text-to-SQL Architecture**: To ensure security and reliability, the AI's primary role is to generate read-only `SELECT` queries. A validation layer in the backend ensures no destructive commands (`DROP`, `DELETE`, etc.) can be executed.
* **Fine-Tuned Intelligence**: The system is designed to use a custom fine-tuned `gpt-3.5-turbo` model. This transforms a generalist AI into a specialized expert on our specific database schema for higher accuracy.
* **Dynamic & Interactive Dashboard**: A "Financial Information" panel allows users to command the AI to track specific, custom financial metrics (e.g., "track my total balance in slot 1"), which are saved persistently in the database.
* **In-Chat Visualizations**: The AI can generate dynamic charts (pie or bar) directly in the chat window in response to user requests (e.g., "show me a pie chart of my spending this month").
* **Multi-Bank Data Aggregation**: Includes scripts and logic to fetch and unify data from different banking institutions (ABN AMRO and ING).

---

## 2. System Architecture

The FinWise MVP is built on a modern, decoupled architecture designed for security, reliability, and scalability.

* **Frontend (Web UI)**: A single-page application that serves as the user interface. It handles user input and renders the conversation and charts.
* **Backend (Flask API Server)**: The central application server that receives user requests, orchestrates AI and database interactions, and enforces business logic.
* **AI Engine (The "Brain")**: Our fine-tuned OpenAI model. Its sole responsibility is to act as a "translator," converting natural language questions into structured JSON commands. It has no direct access to the database.
* **Data Layer**: Includes the scripts for connecting to bank APIs and the local SQLite database (`merged_data1.db`) that stores all unified financial data.

---

## 3. Technology Stack

| Layer                | Technology                                    |
| :------------------- | :-------------------------------------------- |
| **Backend** | Python 3, Flask                               |
| **AI Engine** | OpenAI (`gpt-3.5-turbo`, Fine-Tuning)         |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript               |
| **Data Visualization** | Chart.js                                      |
| **Database** | SQLite                                        |

---

## 4. Setup and Installation

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
    This project requires an OpenAI API key to function. You must edit the Python files directly to include your key.
    * Open the `app.py` file.
    * Find the line `openai.api_key = "sk-..."` and replace the placeholder with your actual OpenAI secret key.
    * Open the `run_finetuning.py` file (used in the next section).
    * Find the line `openai.api_key = "sk-..."` and replace it with your key as well.

4.  **Prepare the Database:**
    * Ensure you have a database file named `merged_data1.db` in the root of the project directory.
    * If you do not have one, you can run `app.py` once to create an empty database with the correct tables.

---

## 5. Fine-Tuning Your Custom AI Model

For the best performance, the agent relies on a custom model that has been fine-tuned to understand our specific database schema. Follow these steps to train your own model.

### Step 1: Curate the Training Data
The quality of your training data is the most important factor for the AI's performance.
* Open the `curated_examples.csv` file.
* This file requires two columns: `question` and `perfect_sql`.
* Add at least 50-100 examples of realistic user questions and the corresponding, perfectly written SQL query that answers that question based on your database schema.

### Step 2: Generate the Training File
Once your CSV is complete, run the `create_finetuning_file.py` script from your terminal:
```bash
python create_finetuning_file.py
```
This will read your CSV and create a new file named `finetuning_data.jsonl`, which is correctly formatted for the OpenAI API.

### Step 3: Run the Fine-Tuning Job
* Open the `run_finetuning.py` script and ensure your OpenAI API key is correctly set inside it.
* Run the script from your terminal:
    ```bash
    python run_finetuning.py
    ```
* This will upload your dataset and start the fine-tuning job. Note the **Job ID** that is printed to the console.
* Go to the [OpenAI platform website](https://platform.openai.com/), navigate to the "Fine-tuning" section, and monitor the status of your job. This can take several minutes to over an hour.

### Step 4: Update the Main Application
* Once your fine-tuning job has succeeded, OpenAI will provide you with a new **custom model ID** (it will start with `ft:gpt-3.5-turbo:...`).
* Open the `app.py` file.
* Find the line that specifies the model:
    ```python
    model="ft:gpt-3.5-turbo-0125:personal::BmnMzNSk",
    ```
* Replace the placeholder ID with your new custom model ID.

Your FinWise agent is now running on your specialized, expert model.

---

## 6. Usage Workflow

**Start the Backend Server:**
* Open your terminal, navigate to the project directory, and run the Flask application:
    ```bash
    python app.py
    ```
* The server will start on `http://127.0.0.1:5001`.

**Launch the Frontend:**
* Navigate to the project directory in your file explorer.
* Open the `login.html` file in your web browser.
* Enter a username, click "Login," and you will be redirected to the main `index.html` application.

**Interact with FinWise:**
* You can now ask questions ("what was my total spend last month?"), request charts ("show me a pie chart of my spending"), and command the AI to track metrics ("track my total balance in slot 1").

---

## 7. Project Components

* `app.py`: The main Flask server and API logic.
* `index.html`: The single-page application user interface.
* `login.html`: The simulated user login page.
* `merged_data1.db`: The SQLite database.
* **Fine-Tuning Pipeline**:
    * `curated_examples.csv`
    * `create_finetuning_file.py`
    * `run_finetuning.py`

---

## 8. API Endpoints

* `GET /dashboard_items`: Fetches and calculates the current values for the three dynamic dashboard slots.
* `POST /ask`: The main endpoint for all conversational interactions. Receives the user's chat history and orchestrates the AI and database response.

---
