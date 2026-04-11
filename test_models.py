from google import genai
import os

project = "gen-ai-exposure"
location = "us-central1"
client = genai.Client(vertexai=True, project=project, location=location)

models_to_test = [
    "gemini-1.5-flash-001",
    "gemini-1.5-flash-002",
    "gemini-1.5-flash",
    "gemini-3.0-flash",
    "gemini-3-flash-001",
    "gemini-pro"
]

for m in models_to_test:
    try:
        response = client.models.generate_content(model=m, contents="x")
        print(f"SUCCESS: {m}")
    except Exception as e:
        err = str(e)
        if "404" in err:
            print(f"NOT FOUND: {m}")
        elif "API not enabled" in err:
            print(f"API DISABLED: {m}")
        elif "403" in err:
            print(f"FORBIDDEN: {m}")
        else:
            print(f"ERROR on {m}: {err[:100]}...")
