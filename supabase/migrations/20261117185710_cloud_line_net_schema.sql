-- pg_net is non-relocatable. Correct only our new, unused installation.
-- No CASCADE: any outside dependency aborts instead of removing user objects.
begin;
create schema if not exists extensions;
do $$ declare location text; begin
 select n.nspname into location from pg_extension e join pg_namespace n on n.oid=e.extnamespace where e.extname='pg_net';
 if location='public' then
  if exists(select 1 from net.http_request_queue) or exists(select 1 from net._http_response) then
   raise exception 'pg_net is in use; refusing to recreate its request/response tables';
  end if;
  drop extension pg_net;
  create extension pg_net with schema extensions;
 elsif location is null then
  create extension pg_net with schema extensions;
 end if;
end $$;
commit;
