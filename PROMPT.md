# Task: Build a Uniswap V2 Frontend

Build a simple, functional frontend for interacting with Uniswap V2 on Base chain.

## Requirements

- [ ] Create a React + Vite application in a `uniswap-frontend/` directory
- [ ] Implement wallet connection using ethers.js or wagmi
- [ ] Add token swap interface with:
  - Token input/output selectors
  - Amount inputs with balance display
  - Price impact calculation
  - Swap button with transaction handling
- [ ] Add liquidity pool interface:
  - Add liquidity form
  - Remove liquidity form
  - Pool share display
- [ ] Style with Tailwind CSS - dark mode, modern UI
- [ ] Connect to Uniswap V2 Router on Base (0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24)

## Technical Details

- Base Chain ID: 8453
- Uniswap V2 Router: 0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24
- Uniswap V2 Factory: 0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6
- WETH on Base: 0x4200000000000000000000000000000000000006

## Success Criteria

- App runs locally with `npm run dev`
- Can connect MetaMask wallet
- Can view token balances
- Can execute swaps (with proper error handling)
- Clean, responsive UI

When the task is complete, output "LOOP_COMPLETE" to signal completion.
