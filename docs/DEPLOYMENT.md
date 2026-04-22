# Deployment

## FindingsRegistry on BNB Testnet

| Field | Value |
|---|---|
| Contract | `FindingsRegistry` |
| Address | _to be populated on first deploy_ |
| Chain | BNB Testnet (chain id 97) |
| Deploy tx | _to be populated_ |
| Deployer address | `$AGENT_WALLET_PRIVATE_KEY` → derived address |
| Deployed at block | _to be populated_ |
| BscScan | https://testnet.bscscan.com/address/&lt;address&gt; |
| Source verified | yes / no |

## Deploy steps

```bash
cd contracts
forge script script/Deploy.s.sol \
  --rpc-url bsc_testnet \
  --broadcast \
  --private-key $AGENT_WALLET_PRIVATE_KEY

# Capture the address printed by console2.log and paste it into .env as:
#   FINDINGS_REGISTRY_ADDRESS=0x....

# Verify on BscScan:
forge verify-contract \
  --chain 97 \
  --etherscan-api-key $BSCSCAN_API_KEY \
  <address> \
  src/FindingsRegistry.sol:FindingsRegistry
```

## Live URLs

| Surface | URL |
|---|---|
| Public API | _to be populated_ |
| Dashboard | _to be populated_ |
| Telegram bot | _to be populated_ |
| Contract | _to be populated_ |

## Smoke test after deploy

```bash
API_URL=https://api.example.com \
DASHBOARD_URL=https://dash.example.com \
bash scripts/smoke_test.sh
```
