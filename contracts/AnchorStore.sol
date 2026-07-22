// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract AnchorStore {
    mapping(string => bytes32) public patientMerkleRoots;
    address public owner;

    event RootUpdated(string indexed patientId, bytes32 newRoot);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can update root");
        _;
    }

    function updateRoot(string memory patientId, bytes32 root) public onlyOwner {
        patientMerkleRoots[patientId] = root;
        emit RootUpdated(patientId, root);
    }
}
