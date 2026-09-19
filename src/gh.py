import logging
import os
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from github import Github
from github import GithubException

try:
    from github import Auth
    _has_auth_token = hasattr(Auth, "Token")
except ImportError:  # PyGithub < 2.0 fallback
    Auth = None
    _has_auth_token = False


class GH:
    def __init__(self, ghToken: str):
        self.token = ghToken
        if _has_auth_token:
            self.github = Github(auth=Auth.Token(self.token))
        else:
            self.github = Github(self.token)

    def downloadReleaseAssets(self, module: dict) -> bool:
        try:
            ghRepo = self.github.get_repo(module["repo"])
        except GithubException as e:
            if hasattr(e, "status") and e.status == 403:
                logging.error(f"GitHub API rate limit or permissions error for: {module['repo']}")
            else:
                logging.error(f"Unable to get repo {module['repo']}: {e}")
            return False

        # Use pinned tag when specified (supports pre-releases),
        # otherwise use get_latest_release() to skip drafts and pre-releases
        try:
            if module.get("releaseTag"):
                ghLatestRelease = ghRepo.get_release(module["releaseTag"])
            else:
                ghLatestRelease = ghRepo.get_latest_release()
        except GithubException as e:
            if hasattr(e, "status") and e.status == 403:
                logging.error(f"GitHub API rate limit exceeded for: {module['repo']}")
            else:
                logging.warning(f"No published release found for: {module['repo']}")
            return False

        downloaded = False
        try:
            assets = list(ghLatestRelease.get_assets())
        except GithubException as e:
            logging.error(f"[{module['repo']}] Failed to list release assets: {e}")
            return False
        for pattern in module["regex"]:
            try:
                compiled = re.compile(pattern)
            except re.error as e:
                logging.error(f"[{module['repo']}] Invalid regex '{pattern}': {e}")
                continue
            for asset in assets:
                if compiled.search(asset.name):
                    logging.info(f"[{module['repo']}] Downloading: {asset.name}")
                    fpath = Path(f"./base/{module['repo']}/")
                    fpath.mkdir(parents=True, exist_ok=True)
                    filepath = str(fpath / asset.name)
                    try:
                        self._download_asset(asset, filepath)
                        downloaded = True
                    except Exception as e:
                        logging.error(f"[{module['repo']}] Failed to download {asset.name}: {e}")

        if not downloaded:
            logging.warning(f"No assets matched patterns for: {module['repo']}")
        return downloaded

    def _download_asset(self, asset, filepath: str, timeout: int = 60):
        """Download a release asset atomically with fallback between public URL and API URL."""
        tmp_filepath = filepath + ".part"
        # Ensure no stale partial file is left behind
        try:
            if os.path.exists(tmp_filepath):
                os.remove(tmp_filepath)
        except OSError:
            pass

        # 1. First attempt: browser download URL (works directly for public releases, avoiding S3 auth issues)
        if asset.browser_download_url:
            try:
                req = urllib.request.Request(asset.browser_download_url)
                req.add_header("User-Agent", "DeepSea-Builder/1.0")
                with urllib.request.urlopen(req, timeout=timeout) as response, open(tmp_filepath, "wb") as out:
                    shutil.copyfileobj(response, out)
                os.replace(tmp_filepath, filepath)
                return
            except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError) as e:
                logging.debug(f"Public browser download failed ({e}), attempting API download fallback...")
                try:
                    if os.path.exists(tmp_filepath):
                        os.remove(tmp_filepath)
                except OSError:
                    pass

        # 2. Second attempt: Authenticated API stream endpoint (supports private repositories)
        try:
            api_req = urllib.request.Request(asset.url)
            api_req.add_header("Authorization", f"token {self.token}")
            api_req.add_header("Accept", "application/octet-stream")
            api_req.add_header("User-Agent", "DeepSea-Builder/1.0")
            with urllib.request.urlopen(api_req, timeout=timeout) as response, open(tmp_filepath, "wb") as out:
                shutil.copyfileobj(response, out)
            os.replace(tmp_filepath, filepath)
        except Exception:
            try:
                if os.path.exists(tmp_filepath):
                    os.remove(tmp_filepath)
            except OSError:
                pass
            raise