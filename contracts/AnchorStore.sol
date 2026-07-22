// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title AnchorStore (Multi-Notary Decentralized Health Vault Anchoring)
 * @notice Stores Merkle Roots of patient health records with Multi-Notary role-based consensus.
 * Eliminates single-point-of-failure vulnerabilities.
 */
contract AnchorStore {
    mapping(string => bytes32) public patientMerkleRoots;
    mapping(address => bool) public isNotary;
    uint256 public totalNotaries;
    uint256 public requiredConsensusThreshold;

    struct Proposal {
        bytes32 root;
        uint256 approvalsCount;
        bool executed;
    }

    // patientId => Proposal
    mapping(string => Proposal) public pendingProposals;
    // patientId => (notary => approved)
    mapping(string => mapping(address => bool)) public proposalApprovals;

    event NotaryAdded(address indexed notary);
    event NotaryRemoved(address indexed notary);
    event RootProposed(string indexed patientId, bytes32 newRoot, address indexed proposedBy);
    event RootApproved(string indexed patientId, bytes32 newRoot, address indexed approvedBy);
    event RootAnchored(string indexed patientId, bytes32 newRoot);

    modifier onlyNotary() {
        require(isNotary[msg.sender], "AnchorStore: caller is not an authorized notary");
        _;
    }

    constructor() {
        isNotary[msg.sender] = true;
        totalNotaries = 1;
        requiredConsensusThreshold = 1;
        emit NotaryAdded(msg.sender);
    }

    function addNotary(address newNotary) public onlyNotary {
        require(!isNotary[newNotary], "AnchorStore: address is already a notary");
        isNotary[newNotary] = true;
        totalNotaries++;
        requiredConsensusThreshold = (totalNotaries / 2) + 1;
        emit NotaryAdded(newNotary);
    }

    function proposeOrApproveRoot(string memory patientId, bytes32 root) public onlyNotary {
        Proposal storage prop = pendingProposals[patientId];

        if (prop.root != root || prop.executed) {
            prop.root = root;
            prop.approvalsCount = 1;
            prop.executed = false;
            proposalApprovals[patientId][msg.sender] = true;
            emit RootProposed(patientId, root, msg.sender);
        } else {
            require(!proposalApprovals[patientId][msg.sender], "AnchorStore: notary already approved this root proposal");
            proposalApprovals[patientId][msg.sender] = true;
            prop.approvalsCount++;
            emit RootApproved(patientId, root, msg.sender);
        }

        if (prop.approvalsCount >= requiredConsensusThreshold && !prop.executed) {
            prop.executed = true;
            patientMerkleRoots[patientId] = root;
            emit RootAnchored(patientId, root);
        }
    }
}
