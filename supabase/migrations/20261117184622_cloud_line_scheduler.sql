-- Explicit deployment step, not part of schema creation. Keep inactive until
-- the cloud page, LINE webhook, private roster and owner test are confirmed.
-- Short-lived one-time tickets avoid putting any long-lived secret in Cron SQL.
create extension if not exists pg_cron;
create extension if not exists pg_net;
create or replace function nsysu_line.request_tick() returns bigint
language plpgsql security definer set search_path='' as $fn$
declare ticket text:=replace(gen_random_uuid()::text||gen_random_uuid()::text,'-','');
begin
 if not (select enabled from nsysu_line.config where id=true) then return null; end if;
 delete from nsysu_line.cron_tickets where expires_at<clock_timestamp();
 insert into nsysu_line.cron_tickets values(encode(sha256(convert_to(ticket,'UTF8')),'hex'),clock_timestamp()+interval '2 minutes');
 return net.http_post(
  url:='https://ztsyxnrnemvcladbaaem.supabase.co/functions/v1/nsysu-line/tick',
  headers:=jsonb_build_object('Content-Type','application/json','Authorization','Bearer '||ticket),
  body:='{}'::jsonb,timeout_milliseconds:=120000);
end $fn$;
revoke all on function nsysu_line.request_tick() from public,anon,authenticated,nsysu_line_api;
select cron.schedule('nsysu-line-cloud-minute','* * * * *',$job$
 select nsysu_line.request_tick();
$job$);
select cron.alter_job((select jobid from cron.job where jobname='nsysu-line-cloud-minute'),active:=false);
