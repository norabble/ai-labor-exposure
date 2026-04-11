import os
import json
import pandas as pd
from typing import Literal
from pydantic import BaseModel
from google import genai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load environment variables for GCP
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")

if not GCP_PROJECT_ID:
    raise ValueError("GCP_PROJECT_ID environment variable is not set. Please set it in .env before running this script.")

# Initialize the Gemini GenAI client with Vertex AI backend
client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)

# Define the expected structured output format
class ClassificationOutput(BaseModel):
    label: Literal["Bounded", "Unbounded", "Adversarial"]
    justification: str

SYSTEM_INSTRUCTION = """
You are an expert labor economist classifying occupational tasks based on their dynamic economic demand.
Read the Job Title and the specific Task Statement, and map the task into one of the following three categories:

1. Bounded (Satiated) Demand: 
   - Finishing this task faster DOES NOT create new demand for it. 
   - Time saved leads to fewer workers needed to accomplish the known workload.
   - Example roles: Payroll, Routine Data Entry. 

2. Unbounded Utility (Infinite Backlog): 
   - Efficiency lowers cost and satisfies an enormous backlog of demand.
   - Time saved is used to produce more outputs or higher-quality outputs. 
   - The outcome has positive societal value that feels nearly infinite.
   - Example roles: Programming, Science, Healthcare.

3. Adversarial Demand (Arms Race):
   - The task exists in a zero-sum competition. 
   - Efficiency leads to task inflation—time saved is reinvested into performing the task at a higher volume or complexity just to maintain an edge over an opponent.
   - Example roles: Law, Sales, Marketing, Cybersecurity.

Return ONLY a JSON object containing the `label` (strictly "Bounded", "Unbounded", or "Adversarial") and a one-sentence `justification`.
"""

def classify_task(job_title: str, task_statement: str) -> dict:
    prompt = f"Job Title: {job_title}\nTask Statement: {task_statement}"
    
    response = client.models.generate_content(
        model='gemini-3-flash-preview',
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=ClassificationOutput,
            temperature=0.1
        ),
    )
    return json.loads(response.text)

def classify_random_sample(sample_size=100):
    print("Loading O*NET tasks...")
    if not os.path.exists("data/raw/onet_tasks.csv"):
        print("data/raw/onet_tasks.csv not found. Please run download_data.py first.")
        return
        
    df_tasks = pd.read_csv("data/raw/onet_tasks.csv")
    
    # Take a random sample for the first validation batch
    df_sample = df_tasks.sample(n=sample_size, random_state=42).copy()
    
    results = []
    print(f"Classifying {sample_size} tasks...")
    
    for idx, row in df_sample.iterrows():
        title = row.get("Title", "")
        task_statement = row.get("Task", "")
        print(f"[{len(results)+1}/{sample_size}] Processing Task for '{title}'...")
        
        try:
            res_dict = classify_task(title, task_statement)
            results.append({
                "O*NET-SOC Code": row.get("O*NET-SOC Code", ""),
                "Title": title,
                "Task ID": row.get("Task ID", ""),
                "Task": task_statement,
                "Demand Type": res_dict.get("label"),
                "Justification": res_dict.get("justification")
            })
        except Exception as e:
            print(f"Error classifying task: {e}")
            results.append({
                "O*NET-SOC Code": row.get("O*NET-SOC Code", ""),
                "Title": title,
                "Task ID": row.get("Task ID", ""),
                "Task": task_statement,
                "Demand Type": "ERROR",
                "Justification": str(e)
            })

    df_results = pd.DataFrame(results)
    os.makedirs("data/output", exist_ok=True)
    df_results.to_csv("data/output/classified_tasks_batch1.csv", index=False)
    print("Saved classification results to data/output/classified_tasks_batch1.csv")

if __name__ == "__main__":
    classify_random_sample(100)
