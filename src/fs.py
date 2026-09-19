import glob
import logging
import os
import re
import shutil
import zipfile
from pathlib import Path


class FS:
    BASE_DIR = "./base"
    MENV_DIR = "./menv"
    SD_DIR = "./sd"

    def __init__(self):
        shutil.rmtree(self.BASE_DIR, ignore_errors=True)
        shutil.rmtree(self.MENV_DIR, ignore_errors=True)
        shutil.rmtree(self.SD_DIR, ignore_errors=True)
        for element in glob.glob("./*.zip"):
            os.remove(element)

    def createSDEnv(self):
        shutil.rmtree(self.SD_DIR, ignore_errors=True)
        Path(self.SD_DIR).mkdir(parents=True, exist_ok=True)

    def createModuleEnv(self, module: dict):
        shutil.rmtree(self.MENV_DIR, ignore_errors=True)
        Path(self.MENV_DIR).mkdir(parents=True, exist_ok=True)
        repo_path = f"{self.BASE_DIR}/{module['repo']}"
        if not os.path.isdir(repo_path):
            raise FileNotFoundError(f"Module repo directory not found: {repo_path}")
        shutil.copytree(repo_path, f"{self.MENV_DIR}/", dirs_exist_ok=True)

    def finishModule(self):
        self.__copyToSD()
        shutil.rmtree(self.MENV_DIR, ignore_errors=True)

    def executeStep(self, module: dict, step: dict):
        step_name = step.get("name")
        args = step.get("arguments", [])

        if step_name == "extract":
            self.__extract(args[0])
        elif step_name == "create_dir":
            self.__createDir(args[0])
        elif step_name == "create_file":
            self.__createFile(args[0], args[1])
        elif step_name == "replace_content":
            self.__replaceFileContent(args[0], args[1], args[2])
        elif step_name == "delete":
            self.__delete(args[0])
        elif step_name == "copy":
            self.__copy(args[0], args[1])
        elif step_name == "move":
            self.__move(args[0], args[1])
        else:
            logging.warning(f"Unknown step name: {step_name}")

    def __extract(self, source: str):
        # Pre-collect matches to avoid iterating over newly unpacked files
        matches = [f for f in os.listdir(self.MENV_DIR) if re.search(source, f)]
        for filename in matches:
            asset_path = os.path.join(self.MENV_DIR, filename)
            if not os.path.isfile(asset_path):
                continue
            try:
                with zipfile.ZipFile(asset_path, "r") as zip_ref:
                    # Validate all paths stay within MENV_DIR (Zip Slip protection)
                    menv_real = os.path.realpath(self.MENV_DIR)
                    for member in zip_ref.namelist():
                        member_path = os.path.realpath(os.path.join(self.MENV_DIR, member))
                        if not member_path.startswith(menv_real + os.sep) and member_path != menv_real:
                            raise ValueError(f"Zip slip detected: '{member}' escapes {self.MENV_DIR}")
                    zip_ref.extractall(self.MENV_DIR)
            except zipfile.BadZipFile:
                logging.error(f"Not a valid zip file, removing to avoid SD pollution: {filename}")
            except ValueError as e:
                logging.error(f"{e}, removing archive to avoid SD pollution: {filename}")
            finally:
                # Always remove the archive (valid or not) so it is never
                # copied to SD via finishModule()/__copyToSD().
                try:
                    self.__delete(filename)
                except OSError as e:
                    logging.error(f"Failed to remove archive {filename}: {e}")

    def __delete(self, source: str):
        matches = glob.glob(f"{self.MENV_DIR}/{source}")
        if not matches:
            target = f"{self.MENV_DIR}/{source}"
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.exists(target):
                os.remove(target)
            return

        for target in matches:
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.exists(target):
                os.remove(target)

    def __copy(self, source: str, dest: str):
        targets = self._resolve_copy_targets(source, dest)
        if not targets:
            logging.warning(f"Copy source matched no files: {source}")
            return

        for element, dest_path in targets:
            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
            if os.path.isdir(element):
                shutil.copytree(element, dest_path, dirs_exist_ok=True)
            else:
                # Bug 3: if dest resolves to an existing directory, copy into it
                # instead of replacing the directory with a file.
                if os.path.isdir(dest_path):
                    dest_path = os.path.join(dest_path, os.path.basename(element))
                    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(element, dest_path)

    def __move(self, source: str, dest: str):
        targets = self._resolve_copy_targets(source, dest)
        if not targets:
            logging.warning(f"Move source matched no files: {source}")
            return

        for element, dest_path in targets:
            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
            if os.path.isdir(element) and not os.path.isdir(dest_path):
                # Merge directory contents when dest does not exist as dir yet
                shutil.copytree(element, dest_path, dirs_exist_ok=True)
            elif os.path.isdir(element):
                shutil.copytree(element, dest_path, dirs_exist_ok=True)
            else:
                if os.path.isdir(dest_path):
                    dest_path = os.path.join(dest_path, os.path.basename(element))
                    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(element, dest_path)
        # Bug 4: delete only what was actually copied, not every glob match.
        for element, _ in targets:
            if os.path.isdir(element):
                shutil.rmtree(element, ignore_errors=True)
            elif os.path.exists(element):
                try:
                    os.remove(element)
                except OSError as e:
                    logging.error(f"Failed to remove moved source {element}: {e}")

    def _resolve_copy_targets(self, source: str, dest: str):
        """Map a (glob source, dest) pair to concrete (src, dst) file pairs.

        - Sorted matches for deterministic builds.
        - dest ending with '/' or existing as dir means "copy each match into dir".
        - Single match to file path means exact rename (with Bug 3 dir guard in caller).
        - Multiple matches to a file path keeps legacy first-only behaviour
          (e.g. hekate `bootloader/hekate_*` -> `update.bin`) but warns.
        """
        matches = sorted(glob.glob(f"{self.MENV_DIR}/{source}"))
        if not matches:
            return []
        dest_path = f"{self.MENV_DIR}/{dest}"
        dest_is_dir_hint = dest.endswith("/") or dest.endswith("\\") or os.path.isdir(dest_path)
        if dest_is_dir_hint:
            return [
                (element, os.path.join(dest_path, os.path.basename(element.rstrip("/\\"))))
                for element in matches
            ]
        if len(matches) == 1:
            return [(matches[0], dest_path)]
        logging.warning(
            f"Multiple matches for '{source}' to single file '{dest}', "
            f"using first (sorted): {os.path.basename(matches[0])} from {[os.path.basename(m) for m in matches]}"
        )
        return [(matches[0], dest_path)]

    def __createDir(self, source: str):
        Path(f"{self.MENV_DIR}/{source}").mkdir(parents=True, exist_ok=True)

    def __createFile(self, source: str, content: str):
        filepath = Path(f"{self.MENV_DIR}/{source}")
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def __replaceFileContent(self, source: str, search: str, replace: str):
        filepath = f"{self.MENV_DIR}/{source}"
        if not os.path.exists(filepath):
            logging.warning(f"File not found for content replacement: {source}")
            return

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            data = f.read()

        if search not in data:
            logging.warning(f"Search string not found in {source}: '{search}'")

        data = data.replace(search, replace)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(data)

    def __copyToSD(self):
        # Bug 5: merge manually so overwrites are visible (last module wins).
        Path(f"{self.SD_DIR}/").mkdir(parents=True, exist_ok=True)
        for root, dirs, files in os.walk(self.MENV_DIR):
            rel = os.path.relpath(root, self.MENV_DIR)
            dest_root = self.SD_DIR if rel == "." else os.path.join(self.SD_DIR, rel)
            Path(dest_root).mkdir(parents=True, exist_ok=True)
            for fname in files:
                src = os.path.join(root, fname)
                # Skip symlinks/dirs that walked as files; copy real files only
                if not os.path.isfile(src) or os.path.islink(src):
                    continue
                dst = os.path.join(dest_root, fname)
                if os.path.exists(dst):
                    logging.warning(
                        f"Overwriting {os.path.relpath(dst, self.SD_DIR)} (last module wins)"
                    )
                shutil.copy2(src, dst)
