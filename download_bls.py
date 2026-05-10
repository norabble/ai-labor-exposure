import io
import os
import zipfile

import requests


def download_bls_oews(year_suffix):
    url = f"https://www.bls.gov/oes/special.requests/oesm{year_suffix}nat.zip"
    print(f"Downloading {url}...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed with status code {response.status_code}")
        print(response.headers)
        return False

    print(f"Successfully downloaded {len(response.content) / (1024 * 1024):.2f} MB")

    # Extract the zip
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        z.extractall("data/raw/bls")
        print(f"Extracted files: {z.namelist()}")

    return True


if __name__ == "__main__":
    os.makedirs("data/raw/bls", exist_ok=True)
    download_bls_oews("23")
    download_bls_oews("22")
