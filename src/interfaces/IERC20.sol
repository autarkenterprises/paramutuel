// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Minimal ERC-20 interface used by Paramutuel V3
/// @notice Deliberately scoped to the two methods the wager and factory actually call:
///         `transfer` and `transferFrom`. The wager never mints, burns, approves, or reads
///         metadata, so a wider interface would only suggest behaviour that does not exist.
/// @dev V3 only uses the boolean return form (no SafeERC20-style return-data probing).
///      Collateral tokens that revert on failure or that follow the boolean convention
///      both work. Tokens that return nothing on success fail safe: the decode reverts, so no
///      bet can be placed. Fee-on-transfer and rebasing tokens fail UNSAFE and are outside the
///      core's solvency guarantee (ADR-0018; pinned in `test/ParamutuelV3Hardening.t.sol`).
interface IERC20 {
    function transfer(address to, uint256 value) external returns (bool);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
}

