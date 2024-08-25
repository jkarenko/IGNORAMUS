import os
import subprocess
import sys
import tomllib as toml

import requests
from packaging import version


def get_pyproject_data():
    try:
        # Get the directory of the current script
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Construct the path to pyproject.toml
        pyproject_path = os.path.join(script_dir, '../pyproject.toml')

        # Read the pyproject.toml file
        with open(pyproject_path, 'rb') as f:
            pyproject_data = toml.load(f)

        return pyproject_data
    except Exception as e:
        print(f"Error reading pyproject.toml: {str(e)}")
        return None


def get_current_version():
    pyproject_data = get_pyproject_data()
    if pyproject_data and 'tool' in pyproject_data and 'poetry' in pyproject_data['tool']:
        return pyproject_data['tool']['poetry']['version']
    print("Version information not found in pyproject.toml")
    return None


def check_latest_version(current_version):
    pyproject_data = get_pyproject_data()
    if not pyproject_data:
        return False, "Unable to read pyproject.toml"

    tags_url = pyproject_data['tool']['poetry']['urls']['repo_api'] + '/refs/tags'

    # Get GitHub token from environment variable
    github_token = os.environ.get('GITHUB_TOKEN')

    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    try:
        return _extracted_from_check_latest_version_21(tags_url, headers, current_version)
    except requests.RequestException as e:
        if not isinstance(e, requests.HTTPError):
            return False, f"Error checking for updates: {str(e)}"
        if e.response.status_code == 401:
            return False, "Error: Authentication failed. Please check your GitHub token."
        elif e.response.status_code == 404:
            return (False, "Error: Repository or tags not found. Please check the repository URL.",)
        else:
            return False, f"HTTP Error: {e.response.status_code} - {e.response.reason}"


# TODO Rename this here and in `check_latest_version`
def _extracted_from_check_latest_version_21(tags_url, headers, current_version):
    # Fetch the tags from GitHub
    response = requests.get(tags_url, headers=headers)
    response.raise_for_status()  # Raise an exception for HTTP errors
    tags = response.json()

    if not tags:
        return False, "No tags found in the repository"

    # Extract version numbers from tags and sort them
    versions = [tag['ref'].split("/v")[1] for tag in tags]
    latest_version = max(versions, key=version.parse)

    # Compare the current version with the latest version
    return ((True, f"You are running the latest version ({current_version})") if version.parse(
        current_version) >= version.parse(latest_version) else (
        False, f"A newer version is available: {latest_version} (you are running {current_version})",))


def update_application():
    update_files = subprocess.run(["git", "pull"], capture_output=True, text=True)
    if update_files.returncode == 0:
        print("Updated files successfully")
        print(update_files.stdout)
    else:
        print("Update failed, check output below")
        print(update_files.stderr)
        sys.exit(1)

    # Install dependencies
    install_deps = subprocess.run(["poetry", "install"], capture_output=True, text=True)
    if install_deps.returncode == 0:
        print("Dependencies installed successfully")
        print(install_deps.stdout)
    else:
        print("Dependency installation failed, check output below")
        print(install_deps.stderr)
        sys.exit(1)


def check_updates():
    if current_version := get_current_version():
        is_latest, message = check_latest_version(current_version)
        print(message)
        if not is_latest:
            update = input("Update to the latest version from GitHub? (Y/n): ")
            if update.lower() in ["y", "yes", ""]:
                update_application()
                restart_application()
    else:
        print("Unable to determine the current version.")


def restart_application():
    print("Restarting application...")
    os.execv(sys.executable, ["poetry", "run", "ignoramus"])
