// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Minimal ERC-20 interface used by Paramutuel V3
/// @notice Deliberately scoped to the three methods the wager and factory actually call:
///         `transfer`, `transferFrom`, and `balanceOf`, which checks that a pull delivered what it
///         was asked to (ADR-0023). The wager never mints, burns, approves, or reads metadata, so
///         a wider interface would only suggest behaviour that does not exist.
/// @dev V3 only uses the boolean return form (no SafeERC20-style return-data probing).
///      Collateral tokens that revert on failure or that follow the boolean convention
///      both work. Tokens that return nothing on success fail safe: the decode reverts, so no
///      bet can be placed. Fee-on-transfer tokens also fail safe since ADR-0023: a pull that
///      delivers less than requested reverts `CollateralShortfall()`. Rebasing tokens remain
///      outside the core's solvency guarantee, because their balances change after the bet
///      (ADR-0018; all pinned in `test/ParamutuelV3Hardening.t.sol`).
interface IERC20 {
    function transfer(address to, uint256 value) external returns (bool);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

