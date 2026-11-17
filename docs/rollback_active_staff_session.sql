-- Restore baseline permission helper. Stop new app/worker and restore state backup first.
begin;
create or replace function nsysu_private.is_diary_staff() returns boolean
language sql stable security definer set search_path='' as $$
 select (select auth.uid()) is not null and exists(
  select 1 from auth.users u where u.id=(select auth.uid())
   and u.raw_app_meta_data->>'diary_staff'='true' and u.deleted_at is null
   and (u.banned_until is null or u.banned_until<now())
 );
$$;
revoke all on function nsysu_private.is_diary_staff() from public,anon;
grant execute on function nsysu_private.is_diary_staff() to authenticated;
commit;
