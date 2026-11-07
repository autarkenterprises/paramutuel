// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Local reentrancy guard for Paramutuel V3
/// @notice Vendoring this tiny primitive instead of importing OpenZeppelin keeps `src/`
///         free of any external dependency at compile time — the wager and factory then
///         compile against nothing but the interfaces in `src/interfaces/` and `src/utils/`.
///         This matches the project posture that the deployable contract surface in `src/` is
///         self-contained and audit-scoped.
/// @dev Storage layout: `_status` is the only slot. Sentinel values 1/2 (rather than
///      0/1) avoid the 20k-gas zero-to-non-zero SSTORE on each guarded call, because the
///      slot is already non-zero from deployment.
abstract contract ReentrancyGuard {
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;

    uint256 private _status = _NOT_ENTERED;

    /// @dev Standard checks-effects-interactions companion: any function that performs
    ///      an external token call after touching wager state must wear `nonReentrant`
    ///      so a malicious collateral token cannot re-enter mid-update. The single
    ///      guard slot is intentionally shared across all guarded entry points.
    modifier nonReentrant() {
        require(_status != _ENTERED, "REENTRANCY");
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }
}

