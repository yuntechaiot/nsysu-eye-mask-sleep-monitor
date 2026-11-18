begin;
-- Configuration is owner-managed; API/browser roles are explicitly denied.
create policy owner_config_only on nsysu_staff.config for all to anon,authenticated,nsysu_staff_api using(false) with check(false);
create function nsysu_staff.finish_login(p_user uuid,p_session uuid,p_account_hash text,p_cipher text,p_expires timestamptz)
returns void language plpgsql security definer set search_path='' as $$
begin
 if not nsysu_staff.allowed_session(p_user,p_session) then raise exception 'Current staff session required'; end if;
 insert into nsysu_staff.sessions(session_id,user_id,account_hash,token_cipher,provider_expires)
 values(p_session,p_user,p_account_hash,p_cipher,p_expires)
 on conflict(session_id) do update set user_id=excluded.user_id,account_hash=excluded.account_hash,
 token_cipher=excluded.token_cipher,provider_expires=excluded.provider_expires;
 -- Only reached after the broker verifies the real DocterCloud password.
 -- First accepted login completes rollout, rejecting legacy password-only sessions.
 update nsysu_staff.config set require_docter=true where id=true;
end;
$$;
revoke all on function nsysu_staff.finish_login(uuid,uuid,text,text,timestamptz) from public,anon,authenticated;
grant execute on function nsysu_staff.finish_login(uuid,uuid,text,text,timestamptz) to nsysu_staff_api;
revoke insert,update,delete on nsysu_staff.sessions from nsysu_staff_api;
commit;
