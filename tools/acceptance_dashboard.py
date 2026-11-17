"""Real dashboard renderer, explicit isolated HTTP provider."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
if os.environ.get('NSYSU_ACCEPTANCE_MODE') != '1':
    raise RuntimeError('Explicit local acceptance mode required')

import streamlit as st
from nsysu import dashboard_flow as flow
from nsysu.acceptance_adapter import AcceptanceStore
from nsysu.store import diary_email

class DisabledPlatform:
    def __init__(self, *args, **kwargs):
        pass

    def login(self, *args, **kwargs):
        raise RuntimeError('DocterCloud is disabled in isolated acceptance')

    def members(self, *args, **kwargs):
        raise RuntimeError('DocterCloud is disabled in isolated acceptance')


flow.Platform = DisabledPlatform
flow.Store = AcceptanceStore
flow.login = lambda account, password: AcceptanceStore().request('POST', '/auth/v1/token?grant_type=password',
                                                               {'email': diary_email(account), 'password': password})
st.set_page_config(page_title='研究資料｜隔離驗收', layout='wide')
st.warning('隔離驗收模式：合成研究資料，不連接正式資料或 DocterCloud。')
flow.main(configure_page=False)
