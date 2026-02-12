import os
import json
from pathlib import Path

PROJECTS_DIR = "projects"
CONFIG_FILE = "project_config.json"

def ensure_projects_dir():
    """Creates the projects directory"""
    if not os.path.exists(PROJECTS_DIR):
        os.makedirs(PROJECTS_DIR)
    return PROJECTS_DIR

def get_project_path(project_name):
    """Returns the full path of the project directory"""
    ensure_projects_dir()
    return os.path.join(PROJECTS_DIR, project_name)

def get_blockchain_file(project_name):
    """Returns the full path of the blockchain file (legacy - for backward compatibility)"""
    project_path = get_project_path(project_name)
    if not os.path.exists(project_path):
        os.makedirs(project_path, exist_ok=True)
    return os.path.join(project_path, "blockchain.json")

def get_blockchain_file_with_id(project_name, blockchain_id):
    """Returns the full path of the blockchain file with unique ID"""
    project_path = get_project_path(project_name)
    if not os.path.exists(project_path):
        os.makedirs(project_path, exist_ok=True)
    return os.path.join(project_path, f"blockchain_{blockchain_id}.json")

def list_blockchains_in_project(project_name):
    """Lists all blockchain files in a project"""
    project_path = get_project_path(project_name)
    if not os.path.exists(project_path):
        return []
    
    blockchains = []
    for file in os.listdir(project_path):
        if file.startswith("blockchain_") and file.endswith(".json"):
            blockchain_id = file.replace("blockchain_", "").replace(".json", "")
            file_path = os.path.join(project_path, file)
            blockchains.append({
                "id": blockchain_id,
                "filename": file,
                "path": file_path
            })
    return sorted(blockchains, key=lambda x: x["filename"])

def get_tokens_file(project_name):
    """Returns the full path of the tokens file"""
    project_path = get_project_path(project_name)
    ensure_projects_dir()
    if not os.path.exists(project_path):
        os.makedirs(project_path, exist_ok=True)
    return os.path.join(project_path, "tokens.json")

def create_project(project_name):
    """Creates a new project directory"""
    project_path = get_project_path(project_name)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
        return True
    return False

def save_project_metadata(project_name, encrypted=False):
    """Saves project metadata (encryption status, etc.)"""
    project_path = get_project_path(project_name)
    metadata_file = os.path.join(project_path, "metadata.json")
    metadata = {"encrypted": encrypted}
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)
        return True
    except:
        return False

def list_projects():
    """Returns a list of existing projects"""
    ensure_projects_dir()
    if not os.path.exists(PROJECTS_DIR):
        return []
    
    projects = []
    for item in os.listdir(PROJECTS_DIR):
        project_path = os.path.join(PROJECTS_DIR, item)
        if os.path.isdir(project_path):
            blockchain_file = os.path.join(project_path, "blockchain.json")
            has_blockchain = os.path.exists(blockchain_file)
            projects.append({
                "name": item,
                "path": project_path,
                "has_blockchain": has_blockchain
            })
    return sorted(projects, key=lambda x: x["name"])

def project_exists(project_name):
    """Checks if project exists"""
    project_path = get_project_path(project_name)
    return os.path.exists(project_path)

def get_last_project():
    """Returns the last used project"""
    if not os.path.exists(CONFIG_FILE):
        return None
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            last_project = config.get("last_project")
            if last_project and project_exists(last_project):
                return last_project
    except:
        pass
    return None

def set_last_project(project_name):
    """Saves the last used project"""
    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except:
            pass
    
    config["last_project"] = project_name
    
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def get_project_info(project_name):
    """Returns information about the project"""
    project_path = get_project_path(project_name)
    blockchain_file = get_blockchain_file(project_name)
    tokens_file = get_tokens_file(project_name)
    metadata_file = os.path.join(project_path, "metadata.json")
    
    info = {
        "name": project_name,
        "path": project_path,
        "blockchain_exists": os.path.exists(blockchain_file),
        "tokens_exists": os.path.exists(tokens_file),
        "encrypted": False
    }
    
    # Load metadata if exists
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                info["encrypted"] = metadata.get("encrypted", False)
        except:
            pass
    
    if info["blockchain_exists"]:
        try:
            with open(blockchain_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    info["block_count"] = len(data)
                elif isinstance(data, dict) and "blocks" in data:
                    info["block_count"] = len(data["blocks"])
                else:
                    info["block_count"] = 0
        except:
            info["block_count"] = 0
    
    return info

def delete_project(project_name):
    """Deletes a project (use with caution!)"""
    import shutil
    project_path = get_project_path(project_name)
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
        return True
    return False
