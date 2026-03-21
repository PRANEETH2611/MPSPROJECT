import google.generativeai as genai
import sys
import os

# SECURITY: Never hardcode API keys in source code!
# Set the API key as an environment variable: GOOGLE_API_KEY
# Example: set GOOGLE_API_KEY=your_api_key_here (Windows)
# Example: export GOOGLE_API_KEY=your_api_key_here (Linux/Mac)

API_KEY = os.environ.get("GOOGLE_API_KEY", "")

if not API_KEY:
    with open("models_list.txt", "w") as f:
        f.write("Error: GOOGLE_API_KEY environment variable not set.\n")
        f.write("Please set the environment variable before running this script.\n")
    sys.exit(1)

try:
    with open("models_list.txt", "w") as f:
        genai.configure(api_key=API_KEY)
        f.write("--- START MODEL LIST ---\n")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                f.write(f"{m.name}\n")
        f.write("--- END MODEL LIST ---\n")
except Exception as e:
    with open("models_list.txt", "w") as f:
        f.write(f"Error: {e}")
