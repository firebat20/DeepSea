import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

from fs import FS
from gh import GH

# Ensure all relative paths resolve from the script's own directory,
# regardless of where the user invokes the script from.
os.chdir(Path(__file__).resolve().parent)

logging.basicConfig(format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logging.getLogger().setLevel(logging.INFO)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Team Neptune's DeepSea build script.")
    requiredNamed = parser.add_argument_group('Options required to build a release candidate')
    requiredNamed.add_argument('-gt', '--githubToken', help='Github Token', required=True)
    args = parser.parse_args()

    token = args.githubToken.strip() if args.githubToken else ""
    if not token:
        logging.error("GitHub token cannot be empty.")
        sys.exit(1)

    sdcard = FS()
    github = GH(token)

    try:
        with open('./settings.json', 'r', encoding='utf-8') as f:
            settings = json.load(f)
    except FileNotFoundError:
        logging.error("settings.json not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.error(f"settings.json contains invalid JSON: {e}")
        sys.exit(1)

    # Collect modules in deterministic order while eliminating duplicates
    needed_modules_ordered = []
    seen = set()
    for package in settings.get("packages", []):
        if package.get("active"):
            for module_name in package.get("modules", []):
                if module_name not in seen:
                    seen.add(module_name)
                    needed_modules_ordered.append(module_name)

    failed_modules = set()
    module_list = settings.get("moduleList", {})

    for module_name in needed_modules_ordered:
        if module_name not in module_list:
            logging.error(f"Module '{module_name}' not found in moduleList, skipping.")
            failed_modules.add(module_name)
            continue
        module = module_list[module_name]
        if not github.downloadReleaseAssets(module):
            logging.error(f"Failed to download assets for module '{module_name}', skipping.")
            failed_modules.add(module_name)

    for package in settings.get("packages", []):
        if package.get("active"):
            logging.info(f"[{package['name']}] Creating package")
            sdcard.createSDEnv()

            for module_name in package.get("modules", []):
                if module_name in failed_modules:
                    logging.warning(f"[{package['name']}] Skipping module '{module_name}' due to earlier failure.")
                    continue
                if module_name not in module_list:
                    logging.error(f"[{package['name']}] Module '{module_name}' not found in moduleList, skipping.")
                    continue

                module = module_list[module_name]
                try:
                    logging.info(f"[{package['name']}][{module['repo']}] Creating module env")
                    sdcard.createModuleEnv(module)
                    for step in module.get("steps", []):
                        logging.info(f"[{package['name']}][{module['repo']}] Executing step: {step['name']}")
                        sdcard.executeStep(module, step)

                    logging.info(f"[{package['name']}][{module['repo']}] Moving MENV to SD")
                    sdcard.finishModule()
                except Exception as e:
                    logging.error(f"[{package['name']}][{module['repo']}] Failed to process module: {e}")
                    failed_modules.add(module_name)

            logging.info(f"[{package['name']}] All modules processed.")
            release_ver = settings.get("releaseVersion", "unknown")
            logging.info(f"[{package['name']}] Creating ZIP")
            shutil.make_archive(f"deepsea-{package['name']}_v{release_ver}", 'zip', "./sd")

    # Clean up working directories after build
    shutil.rmtree("./base", ignore_errors=True)
    shutil.rmtree("./menv", ignore_errors=True)
    shutil.rmtree("./sd", ignore_errors=True)

    if failed_modules:
        logging.warning(f"Build completed with failures in modules: {', '.join(sorted(failed_modules))}")
        sys.exit(1)
    else:
        logging.info("Build completed successfully.")
