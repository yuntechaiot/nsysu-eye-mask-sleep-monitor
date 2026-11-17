-- Only after stopping the dedicated Cron job and disabling the cloud gateway.
-- Back up nsysu_line first. Never use this file to remove research diary data.
begin;
do $$ begin
 if to_regclass('cron.job') is not null then
  if exists(select 1 from cron.job where jobname='nsysu-line-cloud-minute') then
   perform cron.unschedule('nsysu-line-cloud-minute');
  end if;
 end if;
end $$;
drop schema if exists nsysu_line cascade;
drop role if exists nsysu_line_api;
commit;
