begin;
set local lock_timeout='5s';
-- Backend-only capability: no login/password is provisioned by this migration.
do $$ begin
 if not exists(select 1 from pg_roles where rolname='nsysu_line_reader') then
   create role nsysu_line_reader nologin noinherit;
 end if;
end $$;
create table nsysu_private.line_subjects(
 member_id text primary key references public.research_participants(member_id),
 study_id text not null check(length(study_id) between 1 and 80),
 start_date date,end_date date,enabled boolean not null default true,
 check(start_date is null or end_date is null or start_date<=end_date));
alter table nsysu_private.line_subjects enable row level security;
revoke all on nsysu_private.line_subjects from public,anon,authenticated,nsysu_line_reader;
create function nsysu_private.line_diary_snapshot(p_member text,p_day date)
returns jsonb language sql stable security definer set search_path='' as $$
 select jsonb_build_object('study',s.study_id,
   'active',s.enabled and p.archived_at is null
      and (s.start_date is null or p_day>=s.start_date) and (s.end_date is null or p_day<=s.end_date),
   'completed',exists(select 1 from public.sleep_logs l where l.member_id=p.member_id
       and l.date=p_day::text and l.date_definition='wake_date'),
   'invite',case when i.revoked_at is null and i.expires_at>now() then v.decrypted_secret end)
 from nsysu_private.line_subjects s join public.research_participants p on p.member_id=s.member_id
 left join nsysu_private.diary_invitations i on i.member_id=p.member_id
 left join vault.decrypted_secrets v on v.id=i.fixed_secret_id
 where s.member_id=p_member;
$$;
-- This definer is private, has no browser grants, and exposes only enrolled
-- member/date snapshots to a separately provisioned trusted backend DB role.
revoke all on function nsysu_private.line_diary_snapshot(text,date) from public,anon,authenticated;
grant usage on schema nsysu_private to nsysu_line_reader;
grant execute on function nsysu_private.line_diary_snapshot(text,date) to nsysu_line_reader;
commit;
