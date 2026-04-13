#!/usr/bin/env python3
import argparse
import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from .api import Handler
from .indexer import db_connect, get_meta_int, init_db, normalize_address, sync_logs

NETWORK_KEY_MAP = {
    "base-sepolia": "baseSepolia",
    "base-sepolia-testnet": "baseSepolia",
    "base-mainnet": "baseMainnet",
    "base": "baseMainnet",
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _resolve_int_env(name: str, default: int) -> int:
    value = _env(name)
    if not value:
        return default
    return int(value)


def _resolve_optional_int_env(name: str) -> int | None:
    value = _env(name)
    if not value:
        return None
    return int(value)


def _indexer_from_block_from_config(config_path: str, network: str) -> int | None:
    path = Path(config_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    key = NETWORK_KEY_MAP.get(network, network)
    raw = (data.get(key) or {}).get("indexerFromBlock")
    if raw is None or raw == "":
        return None
    return int(raw)


def _factory_from_config(config_path: str, network: str) -> str:
    path = Path(config_path)
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    key = NETWORK_KEY_MAP.get(network, network)
    return str((data.get(key) or {}).get("factoryAddress") or "").strip()


def _factory_freeform_from_config(config_path: str, network: str) -> str:
    path = Path(config_path)
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    key = NETWORK_KEY_MAP.get(network, network)
    return str((data.get(key) or {}).get("factoryFreeformAddress") or "").strip()


def _factory_v2_from_config(config_path: str, network: str) -> str:
    path = Path(config_path)
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    key = NETWORK_KEY_MAP.get(network, network)
    return str((data.get(key) or {}).get("factoryV2Address") or "").strip()


def _factory_v3_from_config(config_path: str, network: str) -> str:
    path = Path(config_path)
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    key = NETWORK_KEY_MAP.get(network, network)
    return str((data.get(key) or {}).get("factoryV3Address") or "").strip()


def _resolve_factory_address(explicit: str, network: str, config_path: str) -> str:
    if explicit:
        return normalize_address(explicit)

    from_env = _env("FACTORY_ADDRESS")
    if from_env:
        return normalize_address(from_env)

    from_config = _factory_from_config(config_path, network)
    if from_config:
        return normalize_address(from_config)

    return ""


def _resolve_factory_v3_address(explicit: str, network: str, config_path: str) -> str:
    if explicit:
        return normalize_address(explicit)
    from_env = _env("FACTORY_V3_ADDRESS")
    if from_env:
        return normalize_address(from_env)
    from_config = _factory_v3_from_config(config_path, network)
    if from_config:
        return normalize_address(from_config)
    return ""


def _resolve_factory_freeform_address(explicit: str, network: str, config_path: str) -> str:
    if explicit:
        return normalize_address(explicit)
    from_env = _env("FACTORY_FREEFORM_ADDRESS")
    if from_env:
        return normalize_address(from_env)
    from_config = _factory_freeform_from_config(config_path, network)
    if from_config:
        return normalize_address(from_config)
    return ""


def _resolve_factory_v2_address(explicit: str, network: str, config_path: str) -> str:
    if explicit:
        return normalize_address(explicit)
    from_env = _env("FACTORY_V2_ADDRESS")
    if from_env:
        return normalize_address(from_env)
    from_config = _factory_v2_from_config(config_path, network)
    if from_config:
        return normalize_address(from_config)
    return ""


def _resolve_rpc_url(explicit: str) -> str:
    if explicit:
        return explicit
    rpc = _env("RPC_URL_BASE_SEPOLIA") or _env("RPC_URL_SEPOLIA") or _env("RPC_URL")
    if not rpc:
        raise RuntimeError("RPC URL is required (arg, RPC_URL_BASE_SEPOLIA, RPC_URL_SEPOLIA, or RPC_URL)")
    return rpc


def _sync_loop(
    stop_event: threading.Event,
    rpc_url: str,
    conn,
    factory_address: str,
    factory_v2_address: str,
    factory_freeform_address: str,
    factory_v3_address: str,
    poll_interval_seconds: int,
    chunk_size: int,
    initial_from_block: int,
) -> None:
    while not stop_event.is_set():
        try:
            last = get_meta_int(conn, "last_indexed_block")
            effective_from: int | None = None if last is not None else initial_from_block
            processed = sync_logs(
                rpc_url=rpc_url,
                conn=conn,
                factory_address=factory_address,
                from_block=effective_from,
                to_block=None,
                chunk_size=chunk_size,
                factory_v2_address=factory_v2_address,
                factory_freeform_address=factory_freeform_address,
                factory_v3_address=factory_v3_address,
            )
            if processed:
                print(f"[indexer-sync] processed logs: {processed}")
        except Exception as exc:
            print(f"[indexer-sync] error: {exc}")

        stop_event.wait(max(1, poll_interval_seconds))


def main() -> None:
    parser = argparse.ArgumentParser(description="Live indexer API (sync loop + HTTP API in one process)")
    parser.add_argument("--db-path", default=_env("INDEXER_DB_PATH", "service/indexer/indexer.db"))
    parser.add_argument("--rpc-url", default=_env("RPC_URL_BASE_SEPOLIA") or _env("RPC_URL_SEPOLIA") or _env("RPC_URL"))
    parser.add_argument("--factory-address", default=_env("FACTORY_ADDRESS"))
    parser.add_argument("--factory-v2-address", default=_env("FACTORY_V2_ADDRESS"))
    parser.add_argument("--factory-freeform-address", default=_env("FACTORY_FREEFORM_ADDRESS"))
    parser.add_argument("--factory-v3-address", default=_env("FACTORY_V3_ADDRESS"))
    parser.add_argument("--network", default=_env("INDEXER_NETWORK", "base-sepolia"))
    parser.add_argument("--deployments-config-path", default=_env("DEPLOYMENTS_CONFIG_PATH", "config/deployments.json"))
    parser.add_argument("--host", default=_env("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=_resolve_int_env("PORT", 8090))
    parser.add_argument("--poll-interval-seconds", type=int, default=_resolve_int_env("INDEXER_POLL_INTERVAL_SECONDS", 15))
    parser.add_argument("--chunk-size", type=int, default=_resolve_int_env("INDEXER_CHUNK_SIZE", 2_000))
    parser.add_argument("--from-block", type=int, default=_resolve_optional_int_env("INDEXER_FROM_BLOCK"))
    args = parser.parse_args()

    rpc_url = _resolve_rpc_url(args.rpc_url)
    factory_address = _resolve_factory_address(
        explicit=args.factory_address,
        network=args.network,
        config_path=args.deployments_config_path,
    )
    factory_v2_address = _resolve_factory_v2_address(
        explicit=args.factory_v2_address,
        network=args.network,
        config_path=args.deployments_config_path,
    )
    factory_freeform_address = _resolve_factory_freeform_address(
        explicit=args.factory_freeform_address,
        network=args.network,
        config_path=args.deployments_config_path,
    )
    factory_v3_address = _resolve_factory_v3_address(
        explicit=args.factory_v3_address,
        network=args.network,
        config_path=args.deployments_config_path,
    )
    if not (factory_address or factory_v2_address or factory_freeform_address or factory_v3_address):
        raise RuntimeError(
            "At least one factory address is required: v1 (FACTORY_ADDRESS / factoryAddress), "
            "v2 (FACTORY_V2_ADDRESS / factoryV2Address), freeform (FACTORY_FREEFORM_ADDRESS / "
            "factoryFreeformAddress), or v3 (FACTORY_V3_ADDRESS / factoryV3Address)"
        )

    initial_from_block = args.from_block
    if initial_from_block is None:
        initial_from_block = _indexer_from_block_from_config(
            args.deployments_config_path, args.network
        )
    if initial_from_block is None:
        raise RuntimeError(
            "Initial indexer from-block is required: set env INDEXER_FROM_BLOCK or add "
            f"indexerFromBlock to the network entry in {args.deployments_config_path}"
        )

    api_conn = db_connect(args.db_path)
    sync_conn = db_connect(args.db_path)
    init_db(api_conn)
    init_db(sync_conn)
    Handler.conn = api_conn
    Handler.indexer_factory_address = factory_address or None
    Handler.indexer_factory_v2_address = factory_v2_address or None
    Handler.indexer_factory_freeform_address = factory_freeform_address or None
    Handler.indexer_factory_v3_address = factory_v3_address or None

    stop_event = threading.Event()
    sync_thread = threading.Thread(
        target=_sync_loop,
        args=(
            stop_event,
            rpc_url,
            sync_conn,
            factory_address,
            factory_v2_address,
            factory_freeform_address,
            factory_v3_address,
            args.poll_interval_seconds,
            args.chunk_size,
            initial_from_block,
        ),
        daemon=True,
    )
    sync_thread.start()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Indexer live API listening on http://{args.host}:{args.port}")
    if factory_address:
        print(f"Factory (v1): {factory_address}")
    if factory_v2_address:
        print(f"Factory (v2): {factory_v2_address}")
    if factory_freeform_address:
        print(f"Factory (freeform): {factory_freeform_address}")
    if factory_v3_address:
        print(f"Factory (v3): {factory_v3_address}")
    print(f"Poll interval: {args.poll_interval_seconds}s")
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        sync_thread.join(timeout=5)
        api_conn.close()
        sync_conn.close()


if __name__ == "__main__":
    main()
