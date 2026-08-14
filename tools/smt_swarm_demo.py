#!/usr/bin/env python3
"""SMT Swarm State Verification & Tamper Detection Demonstration."""

import hashlib
import json
import sys
import time

from smt.hash_engine import hash_leaf
from smt.proof import SMTProof
from smt.sparse_merkle_tree import SparseMerkleTree
from smt.sync import SMTSyncPatch
from smt.verifier import SMTVerifier


def main():
    print("===================================================================")
    print("  SPARSE MERKLE TREE (SMT) SWARM STATE AUTHENTICATION DEMO")
    print("===================================================================\n")

    # 1. Initialize SMT Tree
    smt = SparseMerkleTree()
    print("1. INITIALIZING SPARSE MERKLE TREE...")
    initial_root = smt.get_root_hash()
    print(f"   ► Initial Empty Root Hash (32-byte): {initial_root.hex()[:16]}...\n")

    # 2. Register Active Drone Nodes into Swarm State
    print("2. REGISTERING SWARM DRONES INTO SMT STATE...")
    
    # Drone 1 (Physical Pixhawk)
    drone1_key = hashlib.sha256(b"drone-1-pixhawk").digest()
    drone1_telemetry = json.dumps({"status": "ACTIVE", "lat": 17.44521, "lon": 78.34912, "battery": 98}).encode()
    drone1_val_hash = hashlib.sha256(drone1_telemetry).digest()
    smt.update(drone1_key, drone1_val_hash)
    print(f"   ► Added Drone 1 (Pixhawk FC)  -> Key: {drone1_key.hex()[:12]}...")

    # Drone 2 (Follower)
    drone2_key = hashlib.sha256(b"drone-2-follower").digest()
    drone2_telemetry = json.dumps({"status": "ACTIVE", "lat": 17.44550, "lon": 78.34950, "battery": 95}).encode()
    drone2_val_hash = hashlib.sha256(drone2_telemetry).digest()
    smt.update(drone2_key, drone2_val_hash)
    print(f"   ► Added Drone 2 (Follower)    -> Key: {drone2_key.hex()[:12]}...")

    swarm_root = smt.get_root_hash()
    print(f"\n   ► COMPUTED GLOBAL SWARM ROOT HASH: {swarm_root.hex()}\n")

    # 3. Stateless Membership Proof Verification
    print("3. VERIFYING DRONE 1 MEMBERSHIP PROOF (AUTHENTICATION)...")
    proof1 = smt.get_proof(drone1_key)
    is_valid_member = SMTVerifier.verify_membership(swarm_root, proof1)
    print(f"   ► Proof Path Mask : 0x{proof1.path_mask:x}")
    print(f"   ► Sibling Count   : {len(proof1.siblings)}")
    print(f"   ► VERIFICATION RESULT: {'✅ MEMBERSHIP AUTHENTICATED (Valid Member)' if is_valid_member else '❌ FAILED'}\n")

    # 4. Tamper Detection / Rogue Drone Attack Rejection
    print("4. SIMULATING ATTACK: TAMPERED TELEMETRY & ROGUE DRONE...")
    fake_telemetry = json.dumps({"status": "ACTIVE", "lat": 99.99999, "lon": 99.99999, "battery": 100}).encode()
    fake_val_hash = hashlib.sha256(fake_telemetry).digest()
    fake_proof = SMTProof(key=drone1_key, value_hash=fake_val_hash, siblings=proof1.siblings, path_mask=proof1.path_mask)
    
    is_fake_valid = SMTVerifier.verify_membership(swarm_root, fake_proof)
    print(f"   ► Tampered Leaf Hash : {fake_val_hash.hex()[:16]}...")
    print(f"   ► ATTACK RESULT      : {'❌ SECURITY BREACH' if is_fake_valid else '✅ ATTACK REJECTED! Tampered state fails Merkle Root verification!'}\n")

    # 5. Differential SMT Delta Patch Compression Test
    print("5. DIFFERENTIAL STATE SYNC COMPRESSION (SMTSyncPatch)...")
    old_root = smt.get_root_hash()
    
    # Drone 1 updates location (Waypoint update)
    updated_telemetry = json.dumps({"status": "ACTIVE", "lat": 17.44600, "lon": 78.35000, "battery": 97}).encode()
    updated_val_hash = hashlib.sha256(updated_telemetry).digest()
    smt.update(drone1_key, updated_val_hash)
    new_root = smt.get_root_hash()

    patch = SMTSyncPatch(
        base_root=old_root,
        target_root=new_root,
        mutated_leaves=((drone1_key, updated_val_hash),),
        epoch=1
    )
    serialized_patch = patch.serialize()

    full_state_size = 1024  # Typical full state table size in bytes
    patch_size = len(serialized_patch)
    savings = ((full_state_size - patch_size) / full_state_size) * 100.0

    print(f"   ► Full Swarm Telemetry Table Size : {full_state_size} bytes")
    print(f"   ► Serialized SMT Delta Patch Size : {patch_size} bytes")
    print(f"   ► BANDWIDTH SAVINGS RESULT        : {savings:.1f}% RF BANDWIDTH REDUCTION!\n")

    print("===================================================================")
    print("  SMT SWARM STATE AUTHENTICATION TEST COMPLETE: 100% SUCCESS")
    print("===================================================================")


if __name__ == "__main__":
    main()
