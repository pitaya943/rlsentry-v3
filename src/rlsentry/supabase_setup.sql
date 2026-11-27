-- Supabase's setup as the copy needs it, loaded by the copy's superuser (`rlsentry`) before any
-- migration. It follows the roles, schemas, auth functions and default privileges of
-- supabase/postgres 15.8.1.x (the 15.x line's setup), as far as migrations name them.
-- Kept apart from the migrations: nothing here gives the role `postgres` a way to the machine.

-- Roles ---------------------------------------------------------------------------------------
create role anon nologin noinherit;
create role authenticated nologin noinherit;
create role service_role nologin noinherit bypassrls;
create role authenticator login noinherit;
grant anon, authenticated, service_role to authenticator;

-- The migrations' role: not a superuser, holds none of pg_execute_server_program,
-- pg_read_server_files or pg_write_server_files; it may bypass row-level security (for seeding)
-- and, as on Supabase, alter the API roles (which is how a migration puts a setting on them).
create role postgres login createrole bypassrls;
grant anon, authenticated, service_role, authenticator to postgres with admin option;
alter database postgres owner to postgres;  -- so `public` (owned by pg_database_owner) is theirs
alter role postgres set search_path = "$user", public, extensions;

-- On Supabase the migrations' role may make PostgREST's in-database settings. The copy lets it,
-- so that the settings check after the migrations (not a failed statement) names them.
grant set on parameter
  pgrst.db_aggregates_enabled, pgrst.db_anon_role, pgrst.db_extra_search_path,
  pgrst.db_hoisted_tx_settings, pgrst.db_max_rows, pgrst.db_plan_enabled, pgrst.db_pre_config,
  pgrst.db_pre_request, pgrst.db_prepared_statements, pgrst.db_root_spec, pgrst.db_schemas,
  pgrst.db_tx_end, pgrst.jwt_aud, pgrst.jwt_cache_max_lifetime, pgrst.jwt_role_claim_key,
  pgrst.jwt_secret, pgrst.jwt_secret_is_base64, pgrst.openapi_mode, pgrst.openapi_security_active,
  pgrst.openapi_server_proxy_uri, pgrst.raw_media_types, pgrst.server_cors_allowed_origins,
  pgrst.server_timing_enabled, pgrst.server_trace_header
  to postgres;

-- Schemas -------------------------------------------------------------------------------------
grant usage on schema public to anon, authenticated, service_role;
alter default privileges for role postgres in schema public
  grant all on tables to anon, authenticated, service_role;
alter default privileges for role postgres in schema public
  grant all on sequences to anon, authenticated, service_role;
alter default privileges for role postgres in schema public
  grant all on functions to anon, authenticated, service_role;

create schema extensions;
grant usage on schema extensions to postgres, anon, authenticated, service_role;

create schema graphql_public;
grant usage on schema graphql_public to postgres, anon, authenticated, service_role;

-- auth: the users table and the request functions --------------------------------------------
create schema auth;
grant usage on schema auth to postgres, anon, authenticated, service_role;

create table auth.users (
  instance_id uuid,
  id uuid primary key,
  aud varchar(255),
  role varchar(255),
  email varchar(255),
  encrypted_password varchar(255),
  email_confirmed_at timestamptz,
  invited_at timestamptz,
  confirmation_token varchar(255),
  confirmation_sent_at timestamptz,
  recovery_token varchar(255),
  recovery_sent_at timestamptz,
  email_change_token_new varchar(255),
  email_change varchar(255),
  email_change_sent_at timestamptz,
  last_sign_in_at timestamptz,
  raw_app_meta_data jsonb,
  raw_user_meta_data jsonb,
  is_super_admin boolean,
  created_at timestamptz,
  updated_at timestamptz,
  phone text unique default null,
  phone_confirmed_at timestamptz,
  phone_change text default '',
  phone_change_token varchar(255) default '',
  phone_change_sent_at timestamptz,
  confirmed_at timestamptz generated always as (least(email_confirmed_at, phone_confirmed_at)) stored,
  email_change_token_current varchar(255) default '',
  email_change_confirm_status smallint default 0,
  banned_until timestamptz,
  reauthentication_token varchar(255) default '',
  reauthentication_sent_at timestamptz,
  is_sso_user boolean not null default false,
  deleted_at timestamptz,
  is_anonymous boolean not null default false
);
-- Migrations reference it (foreign keys) and put triggers on it, as on Supabase.
grant all on auth.users to postgres;

create function auth.uid() returns uuid language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;

create function auth.role() returns text language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.role', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role')
  )::text
$$;

create function auth.jwt() returns jsonb language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim', true), ''),
    nullif(current_setting('request.jwt.claims', true), '')
  )::jsonb
$$;

grant execute on function auth.uid(), auth.role(), auth.jwt()
  to postgres, anon, authenticated, service_role;

-- Extensions: the fixed list, created in `extensions` before the migrations ------------------
create extension pgcrypto with schema extensions;
create extension "uuid-ossp" with schema extensions;
create extension citext with schema extensions;
create extension pg_trgm with schema extensions;
create extension btree_gin with schema extensions;
create extension btree_gist with schema extensions;
create extension hstore with schema extensions;
create extension ltree with schema extensions;
create extension intarray with schema extensions;
create extension fuzzystrmatch with schema extensions;
create extension tablefunc with schema extensions;
create extension isn with schema extensions;

-- The guard: any other extension is refused. Owned by the superuser in a schema nobody else may
-- use, so the migrations' role can neither drop nor disable it. It runs inside the migrations' own
-- session, so it names the catalog in full and pins its search_path (pg_temp last, so no temporary
-- object or operator of theirs is found first), and a name it cannot find is refused, not let through.
create schema rlsentry;
revoke all on schema rlsentry from public;

create function rlsentry.only_listed_extensions() returns event_trigger
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare
  r record;
  name text;
begin
  for r in select * from pg_catalog.pg_event_trigger_ddl_commands() where command_tag = 'CREATE EXTENSION' loop
    select e.extname into name from pg_catalog.pg_extension e where e.oid = r.objid;
    if name is null or name not in ('pgcrypto', 'uuid-ossp', 'citext', 'pg_trgm', 'btree_gin', 'btree_gist',
                    'hstore', 'ltree', 'intarray', 'fuzzystrmatch', 'tablefunc', 'isn') then
      raise exception 'extension "%" is not on the list the copy allows', name
        using errcode = 'insufficient_privilege',
              hint = 'rlsentry allows only extensions that touch neither files nor the network';
    end if;
  end loop;
end
$$;

create event trigger rlsentry_only_listed_extensions on ddl_command_end
  when tag in ('CREATE EXTENSION')
  execute function rlsentry.only_listed_extensions();
alter event trigger rlsentry_only_listed_extensions enable always;
