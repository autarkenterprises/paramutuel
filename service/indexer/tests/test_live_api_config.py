import json
import tempfile
import unittest
from pathlib import Path

from service.indexer.live_api import (
    _factory_freeform_from_config,
    _factory_v2_from_config,
    _resolve_factory_freeform_address,
    _resolve_factory_v2_address,
)


class LiveApiFreeformConfigTests(unittest.TestCase):
    def test_factory_freeform_from_deployments_json_network_alias(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(
                {
                    "baseSepolia": {
                        "factoryFreeformAddress": "0xdddddddddddddddddddddddddddddddddddddddd",
                    }
                },
                f,
            )
            path = f.name
        try:
            addr = _factory_freeform_from_config(path, "base-sepolia")
            self.assertEqual(addr.lower(), "0xdddddddddddddddddddddddddddddddddddddddd")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_resolve_factory_freeform_explicit_overrides_config(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(
                {"baseSepolia": {"factoryFreeformAddress": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}},
                f,
            )
            path = f.name
        try:
            got = _resolve_factory_freeform_address(
                explicit="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                network="base-sepolia",
                config_path=path,
            )
            self.assertEqual(got.lower(), "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        finally:
            Path(path).unlink(missing_ok=True)


class LiveApiFactoryV2ConfigTests(unittest.TestCase):
    def test_factory_v2_from_deployments_json_network_alias(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(
                {
                    "baseSepolia": {
                        "factoryV2Address": "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                    }
                },
                f,
            )
            path = f.name
        try:
            addr = _factory_v2_from_config(path, "base-sepolia")
            self.assertEqual(addr.lower(), "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_resolve_factory_v2_explicit_overrides_config(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"baseSepolia": {"factoryV2Address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}, f)
            path = f.name
        try:
            got = _resolve_factory_v2_address(
                explicit="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                network="base-sepolia",
                config_path=path,
            )
            self.assertEqual(got.lower(), "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
