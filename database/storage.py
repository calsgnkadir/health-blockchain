
import os
import json
import lmdb
import shutil

# Constants
PROJECTS_DIR = "projects"

def ensure_projects_dir():
    """Creates the projects directory if it doesn't exist."""
    if not os.path.exists(PROJECTS_DIR):
        os.makedirs(PROJECTS_DIR)
    return PROJECTS_DIR

def get_project_path(project_name):
    """Returns the full path of the project directory."""
    ensure_projects_dir()
    return os.path.join(PROJECTS_DIR, project_name)

def get_db_path(project_name):
    """Returns the path to the LMDB database folder."""
    project_path = get_project_path(project_name)
    if not os.path.exists(project_path):
        os.makedirs(project_path, exist_ok=True)
    # LMDB creates its own files inside this folder
    return os.path.join(project_path, "chaindata.lmdb")

def create_project(project_name):
    """Creates a new project directory."""
    project_path = get_project_path(project_name)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
        return True
    return False

def project_exists(project_name):
    """Checks if a project exists."""
    project_path = get_project_path(project_name)
    return os.path.exists(project_path)

# ------------------------------------------------------------------
# LMDB CORE FUNCTIONS (Key-Value Store Implementation)
# ------------------------------------------------------------------

def open_db(project_name):
    """Opens LMDB environment."""
    path = get_db_path(project_name)
    # map_size needs to be large enough. 1GB for now.
    env = lmdb.open(path, map_size=1024 * 1024 * 1024, subdir=True)
    return env

def save_block_to_db(project_name, index, block_data):
    """Saves a block to LMDB. Key: Index, Value: JSON string."""
    env = open_db(project_name)
    try:
        with env.begin(write=True) as txn:
            # Keys must be bytes. We format index as 8-byte big-endian integer to keep sort order.
            # However, for simplicity and JSON compatibility, we can use string keys "0", "1"...
            # But string keys sort lexicographically ("1", "10", "2").
            # Let's use zero-padded strings for keys: "00000001".
            key = f"{index:010d}".encode('utf-8')
            
            # Serialize data to JSON bytes
            value = json.dumps(block_data).encode('utf-8')
            txn.put(key, value)
            
            # Update 'last_index' metadata
            txn.put(b"meta_last_index", str(index).encode('utf-8'))
    finally:
        env.close()

def load_all_blocks(project_name):
    """Loads all blocks from LMDB ordered by index."""
    if not project_exists(project_name):
        return []
        
    env = open_db(project_name)
    blocks = []
    try:
        with env.begin(write=False) as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                # Skip metadata keys
                if key.startswith(b"meta_"):
                    continue
                
                try:
                    block_data = json.loads(value.decode('utf-8'))
                    blocks.append(block_data)
                except Exception:
                    continue # Skip corrupted
    finally:
        env.close()
        
    # Ensure sorted by index (LMDB iterates by key, and we used zero-padded keys, so it should be sorted)
    return blocks

def reset_db(project_name):
    """Deletes the database to start fresh."""
    path = get_db_path(project_name)
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
        except Exception as e:
            print(f"Error resetting DB: {e}")
