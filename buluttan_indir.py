# -*- coding: utf-8 -*-
"""
GitHub Actions Bulut Derleme Takip ve İndirme Aracı
===================================================
GitHub üzerinde çalışan 'Google Play Store (AAB & APK) Paketi Olustur' iş akışını
bekler, tamamlandığında üretilen .aab, .apk ve upload-keystore.jks dosyalarını
otomatik olarak 'PlayStore/apk_ve_aab_ciktilari' klasörüne indirip çıkartır.
"""

import io
import json
import os
import subprocess
import sys
import time
import urllib.request
import zipfile

REPO = "1newsimplestudio-maker/kisisel-kasa-playstore"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "apk_ve_aab_ciktilari")


def get_github_token() -> str:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        capture_output=True,
    )
    creds = dict(
        line.split("=", 1)
        for line in proc.stdout.splitlines()
        if "=" in line
    )
    return creds["password"]


def api_get(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "KisiselKasaDownloader",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def download_artifact(url: str, token: str, dest_dir: str) -> None:
    os.makedirs(dest_dir, exist_ok=True)

    class NoAuthRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            new_req = urllib.request.Request(
                newurl, headers={"User-Agent": "KisiselKasaDownloader"}
            )
            return new_req

    opener = urllib.request.build_opener(NoAuthRedirectHandler)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "KisiselKasaDownloader",
        },
    )
    with opener.open(req) as resp:
        zip_bytes = resp.read()

    zip_path = os.path.join(dest_dir, "Kisisel-Kasa-GooglePlay-Paketi.zip")
    with open(zip_path, "wb") as f:
        f.write(zip_bytes)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(dest_dir)

    print(f"ZIP indirildi ve çıkartıldı: {dest_dir}")


def main():
    token = get_github_token()
    head_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=BASE_DIR, text=True
    ).strip()
    print(f"GitHub Actions derlemesi kontrol ediliyor ({REPO}, commit: {head_sha[:7]})...")

    while True:
        data = api_get(
            f"https://api.github.com/repos/{REPO}/actions/runs?head_sha={head_sha}",
            token,
        )
        runs = data.get("workflow_runs", [])
        if not runs:
            print("Yeni iş akışı başlatılıyor, bekleniyor...")
            time.sleep(8)
            continue

        run = runs[0]
        run_id = run["id"]
        status = run["status"]
        conclusion = run.get("conclusion")
        html_url = run["html_url"]

        print(f"[Run #{run_id}] Durum: {status} | Sonuç: {conclusion} | {html_url}")

        if status == "completed":
            if conclusion == "success":
                print("Derleme başarıyla tamamlandı! Dosyalar indiriliyor...")
                artifacts_data = api_get(
                    f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/artifacts",
                    token,
                )
                for art in artifacts_data.get("artifacts", []):
                    dl_url = art["archive_download_url"]
                    download_artifact(dl_url, token, OUT_DIR)
                print("TÜM DOSYALAR BAŞARIYLA İNDİRİLDİ!")
                return 0
            else:
                # Hata varsa hangi adımda hata olduğunu göster
                jobs_data = api_get(
                    f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/jobs",
                    token,
                )
                for job in jobs_data.get("jobs", []):
                    for step in job.get("steps", []):
                        if step.get("conclusion") == "failure":
                            print(f"Hatalı adım: {step['name']}")
                return 1

        time.sleep(20)


if __name__ == "__main__":
    sys.exit(main())

