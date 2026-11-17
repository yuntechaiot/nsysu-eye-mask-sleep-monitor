-- Stop reminders first, export private enrollment records, then apply.
begin;
drop function if exists nsysu_private.line_diary_snapshot(text,date);
drop table if exists nsysu_private.line_subjects;
-- Keep the NOLOGIN role; credential/role provisioning is managed separately.
commit;
