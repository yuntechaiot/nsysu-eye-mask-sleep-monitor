"""Dedicated cloud Account Linking page; no local listener or LIFF iframe."""
import hashlib
from urllib.parse import urlsplit

import requests
import streamlit as st

from .config import setting


def main():
    st.title('研究帳號綁定')
    st.write('請輸入研究配發的 Docter+ 帳號與密碼。核對後，回到 LINE 完成綁定。')
    token = st.query_params.get('link_token', '')
    if not isinstance(token, str) or not 1 <= len(token) <= 1000:
        st.info('請回到官方 LINE 聊天室，點選「開始綁定」或「重新綁定」。')
        return
    fingerprint = hashlib.sha256(token.encode()).hexdigest()
    if st.session_state.get('_line_request') != fingerprint:
        st.session_state['_line_request'] = fingerprint
        st.session_state.pop('_line_confirm_url', None)
    with st.form('research_line_binding', clear_on_submit=True):
        account = st.text_input('研究帳號', placeholder='例如 ycc00000001')
        password = st.text_input('研究密碼', type='password')
        submitted = st.form_submit_button('核對帳號', type='primary')
    if submitted:
        st.session_state.pop('_line_confirm_url', None)
        endpoint = setting('NSYSU_LINE_FUNCTION_URL')
        if not endpoint:
            base = setting('SUPABASE_URL').rstrip('/')
            endpoint = base + '/functions/v1/nsysu-line'
        parsed = urlsplit(endpoint)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            st.error('雲端綁定服務尚未完成設定，請聯絡研究團隊。')
            return
        try:
            response = requests.post(endpoint.rstrip('/') + '/prepare-link',
                                     json={'link_token': token, 'account': account.strip(), 'password': password},
                                     timeout=20, allow_redirects=False)
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError('Invalid cloud response')
            if not response.ok:
                st.error(value.get('error', '綁定尚未完成，請回到 LINE 重新開始。'))
                return
            target = urlsplit(value.get('link_url', ''))
            if value.get('status') != 'pending_line_confirmation' or target.scheme != 'https' or target.netloc != 'access.line.me' or target.path != '/dialog/bot/accountLink':
                raise ValueError('Invalid confirmation response')
            st.session_state['_line_confirm_url'] = value['link_url']
        except (requests.RequestException, ValueError, TypeError):
            st.error('連線未完成，尚未確認綁定成功。請回到 LINE 稍後重試。')
            return
    if st.session_state.get('_line_confirm_url'):
        st.info('帳密已核對。請點下方按鈕，在 LINE 完成最後確認。成功後聊天室會顯示首次提醒時間。')
        st.link_button('回 LINE 完成綁定', st.session_state['_line_confirm_url'], type='primary')
    st.caption('這是研究帳號核對與 LINE 綁定，不代表 Docter+ 官方登入。可隨時從聊天室選單取消綁定。')
