-- The profiles table of Supabase's user-management starter, with its read policy left as shipped.
create extension if not exists "uuid-ossp" with schema extensions;

create table public.profiles (
  id uuid not null references auth.users on delete cascade primary key,
  username text unique,
  full_name text,
  phone text,
  updated_at timestamptz default now()
);
alter table public.profiles enable row level security;

create policy "Public profiles are viewable by everyone." on public.profiles
  for select using (true);
create policy "Users can insert their own profile." on public.profiles
  for insert with check ((select auth.uid()) = id);
create policy "Users can update own profile." on public.profiles
  for update using ((select auth.uid()) = id);

create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, full_name) values (new.id, new.raw_user_meta_data ->> 'full_name');
  return new;
end;
$$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute procedure public.handle_new_user();
