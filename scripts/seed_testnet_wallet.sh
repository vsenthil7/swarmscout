#!/usr/bin/env bash
#
# seed_testnet_wallet.sh — top up the agent wallet with BNB from a faucet.
#
# BNB Testnet faucets rotate; three common ones are listed. Tries each in
# order; stops on first success. Run periodically (cron) to avoid the
# wallet running dry mid-run.

set -euo pipefail

: "${AGENT_WALLET_ADDRESS:?AGENT_WALLET_ADDRESS is required}"

FAUCETS=(
  "https://testnet.binance.org/faucet-smart"
  "https://testnet.bnbchain.org/faucet-smart"
  "https://faucet.quicknode.com/binance-smart-chain"
)

for f in "${FAUCETS[@]}"; do
  echo "trying ${f}"
  if curl -fsS -X POST "${f}" \
    -H "content-type: application/json" \
    -d "{\"address\":\"${AGENT_WALLET_ADDRESS}\"}" ; then
    echo "faucet request accepted by ${f}"
    exit 0
  fi
done

echo "no faucet accepted; manual top-up required"
exit 1
