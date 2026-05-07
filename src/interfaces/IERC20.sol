// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Minimal ERC-20 interface used by Paramutuel V3
/// @notice Deliberately scoped to the four methods the wager and factory actually call —
///         `transfer`, `transferFrom`, `balanceOf`, `allowance`. The wager never mints,
///         burns, approves, or reads metadata, so the full ERC-20 surface is unnecessary
///         and would only widen the attack surface and bytecode size.
/// @dev V3 only uses the boolean return form (no SafeERC20-style return-data probing).
///      Collateral tokens that revert on failure or that follow the boolean convention
///      both work; tokens that return nothing on success do NOT — this is documented as
///      a deployment-time prerequisite (see `docs/ADR-0010-IMPLEMENTATION.md`).
interface IERC20 {
    function transfer(address to, uint256 value) external returns (bool);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function allowance(address owner, address spender) external view returns (uint256);
}

