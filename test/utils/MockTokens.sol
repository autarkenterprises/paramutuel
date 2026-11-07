// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Collateral test doubles for the V3 suites (ADR-0020, ADR-0018)
/// @notice Each class of token the protocol's "standard ERC-20" boundary cares about gets one
///         small mock. They live outside the `*.t.sol` files so the local end-to-end test
///         (`test/integration/`) can deploy the same bytecode from `out/`.

/// @dev Plain, well-behaved ERC-20: reverts on insufficient balance or allowance, returns true.
contract MockERC20 {
    /// @dev Real tokens report this, and the bet page will not stake until it can read it.
    uint8 public constant decimals = 18;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

/// @dev USDT-shaped token: moves balances but returns no data. The wager's `bool ok = ...`
///      decode reverts on the empty return, so this class fails SAFE (ADR-0018).
contract NoReturnToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external {
        allowance[msg.sender][spender] = amount;
    }

    function transfer(address to, uint256 amount) external {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
    }

    function transferFrom(address from, address to, uint256 amount) external {
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
    }
}

/// @dev Fee-on-transfer token: skims 1% of every transfer. The wager credits the requested
///      amount while custody receives less, so this class fails UNSAFE: the last claimant
///      cannot be paid. Pinned by test rather than defended in the core (ADR-0018).
contract FeeOnTransferToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function _move(address from, address to, uint256 amount) private {
        uint256 skim = amount / 100;
        balanceOf[from] -= amount;
        balanceOf[to] += amount - skim;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _move(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        allowance[from][msg.sender] -= amount;
        _move(from, to, amount);
        return true;
    }
}
