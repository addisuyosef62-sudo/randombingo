create table if not exists public.user_profiles (
    user_id text primary key,
    full_name text,
    phone_number text,
    balance numeric(12, 2) not null default 5.00,
    winnings_balance numeric(12, 2) not null default 0.00,
    password_hash text,
    phone_verified_at timestamptz,
    updated_at timestamptz not null default now()
);

alter table public.user_profiles
    add column if not exists password_hash text,
    add column if not exists phone_verified_at timestamptz,
    add column if not exists winnings_balance numeric(12, 2) not null default 0.00,
    alter column balance set default 5.00;

create table if not exists public.wallet_deposit_requests (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    telegram_user_id bigint not null,
    user_name text not null default '',
    amount numeric(12, 2) not null check (amount >= 50 and amount <= 100000),
    payment_method text not null check (payment_method in ('TeleBirr', 'CBE Birr')),
    payment_proof text not null check (length(payment_proof) between 8 and 10000),
    status text not null default 'pending_review'
        check (status in ('pending_review', 'approved', 'rejected')),
    reviewed_by bigint,
    reviewed_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists public.app_settings (
    key text primary key,
    value jsonb not null,
    updated_by bigint,
    updated_at timestamptz not null default now()
);

create table if not exists public.wallet_coupon_redemptions (
    id uuid primary key default gen_random_uuid(),
    coupon_code text not null,
    user_id text not null,
    telegram_user_id bigint not null,
    reward_amount numeric(12, 2) not null check (reward_amount = 40.00),
    created_at timestamptz not null default now(),
    unique (coupon_code, user_id)
);

create index if not exists wallet_deposit_requests_user_created_idx
    on public.wallet_deposit_requests (user_id, created_at desc);

create unique index if not exists wallet_deposit_requests_one_pending_per_user_idx
    on public.wallet_deposit_requests (user_id)
    where status = 'pending_review';

create or replace function public.review_wallet_deposit(
    request_id uuid,
    new_status text,
    reviewer_id bigint
) returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
    if new_status not in ('approved', 'rejected') then
        raise exception 'Invalid deposit review status';
    end if;

    update wallet_deposit_requests
       set status = new_status,
           reviewed_by = reviewer_id,
           reviewed_at = now()
     where id = request_id
       and status = 'pending_review';

    return found;
end;
$$;

alter table public.user_profiles enable row level security;
alter table public.wallet_deposit_requests enable row level security;
alter table public.app_settings enable row level security;
alter table public.wallet_coupon_redemptions enable row level security;
revoke all on public.user_profiles from anon, authenticated;
revoke all on public.wallet_deposit_requests from anon, authenticated;
revoke all on public.app_settings from anon, authenticated;
revoke all on public.wallet_coupon_redemptions from anon, authenticated;
grant all on public.user_profiles, public.wallet_deposit_requests,
    public.app_settings, public.wallet_coupon_redemptions to service_role;
revoke all on function public.review_wallet_deposit(uuid, text, bigint)
    from public, anon, authenticated;
grant execute on function public.review_wallet_deposit(uuid, text, bigint)
    to service_role;
