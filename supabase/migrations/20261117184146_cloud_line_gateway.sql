-- Additive, disabled by default. No research diary rows or existing RPCs change.
begin;
create schema if not exists nsysu_line;
revoke all on schema nsysu_line from public,anon,authenticated;
do $$ begin
 if not exists(select 1 from pg_roles where rolname='nsysu_line_api') then
  create role nsysu_line_api nologin noinherit;
 end if;
end $$;
grant usage on schema nsysu_line to nsysu_line_api;
grant nsysu_line_api to postgres;

create table nsysu_line.config(
 id boolean primary key default true check(id),enabled boolean not null default false,
 allowed_users text[] not null default '{}',allow_all boolean not null default false,
 diary_url text not null default 'https://nsysu-eye-mask-sleep-monitor.streamlit.app/',
 binding_url text not null default 'https://nsysu-eye-mask-sleep-monitor.streamlit.app/?view=line');
insert into nsysu_line.config(id) values(true);
create table nsysu_line.accounts(
 account_hash text primary key,password_hash text not null,study text not null,member text not null unique,
 starts date,ends date,active boolean not null default true,check(starts is null or ends is null or starts<=ends));
create table nsysu_line.friends(line_user text primary key,active boolean not null,event_ms bigint not null);
create table nsysu_line.bindings(
 line_user text primary key,account_hash text not null unique references nsysu_line.accounts,
 bound_at timestamptz not null,reminder_start date not null,active boolean not null default true);
create table nsysu_line.events(
 event_id text primary key,line_user text not null,claim uuid not null default gen_random_uuid(),
 lease_until timestamptz not null,result jsonb not null,due_at timestamptz not null,finished boolean not null default false);
create table nsysu_line.link_requests(
 token_hash text primary key,line_user text not null,expires_at timestamptz not null);
create table nsysu_line.link_proofs(
 nonce_hash text primary key,token_hash text not null references nsysu_line.link_requests,
 account_hash text not null references nsysu_line.accounts,expires_at timestamptz not null,used_at timestamptz);
create table nsysu_line.cancellations(
 token_hash text primary key,line_user text not null,account_hash text not null,bound_at timestamptz not null,
 expires_at timestamptz not null,used_at timestamptz);
create table nsysu_line.binding_history(
 change_id uuid primary key default gen_random_uuid(),line_user text not null,account_hash text not null,
 study text not null,member text not null,bound_at timestamptz not null,reminder_start date not null,cancelled_at timestamptz not null);
create table nsysu_line.attempts(bucket text not null,at timestamptz not null);
create table nsysu_line.cron_tickets(token_hash text primary key,expires_at timestamptz not null);
create index line_attempts_bucket on nsysu_line.attempts(bucket,at);
create table nsysu_line.outbox(
 job_key text primary key,kind text not null check(kind in ('diary','interaction')),
 line_user text not null,study text,member text,target_date date,slot text,due_at timestamptz not null,
 retry_key uuid not null default gen_random_uuid() unique,payload jsonb not null,
 status text not null default 'pending',attempts integer not null default 0,
 uncertainty boolean not null default false,retry_at timestamptz,processed_at timestamptz,error_code text,request_id text,
 unique(study,member,target_date,slot));
create index line_pending_outbox on nsysu_line.outbox(due_at) where status in ('pending','retry','uncertain');

create function nsysu_line.now() returns timestamptz language sql volatile set search_path='' as $$select clock_timestamp()$$;
revoke all on function nsysu_line.now() from public,anon,authenticated;
grant execute on function nsysu_line.now() to nsysu_line_api;

-- Least-privilege snapshot: no direct backend-role access to Vault or research rows.
create function nsysu_line.diary_snapshot(p_member text,p_day date) returns jsonb
language plpgsql security definer set search_path='' as $$
declare a nsysu_line.accounts%rowtype; capability text;
begin
 select * into a from nsysu_line.accounts where member=p_member and active;
 if not found or (a.starts is not null and p_day<a.starts) or (a.ends is not null and p_day>a.ends)
  or not exists(select 1 from public.research_participants where member_id=p_member and archived_at is null) then
  return jsonb_build_object('active',false,'completed',false,'invite',null);
 end if;
 select v.decrypted_secret into capability from nsysu_private.diary_invitations i
 join vault.decrypted_secrets v on v.id=i.fixed_secret_id
 where i.member_id=p_member and i.revoked_at is null and i.fixed_secret_id is not null;
 if capability is null or not nsysu_private.check_diary_invitation(p_member,capability) then capability:=null; end if;
 return jsonb_build_object('active',true,'completed',exists(
  select 1 from public.sleep_logs where member_id=p_member and date=p_day::text and date_definition='wake_date'),
  'invite',capability);
end $$;
revoke all on function nsysu_line.diary_snapshot(text,date) from public,anon,authenticated;
grant execute on function nsysu_line.diary_snapshot(text,date) to nsysu_line_api;

do $$ declare item record; begin
 for item in select tablename from pg_tables where schemaname='nsysu_line' loop
  execute format('alter table nsysu_line.%I enable row level security',item.tablename);
  execute format('create policy backend_only on nsysu_line.%I for all to nsysu_line_api using(true) with check(true)',item.tablename);
 end loop;
end $$;
revoke all on all tables in schema nsysu_line from public,anon,authenticated;
grant select,insert,update,delete on all tables in schema nsysu_line to nsysu_line_api;
alter default privileges in schema nsysu_line revoke execute on functions from public;
commit;
