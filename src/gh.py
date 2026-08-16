
from pathlib import Path
from github import Github
import urllib.request
import re
import logging

class GH():
    def __init__(self, ghToken):
        self.token = ghToken
        self.github = Github(self.token)

    def downloadReleaseAssets(self, module):
        try:
            ghRepo = self.github.get_repo(module["repo"])
        except Exception as e:
            logging.exception(f"Unable to get: {module['repo']}")
            return False
        
        releases = ghRepo.get_releases()
        try:
            ghLatestRelease = releases[0]
        except IndexError:
            logging.warning(f"No available release for: {module['repo']}")
            return False

        downloaded = False
        for pattern in module["regex"]:
            for asset in ghLatestRelease.get_assets():
                if re.search(pattern, asset.name):
                    logging.info(f"[{module['repo']}] Downloading: {asset.name}")
                    fpath = f"./base/{module['repo']}/"
                    Path(fpath).mkdir(parents=True, exist_ok=True)
                    try:
                        urllib.request.urlretrieve(asset.browser_download_url, f"{fpath}{asset.name}")
                        downloaded = True
                    except Exception as e:
                        logging.error(f"[{module['repo']}] Failed to download {asset.name}: {e}")
        if not downloaded:
            logging.warning(f"No assets matched patterns for: {module['repo']}")
        return downloaded