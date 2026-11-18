begin;
set local lock_timeout='5s';
create schema nsysu_staff;
revoke all on schema nsysu_staff from public,anon,authenticated;
do $$ begin
 if not exists(select 1 from pg_roles where rolname='nsysu_staff_api') then create role nsysu_staff_api nologin noinherit; end if;
end $$;
grant nsysu_staff_api to postgres;
grant usage on schema nsysu_staff to nsysu_staff_api;
create table nsysu_staff.config(id boolean primary key default true check(id),require_docter boolean not null default false);
insert into nsysu_staff.config values(true,false);
create table nsysu_staff.sessions(
 session_id uuid primary key references auth.sessions(id) on delete cascade,
 user_id uuid not null references auth.users(id) on delete cascade,
 token_cipher text not null,account_hash text not null,provider_expires timestamptz,created_at timestamptz not null default now());
create table nsysu_staff.attempts(bucket text not null,at timestamptz not null default now());
create index staff_attempts_bucket on nsysu_staff.attempts(bucket,at);
alter table nsysu_staff.config enable row level security;
alter table nsysu_staff.sessions enable row level security;
alter table nsysu_staff.attempts enable row level security;
create policy backend_sessions on nsysu_staff.sessions for all to nsysu_staff_api using(true) with check(true);
create policy backend_attempts on nsysu_staff.attempts for all to nsysu_staff_api using(true) with check(true);
revoke all on all tables in schema nsysu_staff from public,anon,authenticated;
grant select,insert,update,delete on nsysu_staff.sessions,nsysu_staff.attempts to nsysu_staff_api;
create function nsysu_staff.identity(p_account text) returns jsonb
language sql stable security definer set search_path='' as $$
 select case when count(*)=1 then (jsonb_agg(jsonb_build_object('id',u.id,'email',u.email,'account',u.raw_app_meta_data->>'diary_username')))->0 end
 from auth.users u where lower(u.raw_app_meta_data->>'diary_username')=lower(trim(p_account))
 and u.email=lower(u.raw_app_meta_data->>'diary_username')||'@diary.nsysu.invalid'
 and u.raw_app_meta_data->>'diary_staff'='true' and u.deleted_at is null
 and (u.banned_until is null or u.banned_until<now());
$$;
create function nsysu_staff.allowed_session(p_user uuid,p_session uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from auth.users u join auth.sessions s on s.user_id=u.id
 where u.id=p_user and s.id=p_session and u.raw_app_meta_data->>'diary_staff'='true'
 and u.deleted_at is null and (u.banned_until is null or u.banned_until<now())
 and (s.not_after is null or s.not_after>now()));
$$;
revoke all on function nsysu_staff.identity(text),nsysu_staff.allowed_session(uuid,uuid) from public,anon,authenticated;
grant execute on function nsysu_staff.identity(text),nsysu_staff.allowed_session(uuid,uuid) to nsysu_staff_api;
-- Rollout flag preserves existing sessions while the new cloud UI is deployed.
-- After owner acceptance, require the DocterCloud-backed session for all RLS.
create or replace function nsysu_private.is_diary_staff() returns boolean
language sql stable security definer set search_path='' as $$
 select (select auth.uid()) is not null and exists(
  select 1 from auth.users u join auth.sessions s on s.user_id=u.id
  where u.id=(select auth.uid()) and u.raw_app_meta_data->>'diary_staff'='true'
  and u.deleted_at is null and (u.banned_until is null or u.banned_until<now())
  and s.id::text=(select auth.jwt())->>'session_id' and (s.not_after is null or s.not_after>now())
  and (not (select require_docter from nsysu_staff.config where id=true) or exists(
    select 1 from nsysu_staff.sessions d where d.session_id=s.id and d.user_id=u.id
    and (d.provider_expires is null or d.provider_expires>now())))
 );
$$;
revoke all on function nsysu_private.is_diary_staff() from public,anon;
grant execute on function nsysu_private.is_diary_staff() to authenticated;
alter default privileges in schema nsysu_staff revoke execute on functions from public;
commit;
