"""ADR-0020: the stdlib ABI encoder must agree with an independent implementation.

`cast` cannot be trusted with arbitrary strings: it strips trailing whitespace and surrounding quotes
and parses a leading `--` as a flag. So anything user-supplied is encoded here and passed to
`cast send` as raw calldata. eth_abi and eth_hash (the MCP server's dependencies, always present in
the fast suite) serve as the independent oracle.
"""
import unittest

from eth_abi import encode as oracle_encode
from eth_hash.auto import keccak

from service.control_panel import abi

ADDR_A = "0x1111111111111111111111111111111111111111"
ADDR_B = "0x2222222222222222222222222222222222222222"
ZERO = "0x" + "00" * 20

# Every string shape that `cast` mangles, plus awkward UTF-8.
NASTY = [
    "plain",
    " padded ",
    "trailing ",
    '"quoted"',
    "'single'",
    "--help",
    "--rpc-url=http://evil",
    "-5",
    "0xdeadbeef",
    "café ☕",
    "a,b",
    "[x]",
    'back\\slash"mix',
    "line\nbreak\n",
    "\t",
]


class SelectorTests(unittest.TestCase):
    def test_every_known_signature_has_the_true_selector(self):
        self.assertGreater(len(abi.SELECTORS), 8)
        for signature, selector in abi.SELECTORS.items():
            with self.subTest(signature=signature):
                self.assertEqual(selector, "0x" + keccak(signature.encode())[:4].hex())

    def test_unknown_signature_is_rejected(self):
        with self.assertRaises(KeyError):
            abi.encode_call("drain()", [], [])


class EncodingTests(unittest.TestCase):
    def _agrees(self, types, values):
        self.assertEqual(abi.encode(types, values), oracle_encode(types, values))

    def test_scalars(self):
        self._agrees(["uint256"], [0])
        self._agrees(["uint256"], [2**256 - 1])
        self._agrees(["uint8", "uint64", "uint16"], [4, 2**64 - 1, 65535])
        self._agrees(["address"], [ADDR_A])

    def test_every_nasty_string_alone(self):
        for s in NASTY:
            with self.subTest(s=s):
                self._agrees(["string"], [s])

    def test_empty_string_and_empty_arrays(self):
        self._agrees(["string"], [""])
        self._agrees(["string[]"], [[]])
        self._agrees(["uint256[]"], [[]])
        self._agrees(["address[]"], [[]])

    def test_string_arrays_hold_every_nasty_string(self):
        self._agrees(["string[]"], [NASTY])

    def test_string_lengths_around_word_boundaries(self):
        for n in (31, 32, 33, 64, 65, 1024):
            with self.subTest(n=n):
                self._agrees(["string"], ["x" * n])

    def test_full_create_enumerated_argument_list(self):
        types = ["address", "string", "string[]", "uint8", "uint256", "uint64", "uint64", "address", "address",
                 "address", "address[]", "uint16[]", "uint256[]", "uint256[]", "uint256"]
        values = [ADDR_A, ' "Will it?" ', NASTY, 3, 2, 2**40, 7200, ZERO, ADDR_B, ADDR_B, [ADDR_A, ADDR_B], [100, 250],
                  [1, 2**254], [10**30, 1], 5_000_000]
        self._agrees(types, values)

    def test_encode_call_prefixes_selector(self):
        data = abi.encode_call("resolve(string)", ["string"], [" Paris "])
        self.assertEqual(data, "0x" + (keccak(b"resolve(string)")[:4] + oracle_encode(["string"], [" Paris "])).hex())

    def test_no_argument_call_is_the_bare_selector(self):
        self.assertEqual(abi.encode_call("retract()", [], []), "0x" + keccak(b"retract()")[:4].hex())


class RejectionTests(unittest.TestCase):
    """Invalid values must fail here, with a clear message, before any key or RPC is involved."""

    def test_bad_addresses(self):
        for bad in ("0x123", "not-an-address", "0x" + "g" * 40, "", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                abi.encode(["address"], [bad])

    def test_out_of_range_integers(self):
        for types, value in ((["uint8"], 256), (["uint16"], 65536), (["uint64"], 2**64), (["uint256"], 2**256), (["uint256"], -1)):
            with self.subTest(types=types, value=value), self.assertRaises(ValueError):
                abi.encode(types, [value])

    def test_bool_and_float_are_not_integers(self):
        for bad in (True, 1.5, "7"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                abi.encode(["uint256"], [bad])

    def test_strings_must_be_strings(self):
        with self.assertRaises(ValueError):
            abi.encode(["string"], [5])

    def test_unsupported_type_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            abi.encode(["bytes32"], [b"x"])


class EncoderMisuseTests(unittest.TestCase):
    def test_array_type_needs_a_list(self):
        with self.assertRaisesRegex(ValueError, "must be a list"):
            abi.encode(["uint256[]"], [5])

    def test_types_and_values_must_align(self):
        with self.assertRaisesRegex(ValueError, "length mismatch"):
            abi.encode(["uint256", "uint256"], [1])


if __name__ == "__main__":
    unittest.main()
