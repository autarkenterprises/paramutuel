# Testnet Rehearsal Matrix (Execution Sheet)

Use this sheet while executing `docs/TESTNET-REHEARSAL.md`.

## Environment

- Chain: `________________________`
- Factory: `________________________`
- Indexer DB path: `________________________`
- Run ID / date: `________________________`

## Wager set (minimum 5)

1. **Finite resolved**
   - Wager: `________________`
   - Expected: `RESOLVED`
   - Result: `[ ] pass  [ ] fail`

2. **Finite retracted**
   - Wager: `________________`
   - Expected: `RETRACTED`
   - Result: `[ ] pass  [ ] fail`

3. **Finite expired by third party**
   - Wager: `________________`
   - Expected: `RETRACTED` via `expire()`
   - Result: `[ ] pass  [ ] fail`

4. **Delegated resolver/closers**
   - Wager: `________________`
   - Expected: delegated role calls succeed, unauthorized calls revert
   - Result: `[ ] pass  [ ] fail`

5. **No-max closer-managed**
   - Wager: `________________`
   - Expected: cannot progress until closer calls; then lifecycle completes
   - Result: `[ ] pass  [ ] fail`

## Service checks

- Indexer state accurate for all wagers: `[ ] pass  [ ] fail`
- Explorer displays all states correctly: `[ ] pass  [ ] fail`
- Control panel web + CLI both operate correctly: `[ ] pass  [ ] fail`
- Sweeper handles candidates and idempotency: `[ ] pass  [ ] fail`

## Accounting checks

- Fee accrual expected vs actual: `[ ] pass  [ ] fail`
- Fee withdrawal to treasury/Safe: `[ ] pass  [ ] fail`
- Claims distribute correctly for each scenario: `[ ] pass  [ ] fail`

## Outcome

- Rehearsal status: `[ ] PASS  [ ] FAIL`
- Incidents/notes:
  - `__________________________________________________________`
  - `__________________________________________________________`
  - `__________________________________________________________`
