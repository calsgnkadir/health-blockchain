import os
import json
from pathlib import Path

# Constants
PROJECTS_DIR = "projects"
CONFIG_FILE = "project_config.json"

def ensure_projects_dir():
    """Creates the projects directory if it doesn't exist."""
    if not os.path.exists(PROJECTS_DIR):
        os.makedirs(PROJECTS_DIR)
    return PROJECTS_DIR

def get_project_path(project_name):
    """Returns the full path of the project directory."""
    ensure_projects_dir()
    return os.path.join(PROJECTS_DIR, project_name)

def get_blockchain_file(project_name):
    """Returns the full path of the blockchain file."""
    project_path = get_project_path(project_name)
    if not os.path.exists(project_path):
        os.makedirs(project_path, exist_ok=True)
    return os.path.join(project_path, "blockchain.json")

def create_project(project_name):
    """Creates a new project directory."""
    project_path = get_project_path(project_name)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
        return True
    return False

def list_projects():
    """Returns a list of existing project names."""
    ensure_projects_dir()
    if not os.path.exists(PROJECTS_DIR):
        return []
    
    projects = []
    for item in os.listdir(PROJECTS_DIR):
        project_path = os.path.join(PROJECTS_DIR, item)
        if os.path.isdir(project_path):
            projects.append(item)
    return sorted(projects)

def project_exists(project_name):
    """Checks if a project exists."""
    project_path = get_project_path(project_name)
    return os.path.exists(project_path)

def save_json(filepath, data):
    """Saves data as JSON to filepath."""
    folder = os.path.dirname(filepath)
    if folder:
        os.makedirs(folder, exist_ok=True)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load_json(filepath):
    """Loads JSON data from filepath."""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
