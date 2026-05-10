import json
import os
import time
from typing import Literal

import pandas as pd
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()

# Load environment variables for GCP
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "global")

if not GCP_PROJECT_ID:
    raise ValueError("GCP_PROJECT_ID environment variable is not set. Please set it in .env before running this script.")

# Initialize the Gemini GenAI client with Vertex AI backend
client = genai.Client(vertexai=True, project=GCP_PROJECT_ID, location=GCP_LOCATION)

MODEL = "gemini-3-flash-preview"

# ── Structured output schema ──────────────────────────────────────────────────


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
   - Efficiency leads to task inflation—time saved is reinvested into performing the task at a higher volume
     or complexity just to maintain an edge over an opponent.
   - Example roles: Law, Sales, Marketing, Cybersecurity.

Return ONLY a JSON object containing the `label` (strictly "Bounded", "Unbounded", or "Adversarial") and a one-sentence `justification`.
"""

# ── Core classification call ──────────────────────────────────────────────────


def classify_task(job_title: str, task_statement: str, retries: int = 3) -> dict:
    prompt = f"Job Title: {job_title}\nTask Statement: {task_statement}"
    delay = 2
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=ClassificationOutput,
                    temperature=0.1,
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait = delay * (2**attempt)
                print(f"  Rate limited — waiting {wait}s before retry {attempt + 1}/{retries}...")
                time.sleep(wait)
            else:
                raise  # Non-retriable errors bubble up immediately
    raise RuntimeError(f"Failed after {retries} retries for: {job_title} | {task_statement[:60]}")


# ── Validation batch (first 100 random tasks) ─────────────────────────────────


def classify_random_sample(sample_size: int = 100):
    """Classify a random sample of tasks for quick validation."""
    print("Loading O*NET tasks...")
    if not os.path.exists("data/raw/onet_tasks.csv"):
        print("data/raw/onet_tasks.csv not found. Please run download_data.py first.")
        return

    onet_tasks_df = pd.read_csv("data/raw/onet_tasks.csv")
    sampled_tasks_df = onet_tasks_df.sample(n=sample_size, random_state=42).copy()

    results = []
    print(f"Classifying {sample_size} tasks...")

    for _, row in sampled_tasks_df.iterrows():
        title = row.get("Title", "")
        task_statement = row.get("Task", "")
        print(f"[{len(results) + 1}/{sample_size}] Processing Task for '{title}'...")

        try:
            classification_result_dict = classify_task(title, task_statement)
            results.append(
                {
                    "O*NET-SOC Code": row.get("O*NET-SOC Code", ""),
                    "Title": title,
                    "Task ID": row.get("Task ID", ""),
                    "Task": task_statement,
                    "Demand Type": classification_result_dict.get("label"),
                    "Justification": classification_result_dict.get("justification"),
                }
            )
        except Exception as e:
            print(f"  Error: {e}")
            results.append(
                {
                    "O*NET-SOC Code": row.get("O*NET-SOC Code", ""),
                    "Title": title,
                    "Task ID": row.get("Task ID", ""),
                    "Task": task_statement,
                    "Demand Type": "ERROR",
                    "Justification": str(e),
                }
            )

    classification_results_df = pd.DataFrame(results)
    os.makedirs("data/output", exist_ok=True)
    classification_results_df.to_csv("data/output/classified_tasks_batch1.csv", index=False)
    print("Saved classification results to data/output/classified_tasks_batch1.csv")


# ── Full classification (all tasks, grouped by occupation) ────────────────────

CHECKPOINT_PATH = "data/output/classified_all_tasks_checkpoint.csv"
FINAL_PATH = "data/output/classified_all_tasks.csv"


def classify_all(delay_between_tasks: float = 0.3):
    """
    Classify every O*NET task, grouped by occupation code.
    Uses a checkpoint file so execution can be safely interrupted and resumed.
    """
    print("Loading O*NET tasks...")
    if not os.path.exists("data/raw/onet_tasks.csv"):
        print("data/raw/onet_tasks.csv not found. Please run download_data.py first.")
        return

    onet_tasks_df = pd.read_csv("data/raw/onet_tasks.csv")
    total = len(onet_tasks_df)
    print(f"Total tasks to classify: {total}")

    # ── Load checkpoint if it exists ─────────────────────────────────────────
    done_ids: set = set()
    existing_rows: list = []
    if os.path.exists(CHECKPOINT_PATH):
        checkpoint_df = pd.read_csv(CHECKPOINT_PATH)
        done_ids = set(checkpoint_df["Task ID"].astype(str).tolist())
        existing_rows = checkpoint_df.to_dict(orient="records")
        print(f"Resuming from checkpoint — {len(done_ids)} tasks already done.")

    # ── Iterate grouped by O*NET-SOC Code ────────────────────────────────────
    groups = onet_tasks_df.groupby("O*NET-SOC Code", sort=True)
    results = list(existing_rows)
    processed = len(done_ids)
    errors = 0

    for occ_code, group in groups:
        occ_title = group["Title"].iloc[0]

        # Skip occupations already fully classified
        occ_task_ids = set(group["Task ID"].astype(str).tolist())
        remaining = occ_task_ids - done_ids
        if not remaining:
            continue

        print(f"\n── {occ_title} ({occ_code}) — {len(remaining)} tasks remaining ──")

        for _, row in group.iterrows():
            task_id = str(row.get("Task ID", ""))
            if task_id in done_ids:
                continue

            task_statement = row.get("Task", "")
            print(f"  [{processed + 1}/{total}] {task_statement[:70]}...")

            try:
                classification_result_dict = classify_task(occ_title, task_statement)
                results.append(
                    {
                        "O*NET-SOC Code": occ_code,
                        "Title": occ_title,
                        "Task ID": task_id,
                        "Task": task_statement,
                        "Demand Type": classification_result_dict.get("label"),
                        "Justification": classification_result_dict.get("justification"),
                    }
                )
            except Exception as e:
                print(f"  Error: {e}")
                errors += 1
                results.append(
                    {
                        "O*NET-SOC Code": occ_code,
                        "Title": occ_title,
                        "Task ID": task_id,
                        "Task": task_statement,
                        "Demand Type": "ERROR",
                        "Justification": str(e),
                    }
                )

            processed += 1
            done_ids.add(task_id)
            time.sleep(delay_between_tasks)

        # ── Checkpoint after each occupation ─────────────────────────────────
        pd.DataFrame(results).to_csv(CHECKPOINT_PATH, index=False)

    # ── Write final output ───────────────────────────────────────────────────
    final_results_df = pd.DataFrame(results)
    os.makedirs("data/output", exist_ok=True)
    final_results_df.to_csv(FINAL_PATH, index=False)
    print(f"\nDone! {processed} tasks processed ({errors} errors).")
    print(f"Saved to {FINAL_PATH}")
    return final_results_df


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "sample"
    if mode == "all":
        classify_all()
    else:
        classify_random_sample(100)
