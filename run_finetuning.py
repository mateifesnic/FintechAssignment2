import openai
import os

# --- Setup ---
# Your API Key should be set as an environment variable for security
# The new syntax recommends initializing the client with the key
try:
    client = openai.OpenAI(
        api_key = "YOUR_API_KEY"
    )
except TypeError:
    print("ERROR: Your OpenAI API key is not set.")
    print("Please set your OPENAI_API_KEY environment variable.")
    client = None

TRAINING_FILE = "finetuning_data.jsonl"
MODEL_TO_TUNE = "gpt-3.5-turbo"

def start_finetuning_job():
    if not client:
        return

    try:
        # 1. Upload your training file using the new client syntax
        print(f"Uploading training file: '{TRAINING_FILE}'...")
        with open(TRAINING_FILE, "rb") as f:
            # REVISION: Using client.files.create instead of openai.File.create
            training_file_obj = client.files.create(
              file=f,
              purpose='fine-tune'
            )
        print(f"   -> File uploaded successfully with ID: {training_file_obj.id}")

        # 2. Start the fine-tuning job using the new client syntax
        print(f"\nStarting fine-tuning job with model '{MODEL_TO_TUNE}'...")
        # REVISION: Using client.fine_tuning.jobs.create instead of openai.FineTuningJob.create
        job = client.fine_tuning.jobs.create(
          training_file=training_file_obj.id,
          model=MODEL_TO_TUNE
        )
        print(f"   -> Fine-tuning job started successfully with ID: {job.id}")
        print("\n--- PROCESS STARTED ---")
        print("You can monitor the job's progress on the OpenAI website under the 'Fine-tuning' section.")
        print("Once the job is complete, you will receive an email and your custom model ID will be available.")

    except FileNotFoundError:
        print(f"\n--- ERROR: FILE NOT FOUND ---")
        print(f"Make sure your training data file '{TRAINING_FILE}' exists in the same directory.")
        print("You may need to run the 'create_finetuning_file.py' script first.")
    except Exception as e:
        print(f"\n--- An Error Occurred ---")
        print(f"An error occurred while communicating with the OpenAI API: {e}")


if __name__ == "__main__":
    start_finetuning_job()
