import hashlib
import json
from typing import Any

def calculate_merkle_root(data: Any) -> str:
    """
    Computes Merkle Root hash based on leaf data elements.
    """
    if data is None:
        return hashlib.sha256(b"").hexdigest()
        
    leaves = []
    if isinstance(data, dict):
        for k in sorted(data.keys()):
            val = data[k]
            val_str = json.dumps(val, sort_keys=True, ensure_ascii=False)
            leaf_hash = hashlib.sha256(f"{k}:{val_str}".encode("utf-8")).hexdigest()
            leaves.append(leaf_hash)
    elif isinstance(data, list):
        for item in data:
            item_str = json.dumps(item, sort_keys=True, ensure_ascii=False)
            leaf_hash = hashlib.sha256(item_str.encode("utf-8")).hexdigest()
            leaves.append(leaf_hash)
    else:
        leaf_hash = hashlib.sha256(str(data).encode("utf-8")).hexdigest()
        leaves.append(leaf_hash)
        
    if not leaves:
        return hashlib.sha256(b"").hexdigest()
        
    nodes = leaves
    while len(nodes) > 1:
        temp_nodes = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i+1] if i+1 < len(nodes) else left
            combined = hashlib.sha256((left + right).encode("utf-8")).hexdigest()
            temp_nodes.append(combined)
        nodes = temp_nodes
        
    return nodes[0]
