# Bingo Habesha

## Secure backend setup

The static game is a browser demo. Deposits are recorded for admin review; approval only changes the request status and does not credit the browser balance. Promo codes can award 40 ETB to a user's local demo balance once per code, but the reward is not withdrawable. The Withdraw button opens an information screen; withdrawals are not accepted until wagering rules and server-verified winnings are implemented.

1. Apply [`supabase_schema.sql`](./supabase_schema.sql) in the Supabase SQL Editor. Reapply it after updating this project to create the payment-settings and promo-redemption tables.
2. Deploy [`render.yaml`](./render.yaml) as a Render Blueprint.
3. Configure the Render environment variables:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY` (server-side only; never put this in HTML)
   - `TELEGRAM_BOT_TOKEN` (rotate the previously exposed token before setting it)
   - `TELEGRAM_ADMIN_ID` (the numeric Telegram ID authorized to review deposits)
   - `APP_ORIGIN` (the Pages origin, e.g. `https://addisuyosef62-sudo.github.io`, without a repository path)
   - `WEB_APP_URL` (the deployed Pages URL)
4. In `index.html`, set the `bingo-api-url` meta tag to the HTTPS URL Render assigns to `randombingo-api`.
5. Configure the Telegram bot's Mini App URL to the deployed Pages URL.

Users must register with the bot and share their own phone contact before changing a password. Password changes require an authenticated Telegram Mini App session; phone/password browser login is not implemented. Deposit requests require an authenticated Telegram Mini App session. Approving a deposit changes the request status only; it does not credit the browser-managed game balance.

After deploying the bot and applying the schema, use its private admin chat to configure deposit accounts:

```text
/setpayment telebirr 09XXXXXXXX Account Name
/setpayment cbe 09XXXXXXXX Account Name
```

The same settings are shown in the web deposit modal and Telegram deposit flow. Until configured, users cannot submit web deposit requests. Set one active promo code with `/setcoupon CODE`; each Telegram user can redeem it once for 40 ETB in the browser demo. Use `/setcoupon off` to deactivate the code. Codes must be shared with users separately.

The bottom navigation provides Home, Tickets, Wallet, and Profile. Withdrawals intentionally remain unavailable until wagering and authoritative server-side balances are implemented.

The Wallet view shows the local Play Wallet balance and the authenticated profile's Main Wallet (`winnings_balance`), along with an empty transaction-history state. New accounts start with 5 ETB in the Play Wallet; existing balances are preserved when applying the schema update.
