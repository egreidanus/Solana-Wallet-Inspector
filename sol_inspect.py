"""Solana Wallet Inspector (CLI)

Usage examples:
  python sol_inspect.py <WALLET_ADDRESS>
  python sol_inspect.py <WALLET_ADDRESS> --limit 20 --commitment finalized
  python sol_inspect.py <WALLET_ADDRESS> --rpc https://api.mainnet-beta.solana.com --rpc https://solana.drpc.org
  python sol_inspect.py <WALLET_ADDRESS> --json
  python sol_inspect.py <WALLET_ADDRESS> --no-tokens --no-txs
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional

import requests

TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
DEFAULT_ENDPOINTS = [
    "https://api.mainnet-beta.solana.com",
    "https://solana.drpc.org",
]
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class RPCError(Exception):
    pass


def base58_decode(value: str) -> bytes:
    if not value:
        raise ValueError("empty base58 string")

    num = 0
    for ch in value:
        idx = BASE58_ALPHABET.find(ch)
        if idx == -1:
            raise ValueError(f"invalid base58 character: {ch}")
        num = num * 58 + idx

    combined = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    pad = len(value) - len(value.lstrip("1"))
    return b"\x00" * pad + combined


def validate_address(address: str) -> None:
    try:
        decoded = base58_decode(address)
    except ValueError as exc:
        raise ValueError(f"Invalid address: {exc}") from exc
    if len(decoded) != 32:
        raise ValueError(
            f"Invalid address length: decoded to {len(decoded)} bytes, expected 32"
        )


def lamports_to_sol(lamports: int) -> float:
    return lamports / 1_000_000_000


def format_sol(sol: float) -> str:
    text = f"{sol:.9f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _iso_time_from_blocktime(block_time: Optional[int]) -> str:
    if block_time is None:
        return "N/A"
    return datetime.fromtimestamp(block_time, tz=timezone.utc).isoformat()


def _err_summary(err: Any) -> str:
    if err is None:
        return ""
    try:
        return json.dumps(err, separators=(",", ":"))
    except TypeError:
        return str(err)


def parse_token_accounts(value: Iterable[dict[str, Any]]) -> List[dict[str, Any]]:
    tokens: List[dict[str, Any]] = []
    for item in value:
        pubkey = item.get("pubkey")
        parsed = (
            item.get("account", {})
            .get("data", {})
            .get("parsed", {})
            .get("info", {})
        )
        mint = parsed.get("mint")
        token_amount = parsed.get("tokenAmount", {})
        amount_raw = token_amount.get("amount")
        decimals = token_amount.get("decimals")
        ui_amount_str = token_amount.get("uiAmountString")
        ui_amount = (
            ui_amount_str
            if ui_amount_str is not None
            else str(token_amount.get("uiAmount"))
        )

        if not (pubkey and mint and amount_raw is not None and decimals is not None):
            continue

        tokens.append(
            {
                "mint": mint,
                "token_account": pubkey,
                "amount_raw": str(amount_raw),
                "decimals": int(decimals),
                "ui_amount": ui_amount,
            }
        )
    return tokens


@dataclass
class RPCClient:
    endpoints: List[str]
    timeout: float

    def request(self, method: str, params: list[Any]) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        backoffs = [0.5, 1.0, 2.0]

        last_error: Optional[Exception] = None
        for endpoint in self.endpoints:
            for attempt in range(len(backoffs) + 1):
                try:
                    response = requests.post(
                        endpoint, json=payload, timeout=self.timeout
                    )
                    if response.status_code != 200:
                        raise RPCError(
                            f"HTTP {response.status_code} from {endpoint}: {response.text}"
                        )
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise RPCError(
                            f"Invalid JSON from {endpoint}: {response.text}"
                        ) from exc
                    if data.get("error"):
                        raise RPCError(
                            f"RPC error from {endpoint}: {data['error']}"
                        )
                    if "result" not in data:
                        raise RPCError(f"Malformed response from {endpoint}: {data}")
                    return data["result"]
                except Exception as exc:
                    last_error = exc
                    if attempt < len(backoffs):
                        time.sleep(backoffs[attempt])
            # move to next endpoint

        raise RPCError(f"All RPC endpoints failed: {last_error}")


def get_balance(client: RPCClient, address: str, commitment: str) -> int:
    result = client.request("getBalance", [address, {"commitment": commitment}])
    return int(result.get("value", 0))


def get_tokens(
    client: RPCClient, address: str, commitment: str
) -> List[dict[str, Any]]:
    result = client.request(
        "getTokenAccountsByOwner",
        [
            address,
            {"programId": TOKEN_PROGRAM_ID},
            {"encoding": "jsonParsed", "commitment": commitment},
        ],
    )
    value = result.get("value", [])
    return parse_token_accounts(value)


def get_signatures(
    client: RPCClient, address: str, limit: int, commitment: str
) -> List[dict[str, Any]]:
    result = client.request(
        "getSignaturesForAddress",
        [address, {"limit": limit, "commitment": commitment}],
    )
    items: List[dict[str, Any]] = []
    for entry in result:
        items.append(
            {
                "signature": entry.get("signature"),
                "block_time": _iso_time_from_blocktime(entry.get("blockTime")),
                "confirmation_status": entry.get("confirmationStatus"),
                "err": _err_summary(entry.get("err")),
            }
        )
    return items


def _print_human(
    address: str,
    sol_lamports: int,
    tokens: List[dict[str, Any]],
    transactions: List[dict[str, Any]],
) -> None:
    print("\033[2J\033[H", end="")
    print("Solana Wallet Inspector")
    print("=" * 25)
    print(f"Address: {address}")
    print(
        f"SOL Balance: {format_sol(lamports_to_sol(sol_lamports))} SOL "
        f"({sol_lamports} lamports)"
    )

    print(f"SPL Tokens: {len(tokens)}")
    if tokens:
        mint_w = max(len(t["mint"]) for t in tokens)
        acct_w = max(len(t["token_account"]) for t in tokens)
        header = (
            f"{'Mint'.ljust(mint_w)}  {'Token Account'.ljust(acct_w)}  "
            f"{'Amount Raw':>12}  {'Dec':>3}  {'UI Amount':>12}"
        )
        print(header)
        for t in tokens:
            print(
                f"{t['mint'].ljust(mint_w)}  "
                f"{t['token_account'].ljust(acct_w)}  "
                f"{t['amount_raw']:>12}  "
                f"{t['decimals']:>3}  "
                f"{t['ui_amount']:>12}"
            )

    print(f"Recent Transactions: {len(transactions)}")
    if transactions:
        sig_w = max(len(t["signature"] or "") for t in transactions)
        header = (
            f"{'Signature'.ljust(sig_w)}  {'Block Time (UTC)':<25}  "
            f"{'Status':<10}  {'Err'}"
        )
        print(header)
        for t in transactions:
            sig = t["signature"] or ""
            status = t["confirmation_status"] or ""
            err = t["err"]
            print(
                f"{sig.ljust(sig_w)}  "
                f"{t['block_time']:<25}  "
                f"{status:<10}  "
                f"{err}"
            )


def _print_json(
    address: str,
    sol_lamports: int,
    tokens: List[dict[str, Any]],
    transactions: List[dict[str, Any]],
) -> None:
    payload = {
        "address": address,
        "sol_balance_lamports": sol_lamports,
        "sol_balance_sol": lamports_to_sol(sol_lamports),
        "tokens": tokens,
        "transactions": transactions,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solana Wallet Inspector")
    parser.add_argument("address", help="Solana wallet address (base58)")
    parser.add_argument(
        "--rpc",
        action="append",
        dest="rpc",
        help="RPC endpoint URL (can be specified multiple times)",
    )
    parser.add_argument("--limit", type=int, default=10, help="Number of txs")
    parser.add_argument("--timeout", type=float, default=10, help="Timeout seconds")
    parser.add_argument(
        "--commitment",
        choices=["processed", "confirmed", "finalized"],
        default="confirmed",
        help="Commitment level",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--no-tokens", action="store_true", help="Skip SPL tokens")
    parser.add_argument("--no-txs", action="store_true", help="Skip transactions")
    return parser.parse_args(argv)


def run(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    try:
        validate_address(args.address)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    endpoints = args.rpc if args.rpc else DEFAULT_ENDPOINTS
    client = RPCClient(endpoints=endpoints, timeout=args.timeout)

    try:
        sol_lamports = get_balance(client, args.address, args.commitment)
        tokens: List[dict[str, Any]] = []
        transactions: List[dict[str, Any]] = []

        if not args.no_tokens:
            tokens = get_tokens(client, args.address, args.commitment)
        if not args.no_txs:
            transactions = get_signatures(
                client, args.address, args.limit, args.commitment
            )
    except Exception as exc:
        print(f"RPC error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        _print_json(args.address, sol_lamports, tokens, transactions)
    else:
        _print_human(args.address, sol_lamports, tokens, transactions)

    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
