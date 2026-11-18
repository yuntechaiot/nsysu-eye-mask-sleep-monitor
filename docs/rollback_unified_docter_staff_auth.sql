begin;
create or replace function nsysu_private.is_diary_staff() returns boolean
language sql stable security definer set search_path='' as $$
 select (select auth.uid()) is not null and exists(
 select 1 from auth.users u join auth.sessions s on s.user_id=u.id where u.id=(select auth.uid())
 and u.raw_app_meta_data->>'diary_staff'='true' and u.deleted_at is null
 and (u.banned_until is null or u.banned_until<now())
 and s.id::text=(select auth.jwt())->>'session_id' and (s.not_after is null or s.not_after>now()));
$$;
revoke all on function nsysu_private.is_diary_staff() from public,anon;
grant execute on function nsysu_private.is_diary_staff() to authenticated;
drop schema if exists nsysu_staff cascade;
revoke nsysu_staff_api from postgres;
drop role if exists nsysu_staff_api;
commit;
