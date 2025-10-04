-- Run this in your Supabase project's SQL Editor.

create table if not exists public.progress (
  user_id uuid primary key references auth.users(id) on delete cascade,
  attempts integer not null default 0,
  correct integer not null default 0,
  wrong_ids jsonb not null default '[]',
  seen_ids  jsonb not null default '[]',
  updated_at timestamptz not null default now()
);

alter table public.progress enable row level security;

create policy "select own progress"
on public.progress for select
to authenticated
using (auth.uid() = user_id);

create policy "insert own progress"
on public.progress for insert
to authenticated
with check (auth.uid() = user_id);

create policy "update own progress"
on public.progress for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);
