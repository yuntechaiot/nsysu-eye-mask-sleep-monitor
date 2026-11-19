"""Dedicated cloud Account Linking page; no local listener or LIFF iframe."""
import hashlib
from html import escape
import re
from urllib.parse import parse_qs, urlsplit

import requests
import streamlit as st

from .config import setting


def confirmation_link(value, token):
    """Keep the official confirmation in the current LINE browser, without a popup."""
    url = value.get('link_url')
    if not isinstance(url, str):
        raise ValueError('Invalid confirmation response')
    target = urlsplit(url)
    params = parse_qs(target.query, keep_blank_values=True)
    if (value.get('status') != 'pending_line_confirmation' or target.scheme != 'https'
            or target.netloc != 'access.line.me' or target.path != '/dialog/bot/accountLink'
            or target.fragment or set(params) != {'linkToken', 'nonce'}
            or params['linkToken'] != [token] or len(params['nonce']) != 1
            or not re.fullmatch(r'[a-f0-9]{64}', params['nonce'][0])):
        raise ValueError('Invalid confirmation response')
    return value['link_url']


def confirmation_button(url):
    # st.link_button always opens a new tab; a normal user-activated same-tab link
    # also works in in-app browsers that cannot create a separate window.
    return '''<style>
    .line-confirm-button{display:inline-flex;align-items:center;justify-content:center;
    min-height:48px;box-sizing:border-box;max-width:100%;padding:.75rem 1.25rem;
    border-radius:.65rem;background:#0066cc;color:#fff!important;text-decoration:none;
    font:600 1rem/1.5 sans-serif;touch-action:manipulation}
    .line-confirm-button:focus-visible{outline:3px solid #0066cc;outline-offset:4px}
    @media(max-width:600px){.line-confirm-button{width:100%}}
    </style><a class="line-confirm-button" href="''' + escape(url, quote=True) + '''"
    target="_self" rel="noreferrer" referrerpolicy="no-referrer">回 LINE 完成綁定</a>'''


def binding_status(message, *, confirmation=None):
    """One HTML element swaps the pending state and handoff without stale children."""
    content = '<p class="line-binding-status" role="status">' + escape(message) + '</p>'
    if confirmation:
        content += confirmation_button(confirmation)
        content += '<p class="line-binding-help">請用收到綁定訊息的同一個手機 LINE 帳號完成確認。若沒有開啟，請回官方聊天室重新點「開始綁定」取得新連結。</p>'
    return '''<style>.line-binding-status{padding:1rem;border-radius:.65rem;
    background:#eaf3ff;color:#154a74;font:1rem/1.8 sans-serif;overflow-wrap:anywhere}
    .line-binding-help{color:#626772;font:.875rem/1.8 sans-serif;margin-top:1rem}</style>''' + content


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
    confirmation_area = st.empty()
    waiting = confirmation_area
    if submitted:
        st.session_state.pop('_line_confirm_url', None)
        confirmation_area.empty()
        endpoint = setting('NSYSU_LINE_FUNCTION_URL')
        if not endpoint:
            base = setting('SUPABASE_URL').rstrip('/')
            endpoint = base + '/functions/v1/nsysu-line'
        parsed = urlsplit(endpoint)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            st.error('雲端綁定服務尚未完成設定，請聯絡研究團隊。')
            return
        waiting.html(binding_status('正在核對研究帳號，請稍候…請勿重複送出。'))
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
            st.session_state['_line_confirm_url'] = confirmation_link(value, token)
        except (requests.RequestException, ValueError, TypeError):
            st.error('連線未完成，尚未確認綁定成功。請回到 LINE 稍後重試。')
            return
        finally:
            waiting.empty()
    if st.session_state.get('_line_confirm_url'):
        confirmation_area.html(binding_status('帳密已核對。請點下方按鈕，在 LINE 完成最後確認。成功後聊天室會顯示首次提醒時間。',
                                              confirmation=st.session_state['_line_confirm_url']))
    st.caption('這是研究帳號核對與 LINE 綁定，不代表 Docter+ 官方登入。可隨時從聊天室選單取消綁定。')
