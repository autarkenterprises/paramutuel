// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";

import {ParamutuelFactoryV3} from "../src/ParamutuelFactoryV3.sol";
import {ParamutuelWagerV3} from "../src/ParamutuelWagerV3.sol";
import {MockERC20} from "./utils/MockTokens.sol";

/// @notice Random-walk driver for one wager. Foundry calls these actions in random order with random
///         inputs, so the invariants below are checked across lifecycles no hand-written test
///         enumerates. Ghost variables record what the handler moved, independently of the wager's
///         own accounting, so the invariants compare two separately derived sets of numbers.
contract WagerHandler is Test {
    ParamutuelWagerV3 public immutable wager;
    MockERC20 public immutable token;
    address public immutable resolverAddr;
    uint256 public immutable numOptions;
    bool public immutable freeform;
    uint64 public immutable closeAt;
    uint64 public immutable windowLength;

    address[] public actors;
    address[] public feeRecipients;
    string[] internal answers;

    uint256 public ghostDeposited;
    uint256 public ghostClaimedOut;
    uint256 public ghostFeesOut;
    /// @dev Number of stake legs. Rounding loses less than 1 wei per paid leg, which bounds the dust.
    uint256 public ghostLegs;

    constructor(
        ParamutuelWagerV3 wager_,
        MockERC20 token_,
        address resolver_,
        uint256 numOptions_,
        bool freeform_,
        uint64 closeAt_,
        uint64 windowLength_,
        address[] memory feeRecipients_
    ) {
        wager = wager_;
        token = token_;
        resolverAddr = resolver_;
        numOptions = numOptions_;
        freeform = freeform_;
        closeAt = closeAt_;
        windowLength = windowLength_;
        feeRecipients = feeRecipients_;
        for (uint160 i = 1; i <= 4; i++) {
            address a = address(i * 0x1000);
            actors.push(a);
            token.mint(a, type(uint96).max);
            vm.prank(a);
            token.approve(address(wager), type(uint256).max);
        }
        answers.push("alpha");
        answers.push(unicode"bêta");
        answers.push(" gamma ");
        answers.push("delta");
    }

    function _actor(uint256 seed) internal view returns (address) {
        return actors[seed % actors.length];
    }

    /// @dev Single-winner wagers only admit single-bit masks; other policies take any non-zero mask.
    function _validMask(uint256 seed) internal view returns (uint256) {
        if (wager.payoffPolicy() == ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER) {
            return uint256(1) << (seed % numOptions);
        }
        return (seed % ((uint256(1) << numOptions) - 1)) + 1;
    }

    function bet(uint256 actorSeed, uint256 ticketSeed, uint96 rawAmount) external {
        if (wager.state() != ParamutuelWagerV3.State.Open || block.timestamp >= closeAt) return;
        uint256 amount = bound(rawAmount, 1, 1e24);
        address actor = _actor(actorSeed);
        if (freeform) {
            vm.prank(actor);
            wager.placeBet(answers[ticketSeed % answers.length], amount);
        } else {
            // Compute the mask before pranking: `vm.prank` applies to the very next external call,
            // and `_validMask` makes one to read the policy.
            uint256 mask = _validMask(ticketSeed);
            vm.prank(actor);
            wager.placeBet(mask, amount);
        }
        ghostDeposited += amount;
        ghostLegs++;
    }

    function advanceTime(uint256 seconds_) external {
        vm.warp(block.timestamp + bound(seconds_, 0, 3 hours));
    }

    /// @dev Attempts every terminal transition. Whichever is currently legal may fire; reverts
    ///      (wrong window, no winning stake) are normal outcomes of the walk.
    function finalize(uint256 winSeed, uint256 pathSeed) external {
        if (wager.state() != ParamutuelWagerV3.State.Open) return;
        uint256 path = pathSeed % 3;
        if (path == 0) {
            if (freeform) {
                vm.prank(resolverAddr);
                try wager.resolve(answers[winSeed % answers.length]) {} catch {}
            } else {
                uint256 w = _validMask(winSeed);
                vm.prank(resolverAddr);
                try wager.resolve(w) {} catch {}
            }
        } else if (path == 1) {
            vm.prank(resolverAddr);
            try wager.retract() {} catch {}
        } else {
            try wager.expire() {} catch {}
        }
    }

    function claim(uint256 actorSeed) external {
        address actor = _actor(actorSeed);
        vm.prank(actor);
        try wager.claim() returns (uint256 paid) {
            ghostClaimedOut += paid;
        } catch {}
    }

    function withdrawFees(uint256 seed) external {
        if (feeRecipients.length == 0) return;
        address recipient = feeRecipients[seed % feeRecipients.length];
        vm.prank(recipient);
        try wager.withdrawFees() returns (uint256 amount) {
            ghostFeesOut += amount;
        } catch {}
    }

    /// @dev End-of-run settlement, used by the dust invariant.
    function claimEverything() external {
        for (uint256 i; i < actors.length; i++) {
            vm.prank(actors[i]);
            try wager.claim() returns (uint256 paid) {
                ghostClaimedOut += paid;
            } catch {}
        }
        for (uint256 i; i < feeRecipients.length; i++) {
            vm.prank(feeRecipients[i]);
            try wager.withdrawFees() returns (uint256 amount) {
                ghostFeesOut += amount;
            } catch {}
        }
    }
}

/// @notice The solvency properties ADR-0018 says the core guarantees for standard ERC-20 collateral.
///         One concrete suite per wager shape; `_shape()` selects the policy.
abstract contract WagerInvariants is Test {
    uint64 internal constant CLOSE = 3 hours;
    uint64 internal constant WINDOW = 1 hours;
    address internal constant RESOLVER = address(0xBEEF);
    address internal constant TREASURY = address(0xFEE);
    address internal constant BENEFICIARY = address(0xCAFE);

    ParamutuelWagerV3 internal wager;
    MockERC20 internal token;
    WagerHandler internal handler;

    function _create(ParamutuelFactoryV3 factory, address[] memory recipients, uint16[] memory bps)
        internal
        virtual
        returns (ParamutuelWagerV3 w, uint256 numOptions, bool freeform);

    function setUp() public {
        vm.warp(1000);
        ParamutuelFactoryV3 factory = new ParamutuelFactoryV3(TREASURY, 137, 0, 0);
        token = new MockERC20();
        address[] memory extra = new address[](1);
        uint16[] memory bps = new uint16[](1);
        extra[0] = BENEFICIARY;
        bps[0] = 251; // Distinct primes, so a wrong fee split cannot pass by accident.
        (ParamutuelWagerV3 w, uint256 numOptions, bool freeform) = _create(factory, extra, bps);
        wager = w;
        address[] memory allRecipients = new address[](2);
        allRecipients[0] = TREASURY;
        allRecipients[1] = BENEFICIARY;
        handler = new WagerHandler(wager, token, RESOLVER, numOptions, freeform, uint64(1000) + CLOSE, WINDOW, allRecipients);
        targetContract(address(handler));
        bytes4[] memory selectors = new bytes4[](5);
        selectors[0] = WagerHandler.bet.selector;
        selectors[1] = WagerHandler.advanceTime.selector;
        selectors[2] = WagerHandler.finalize.selector;
        selectors[3] = WagerHandler.claim.selector;
        selectors[4] = WagerHandler.withdrawFees.selector;
        targetSelector(FuzzSelector({addr: address(handler), selectors: selectors}));
    }

    /// @dev Custody exactly equals deposits minus everything paid out. Nothing appears or vanishes.
    function invariant_custodyConservation() public view {
        assertEq(
            token.balanceOf(address(wager)),
            handler.ghostDeposited() - handler.ghostClaimedOut() - handler.ghostFeesOut()
        );
    }

    /// @dev The wager's pot tracks exactly what was deposited, and is frozen once finalised.
    function invariant_potMatchesDeposits() public view {
        assertEq(wager.totalPot(), handler.ghostDeposited());
    }

    /// @dev Bettors are never paid more than the net pot, and fees never exceed their share. This is
    ///      the property that makes every recipient's claim payable.
    function invariant_payoutsNeverExceedEntitlement() public view {
        uint256 pot = wager.totalPot();
        uint256 fees = (pot * 388) / 10_000;
        assertLe(handler.ghostClaimedOut(), pot - fees, "claims exceed net pot");
        assertLe(handler.ghostFeesOut(), fees, "fee withdrawals exceed fee total");
    }

    /// @dev Once finalised, custody always covers unwithdrawn fees: paying bettors can never eat
    ///      into what fee recipients are owed.
    function invariant_custodyCoversAccruedFees() public view {
        if (wager.state() == ParamutuelWagerV3.State.Open) return;
        assertGe(token.balanceOf(address(wager)), wager.feeBalances(TREASURY) + wager.feeBalances(BENEFICIARY));
    }

    /// @dev After everyone settles, what remains is rounding dust only (less than 1 wei per leg),
    ///      plus unclaimable losing stake only when no ticket can claim it. Enumerated wagers can
    ///      resolve with winners only, so the residue on a finalised wager is bounded by legs.
    function invariant_settlementLeavesOnlyDust() public {
        if (wager.state() == ParamutuelWagerV3.State.Open) return;
        uint256 snapshot = vm.snapshotState();
        handler.claimEverything();
        uint256 residue = token.balanceOf(address(wager));
        assertLe(residue, handler.ghostLegs() + 2, "more than rounding dust left behind");
        vm.revertToState(snapshot);
    }
}

/// forge-config: default.invariant.runs = 48
/// forge-config: default.invariant.depth = 40
/// forge-config: default.invariant.fail-on-revert = true
contract InvariantSingleWinner is WagerInvariants {
    function _create(ParamutuelFactoryV3 f, address[] memory r, uint16[] memory b)
        internal
        override
        returns (ParamutuelWagerV3, uint256, bool)
    {
        string[] memory o = new string[](4);
        o[0] = "a";
        o[1] = "b";
        o[2] = "c";
        o[3] = "d";
        return (
            ParamutuelWagerV3(
                f.createEnumeratedWager(
                    address(token), "Q", o, ParamutuelWagerV3.PayoffPolicy.SINGLE_WINNER, 0, uint64(1000) + CLOSE, WINDOW, RESOLVER, address(0), address(0), r, b
                )
            ),
            4,
            false
        );
    }
}

/// forge-config: default.invariant.runs = 48
/// forge-config: default.invariant.depth = 40
/// forge-config: default.invariant.fail-on-revert = true
contract InvariantAnyOf is WagerInvariants {
    function _create(ParamutuelFactoryV3 f, address[] memory r, uint16[] memory b)
        internal
        override
        returns (ParamutuelWagerV3, uint256, bool)
    {
        string[] memory o = new string[](4);
        o[0] = "a";
        o[1] = "b";
        o[2] = "c";
        o[3] = "d";
        return (
            ParamutuelWagerV3(
                f.createEnumeratedWager(
                    address(token), "Q", o, ParamutuelWagerV3.PayoffPolicy.ANY_OF, 0, uint64(1000) + CLOSE, WINDOW, RESOLVER, address(0), address(0), r, b
                )
            ),
            4,
            false
        );
    }
}

/// forge-config: default.invariant.runs = 48
/// forge-config: default.invariant.depth = 40
/// forge-config: default.invariant.fail-on-revert = true
contract InvariantExactSet is WagerInvariants {
    function _create(ParamutuelFactoryV3 f, address[] memory r, uint16[] memory b)
        internal
        override
        returns (ParamutuelWagerV3, uint256, bool)
    {
        string[] memory o = new string[](3);
        o[0] = "a";
        o[1] = "b";
        o[2] = "c";
        return (
            ParamutuelWagerV3(
                f.createEnumeratedWager(
                    address(token), "Q", o, ParamutuelWagerV3.PayoffPolicy.EXACT_SET, 0, uint64(1000) + CLOSE, WINDOW, RESOLVER, address(0), address(0), r, b
                )
            ),
            3,
            false
        );
    }
}

/// forge-config: default.invariant.runs = 48
/// forge-config: default.invariant.depth = 40
/// forge-config: default.invariant.fail-on-revert = true
contract InvariantAtLeastK is WagerInvariants {
    function _create(ParamutuelFactoryV3 f, address[] memory r, uint16[] memory b)
        internal
        override
        returns (ParamutuelWagerV3, uint256, bool)
    {
        string[] memory o = new string[](5);
        o[0] = "a";
        o[1] = "b";
        o[2] = "c";
        o[3] = "d";
        o[4] = "e";
        return (
            ParamutuelWagerV3(
                f.createEnumeratedWager(
                    address(token), "Q", o, ParamutuelWagerV3.PayoffPolicy.AT_LEAST_K, 2, uint64(1000) + CLOSE, WINDOW, RESOLVER, address(0), address(0), r, b
                )
            ),
            5,
            false
        );
    }
}

/// forge-config: default.invariant.runs = 48
/// forge-config: default.invariant.depth = 40
/// forge-config: default.invariant.fail-on-revert = true
contract InvariantWeightedOverlap is WagerInvariants {
    function _create(ParamutuelFactoryV3 f, address[] memory r, uint16[] memory b)
        internal
        override
        returns (ParamutuelWagerV3, uint256, bool)
    {
        string[] memory o = new string[](5);
        o[0] = "a";
        o[1] = "b";
        o[2] = "c";
        o[3] = "d";
        o[4] = "e";
        return (
            ParamutuelWagerV3(
                f.createEnumeratedWager(
                    address(token), "Q", o, ParamutuelWagerV3.PayoffPolicy.WEIGHTED_OVERLAP, 0, uint64(1000) + CLOSE, WINDOW, RESOLVER, address(0), address(0), r, b
                )
            ),
            5,
            false
        );
    }
}

/// forge-config: default.invariant.runs = 48
/// forge-config: default.invariant.depth = 40
/// forge-config: default.invariant.fail-on-revert = true
contract InvariantFreeform is WagerInvariants {
    function _create(ParamutuelFactoryV3 f, address[] memory r, uint16[] memory b)
        internal
        override
        returns (ParamutuelWagerV3, uint256, bool)
    {
        return (
            ParamutuelWagerV3(
                f.createFreeformWager(address(token), "Q", uint64(1000) + CLOSE, WINDOW, RESOLVER, address(0), address(0), r, b)
            ),
            0,
            true
        );
    }
}
