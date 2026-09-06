import io
import os

import pandas as pd
import requests

ONET_TASKS_URL = "https://www.onetcenter.org/dl_files/database/db_28_2_excel/Task%20Statements.xlsx"
ONET_TASK_RATINGS_URL = "https://www.onetcenter.org/dl_files/database/db_28_2_excel/Task%20Ratings.xlsx"
ANTHROPIC_TASK_PENETRATION_URL = (
    "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main/labor_market_impacts/task_penetration.csv"
)
ANTHROPIC_JOB_EXPOSURE_URL = "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main/labor_market_impacts/job_exposure.csv"
ANTHROPIC_TASK_CONVERSATION_PCT_URL = (
    "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main/release_2025_03_27/task_pct_v2.csv"
)
ELOUNDOU_EXPOSURE_URL = "https://raw.githubusercontent.com/openai/GPTs-are-GPTs/main/data/occ_level.csv"


def download_onet_tasks():
    print("Downloading O*NET Task Statements...")
    response = requests.get(ONET_TASKS_URL)
    response.raise_for_status()

    print("Parsing O*NET tasks...")
    # Read the Excel file into a pandas DataFrame
    onet_tasks_df = pd.read_excel(io.BytesIO(response.content))

    print(f"Loaded {len(onet_tasks_df)} task statements.")
    onet_tasks_df.to_csv("data/raw/onet_tasks.csv", index=False)
    print("Saved data/raw/onet_tasks.csv")
    return onet_tasks_df


def download_onet_task_ratings():
    print("Downloading O*NET Task Ratings...")
    response = requests.get(ONET_TASK_RATINGS_URL)
    response.raise_for_status()

    print("Parsing O*NET task ratings...")
    task_ratings_df = pd.read_excel(io.BytesIO(response.content))

    # Filter for Importance (IM)
    importance_df = task_ratings_df[task_ratings_df["Scale ID"] == "IM"].copy()

    # Rename for clarity
    importance_df = importance_df.rename(columns={"Data Value": "task_importance"})

    # Keep only what we need
    importance_df = importance_df[["Task ID", "task_importance"]]

    importance_df.to_csv("data/raw/onet_task_ratings.csv", index=False)
    print(f"Saved data/raw/onet_task_ratings.csv ({len(importance_df)} task weights)")
    return importance_df


def download_anthropic_data():
    print("Downloading Anthropic task penetration data...")
    task_penetration_response = requests.get(ANTHROPIC_TASK_PENETRATION_URL)
    task_penetration_response.raise_for_status()
    task_penetration_df = pd.read_csv(io.StringIO(task_penetration_response.text))
    task_penetration_df.to_csv("data/raw/anthropic_task_penetration.csv", index=False)
    print(f"Saved data/raw/anthropic_task_penetration.csv ({len(task_penetration_df)} rows)")

    print("Downloading Anthropic job exposure data...")
    job_exposure_response = requests.get(ANTHROPIC_JOB_EXPOSURE_URL)
    job_exposure_response.raise_for_status()
    job_exposure_df = pd.read_csv(io.StringIO(job_exposure_response.text))
    job_exposure_df.to_csv("data/raw/anthropic_job_exposure.csv", index=False)
    print(f"Saved data/raw/anthropic_job_exposure.csv ({len(job_exposure_df)} rows)")

    print("Downloading Anthropic task conversation % data...")
    task_conv_pct_response = requests.get(ANTHROPIC_TASK_CONVERSATION_PCT_URL)
    task_conv_pct_response.raise_for_status()
    task_conv_pct_df = pd.read_csv(io.StringIO(task_conv_pct_response.text))
    task_conv_pct_df.to_csv("data/raw/anthropic_task_conversation_pct.csv", index=False)
    print(f"Saved data/raw/anthropic_task_conversation_pct.csv ({len(task_conv_pct_df)} rows)")

    return task_penetration_df, job_exposure_df


def download_eloundou_data():
    print("Downloading Eloundou et al. occupation exposure data...")
    response = requests.get(ELOUNDOU_EXPOSURE_URL)
    response.raise_for_status()

    eloundou_exposure_df = pd.read_csv(io.StringIO(response.text))
    print(f"Loaded exposure data for {len(eloundou_exposure_df)} occupations.")
    eloundou_exposure_df.to_csv("data/raw/eloundou_exposure.csv", index=False)
    print("Saved data/raw/eloundou_exposure.csv")
    return eloundou_exposure_df


if __name__ == "__main__":
    os.makedirs("data/raw/", exist_ok=True)
    download_onet_tasks()
    download_onet_task_ratings()
    download_anthropic_data()
    download_eloundou_data()
