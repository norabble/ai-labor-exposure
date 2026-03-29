import os
import io
import requests
import pandas as pd

ONET_TASKS_URL = "https://www.onetcenter.org/dl_files/database/db_28_2_excel/Task%20Statements.xlsx"
ANTHROPIC_TASK_PENETRATION_URL = "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main/labor_market_impacts/task_penetration.csv"
ANTHROPIC_JOB_EXPOSURE_URL = "https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/main/labor_market_impacts/job_exposure.csv"
ELOUNDOU_EXPOSURE_URL = "https://raw.githubusercontent.com/openai/GPTs-are-GPTs/main/data/occ_level.csv"

def download_onet_tasks():
    print("Downloading O*NET Task Statements...")
    response = requests.get(ONET_TASKS_URL)
    response.raise_for_status()
    
    print("Parsing O*NET tasks...")
    # Read the Excel file into a pandas DataFrame
    df_tasks = pd.read_excel(io.BytesIO(response.content))
    
    print(f"Loaded {len(df_tasks)} task statements.")
    df_tasks.to_csv("onet_tasks.csv", index=False)
    print("Saved onet_tasks.csv")
    return df_tasks

def download_anthropic_data():
    print("Downloading Anthropic task penetration data...")
    task_res = requests.get(ANTHROPIC_TASK_PENETRATION_URL)
    task_res.raise_for_status()
    df_task_pen = pd.read_csv(io.StringIO(task_res.text))
    df_task_pen.to_csv("anthropic_task_penetration.csv", index=False)
    print(f"Saved anthropic_task_penetration.csv ({len(df_task_pen)} rows)")
    
    print("Downloading Anthropic job exposure data...")
    job_res = requests.get(ANTHROPIC_JOB_EXPOSURE_URL)
    job_res.raise_for_status()
    df_job_exp = pd.read_csv(io.StringIO(job_res.text))
    df_job_exp.to_csv("anthropic_job_exposure.csv", index=False)
    print(f"Saved anthropic_job_exposure.csv ({len(df_job_exp)} rows)")
    
    return df_task_pen, df_job_exp

def download_eloundou_data():
    print("Downloading Eloundou et al. occupation exposure data...")
    response = requests.get(ELOUNDOU_EXPOSURE_URL)
    response.raise_for_status()
    
    df_exposure = pd.read_csv(io.StringIO(response.text))
    print(f"Loaded exposure data for {len(df_exposure)} occupations.")
    df_exposure.to_csv("eloundou_exposure.csv", index=False)
    print("Saved eloundou_exposure.csv")
    return df_exposure

if __name__ == "__main__":
    download_onet_tasks()
    download_anthropic_data()
    download_eloundou_data()
