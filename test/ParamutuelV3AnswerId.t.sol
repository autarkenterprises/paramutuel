// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

/// @notice Document cryptographic / namespace properties of v3 freeform `answerId`.
contract ParamutuelV3AnswerIdTest is Test {
    bytes1 internal constant DOMAIN = bytes1(0x03);

    function _answerId(string memory s) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(DOMAIN, bytes(s)));
    }

    /// @dev v3 ids are never equal to legacy ADR-0009 `keccak256(bytes(answer))` for the same string.
    function test_v3_answerId_ne_legacy_freeform_hash() public pure {
        string memory s = "Paris";
        bytes32 legacy = keccak256(bytes(s));
        bytes32 v3 = _answerId(s);
        assertTrue(legacy != v3, "domain separation must change the digest");
    }

    /// @dev Cross-language anchor: keccak256(abi.encodePacked(0x03, bytes("Paris"))).
    function test_v3_answerId_paris_matches_offchain_vectors() public pure {
        bytes32 expected = bytes32(
            uint256(0x1912e91243cbc3b42ab17ada47d57ab68ed946bc24de33ae4f6c13bdad067953)
        );
        assertEq(_answerId("Paris"), expected);
    }

    function test_v3_distinct_utf8_strings_distinct_ids() public pure {
        assertTrue(_answerId("a") != _answerId("b"));
        assertTrue(_answerId("yes") != _answerId("Yes"));
    }

    /// @dev Empty string is still a well-defined id (not recommended for UX, but deterministic).
    function test_v3_empty_string_deterministic() public pure {
        assertEq(_answerId(""), keccak256(abi.encodePacked(DOMAIN)));
    }

    /// @dev Collision resistance is that of Keccak-256 on the encoded preimage; different preimages should not collide.
    function testFuzz_v3_answerId_injective_on_bounded_length(bytes memory payload) public {
        vm.assume(payload.length <= 256);
        bytes32 id = keccak256(abi.encodePacked(DOMAIN, payload));
        // Flipping any bit in the preimage should change the digest with overwhelming probability;
        // we check a simple neighbor if non-empty.
        if (payload.length == 0) return;
        bytes memory flipped = payload;
        flipped[0] ^= bytes1(0x01);
        bytes32 id2 = keccak256(abi.encodePacked(DOMAIN, flipped));
        assertTrue(id != id2, "single-bit flip should not collide at 256-bit output");
    }
}
