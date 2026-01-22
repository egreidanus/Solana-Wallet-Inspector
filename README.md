# Solana Wallet Inspector (CLI)

Terminal-based inspector for Solana wallet balances, SPL token holdings, and recent transactions.

## Features
- SOL balance (lamports and SOL)
- SPL token balances (mint, token account, raw amount, decimals, UI amount)
- Recent transaction signatures with status, block time, and error summary
- Multiple RPC endpoints with failover + exponential backoff
- Human-readable or JSON output

## Requirements
- Python 3.11+
- Dependencies: `requests`

## Install
```bash
git clone https://github.com/egreidanus/Solana-Wallet-Inspector.git
cd Solana-Wallet-Inspector
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage
```bash
python sol_inspect.py <WALLET_ADDRESS>
python sol_inspect.py <WALLET_ADDRESS> --limit 20 --commitment finalized
python sol_inspect.py <WALLET_ADDRESS> --rpc https://api.mainnet-beta.solana.com --rpc https://solana.drpc.org
python sol_inspect.py <WALLET_ADDRESS> --json
python sol_inspect.py <WALLET_ADDRESS> --no-tokens --no-txs
```

### CLI options
- `--rpc URL` Override/add RPC endpoint(s). Can be provided multiple times.
- `--limit N` Number of recent signatures (default: 10).
- `--timeout SECONDS` HTTP timeout (default: 10).
- `--commitment processed|confirmed|finalized` Commitment level (default: confirmed).
- `--json` Output machine-readable JSON only.
- `--no-tokens` Skip SPL token balances.
- `--no-txs` Skip recent transactions.

## Output (JSON mode)
```json
{
  "address": "...",
  "sol_balance_lamports": 0,
  "sol_balance_sol": 0.0,
  "tokens": [
    {
      "mint": "...",
      "token_account": "...",
      "amount_raw": "...",
      "decimals": 6,
      "ui_amount": "..."
    }
  ],
  "transactions": [
    {
      "signature": "...",
      "block_time": "...",
      "confirmation_status": "confirmed",
      "err": ""
    }
  ]
}
```


## Exit codes
- `0` success
- `1` runtime/RPC error
- `2` invalid user input

## Notes
- This tool is inspection-only and never handles private keys.
- RPC requests are made directly via JSON-RPC over HTTP POST.

## License
This project is distributed under the MIT license.

## Support Me
Any donation will make me happy and will keep this project online :)

SOL: `DMWGUXuEEaVY4xT4jcEZPace76J2DYV4FXPBmk9411sc`

BTC: `bc1qtj5c7mg9c5mmg0mv84reh7emwl5j9scqnwzfak`

ETH: `0xe547e12225a52A6cc9A4a4ea6a352fFCAF38ae4C`
