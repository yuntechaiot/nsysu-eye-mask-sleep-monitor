"""Run with Streamlit: the existing LINE page, loopback-only synthetic verification.

The confirmation button leads to a local receipt, never to LINE.
"""
from pathlib import Path
import sys
from time import sleep

import requests
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from nsysu import cloud_line_page as page  # noqa: E402 -- standalone repository entry

st.set_page_config(page_title='LINE 綁定・本機驗收', page_icon='🧪')
st.secrets = {}


def no_external_request(*args, **kwargs):
    raise RuntimeError('External requests are disabled in the isolated preview')


requests.sessions.Session.request = no_external_request
st.warning('隔離本機驗收：只使用測試帳密，不連接 LINE、不變更綁定、不發送訊息。')
if st.query_params.get('preview_complete') == '1':
    st.success('已在同一分頁開啟本機確認示範。這不是正式 LINE 綁定成功。')
    st.link_button('重新測試', '?view=line')
else:
    st.caption('這是導頁示範，兩個帳密欄位留空即可模擬核對。請勿輸入真實帳密。核對會等待約 4 秒；確認按鈕只開啟本機示範。')
    st.query_params['link_token'] = 'SYNTHETIC_LOCAL_LINK'
    scenario = st.selectbox('模擬服務回應', ['正常核對', '服務無法連線'])
    slow = st.checkbox('慢速回應（15 秒，方便查看等待提示）')

    class Reply:
        def __init__(self, ok):
            self.ok = ok
        def json(self):
            if not self.ok:
                return {'error': '本機導頁示範請將兩個帳密欄位留空，不需要輸入真實帳密。'}
            return {'status': 'pending_line_confirmation', 'link_url':
                    'https://access.line.me/dialog/bot/accountLink?linkToken=SYNTHETIC_LOCAL_LINK&nonce=' + 'c' * 64}

    def prepare(url, *, json, **kwargs):
        if url != 'https://synthetic.invalid/prepare-link':
            raise RuntimeError('Unexpected synthetic endpoint')
        sleep(15 if slow else 4)
        if scenario == '服務無法連線':
            raise requests.Timeout('SYNTHETIC_TIMEOUT')
        return Reply(not json.get('account') and not json.get('password'))

    # These substitutions run only in this dedicated preview process.
    page.setting = lambda name: 'https://synthetic.invalid' if name == 'NSYSU_LINE_FUNCTION_URL' else ''
    page.requests.post = prepare
    if not hasattr(page, '_preview_confirmation_button'):
        page._preview_confirmation_button = page.confirmation_button
    page.confirmation_button = lambda url: page._preview_confirmation_button('?preview_complete=1')
    page.main()
