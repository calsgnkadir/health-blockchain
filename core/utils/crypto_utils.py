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


def generate_merkle_proof(leaves: list, target_index: int) -> dict:
    """
    Generates Merkle Inclusion Proof (audit path) for a target leaf index.
    Returns proof nodes list with direction ('left'/'right') and the root.
    """
    if not leaves or target_index < 0 or target_index >= len(leaves):
        return {"proof": [], "root": None}

    nodes = list(leaves)
    idx = target_index
    proof = []

    while len(nodes) > 1:
        next_level = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else left

            if i == idx or i + 1 == idx:
                sibling = right if idx % 2 == 0 else left
                direction = "right" if idx % 2 == 0 else "left"
                proof.append({"position": direction, "hash": sibling})

            combined = hashlib.sha256((left + right).encode("utf-8")).hexdigest()
            next_level.append(combined)

        idx = idx // 2
        nodes = next_level

    return {"proof": proof, "root": nodes[0] if nodes else None}


def verify_merkle_proof(leaf_hash: str, proof: list, root_hash: str) -> bool:
    """
    Verifies Merkle inclusion proof against root hash.
    """
    current = leaf_hash
    for item in proof:
        sibling = item["hash"]
        pos = item["position"]
        if pos == "right":
            combined = current + sibling
        else:
            combined = sibling + current
        current = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return current.lower() == root_hash.lower()
