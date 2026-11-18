"""Trusted browser session handoffs; credentials never appear in a URL."""
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

_component = components.declare_component('nsysu_auth_bridge', path=str(Path(__file__).resolve().parents[2] / 'frontend/auth_bridge'))
_home_component = components.declare_component('nsysu_auth_return', path=str(Path(__file__).resolve().parents[2] / 'frontend/auth_return'))


def home_link(diary_url):
    """Return through a trusted browser handoff, never credentials in a URL."""
    _home_component(diary_url=diary_url, key='research_home_link', default=None)


def synchronize(diary_url):
    value = _component(diary_url=diary_url,
                       operation='clear' if st.session_state.get('_auth_clear') else 'read',
                       session=st.session_state.get('supabase_session'), key='research_auth_bridge', default=None)
    if value is None:
        st.info('正在確認登入狀態…')
        return False
    if st.session_state.get('_auth_clear'):
        if not value.get('cleared'):
            st.info('正在更新登入狀態…')
            return False
        st.session_state.pop('_auth_clear', None)
    if value.get('logged_out') and value['logged_out'] != st.session_state.get('_auth_logout_event'):
        st.session_state['_auth_logout_event'] = value['logged_out']
        for key in ('supabase_session','platform_token','dashboard_data','flow_platform_members'):
            st.session_state.pop(key, None)
        st.session_state['_auth_initialized'] = True
    if value.get('session_updated') and value['session_updated'] != st.session_state.get('_auth_update_event'):
        st.session_state['_auth_update_event'] = value['session_updated']
        saved, current = value.get('session'), st.session_state.get('supabase_session')
        if isinstance(saved, dict) and saved.get('access_token') and saved.get('refresh_token'):
            if isinstance(current, dict) and saved.get('user', {}).get('id') != current.get('user', {}).get('id'):
                for key in ('platform_token', 'dashboard_data', 'flow_platform_members'):
                    st.session_state.pop(key, None)
            # Identity/role is revalidated by research_store, not this message.
            st.session_state['supabase_session'] = saved
    if not st.session_state.get('_auth_initialized'):
        st.session_state['_auth_initialized'] = True
        saved = value.get('session')
        if isinstance(saved, dict) and isinstance(saved.get('access_token'), str) and isinstance(saved.get('refresh_token'), str):
            # research_store performs server verification and current DB role checks.
            st.session_state['supabase_session'] = saved
    return True
