-- Written first, so the policy names a table no migration has created yet.
alter table public.orders enable row level security;
create policy "Orders are private." on public.orders for select using (false);
