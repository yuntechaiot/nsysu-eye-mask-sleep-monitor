"""單一 Streamlit 網址：保留最新日誌 HTML 與研究 Dashboard。"""
import json
import re
from urllib.parse import urlencode

from .config import ROOT, public_url
from .store import settings


def app_url():
    import streamlit as st
    try:
        current = st.context.url
    except (AttributeError, RuntimeError):
        current = None
    return public_url(current)


def public_config(base):
    url, key = settings()
    from .reminder_routes import public_line_info
    return {'line': public_line_info(), 'supabase_url': url, 'publishable_key': key, 'timezone': 'Asia/Taipei',
            'diary_url': base, 'dashboard_url': base + ('&' if '?' in base else '?') + 'view=dashboard'}


def diary_document(config, query=None):
    """只嵌入版本控制內的固定 HTML／assets；動態資料以安全 JSON 序列化。"""
    query = query or {}
    allowed = {}
    member = str(query.get('member', '')).strip().lower()
    if member:
        if not re.fullmatch(r'ycc[0-9]{8}', member):
            raise ValueError('無效的受試者連結，請重新掃描研究團隊提供的 QR Code')
        allowed['member'] = member
    invite = str(query.get('invite', ''))
    if invite:
        if not member or not re.fullmatch(r'[a-f0-9]{64}', invite):
            raise ValueError('無效的填寫連結，請使用研究團隊提供的完整 QR Code')
        allowed['invite'] = invite
    view = query.get('view')
    if view in {'history', 'members', 'start', 'diary', 'submitted', 'workspace', 'qr'}:
        allowed['view'] = view
    target = str(query.get('date', ''))
    if target:
        from datetime import date
        date.fromisoformat(target)
        allowed['date'] = target
    html = (ROOT / 'frontend/source/睡眠日誌表單.html').read_text(encoding='utf-8')
    html = re.sub(r'<script src="/web/[^\"]+" defer></script>', '', html)
    css = '\n'.join((ROOT / 'frontend/web' / name).read_text(encoding='utf-8')
                    for name in ['app.css', 'apple.css', 'responsive.css'])
    html = html.replace('<link rel="stylesheet" href="/web/app.css">', '<style>' + css + '</style>')
    html = html.replace('<link rel="stylesheet" href="/web/apple.css">', '')
    html = html.replace('<link rel="stylesheet" href="/web/responsive.css">', '')
    boot = json.dumps({'config': config, 'initial_query': urlencode(allowed)}, ensure_ascii=False)
    boot = boot.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    scripts = ['<script>window.NSYSU_EMBED=' + boot + ';</script>']
    for name in ['core.js', 'cloud-transport.js', 'qrcode.min.js', 'participants.js', 'invitations.js', 'management.js', 'history.js', 'diary.js', 'apple-motion.js', 'mobile-ui.js', 'workspace.js']:
        code = (ROOT / 'frontend/web' / name).read_text(encoding='utf-8')
        scripts.append('<script>' + code.replace('</script', '<\\/script') + '</script>')
    return html.replace('</body>', '\n'.join(scripts) + '</body>')


def main():
    import streamlit as st
    import streamlit.components.v1 as components

    st.set_page_config(page_title='nsysu-eye-mask-sleep-monitor', page_icon='🌙', layout='wide')
    st.session_state['_nsysu_cloud'] = True
    if st.query_params.get('view') == 'line':
        from .cloud_line_page import main as binding
        binding()
        return
    if st.query_params.get('view') == 'dashboard':
        from .dashboard_flow import main as dashboard
        dashboard(configure_page=False)
        return
    try:
        config = public_config(app_url())
        document = diary_document(config, st.query_params.to_dict())
    except ValueError as error:
        st.error(str(error))
        return
    st.markdown('''<style>
    .stApp{background:#f5f5f7}
    .block-container{padding:3.5rem 0 0;max-width:1200px}
    [data-testid="stHeader"]{background:rgba(245,245,247,.9)}
    [data-testid="stIFrame"]{border:0;display:block}
    @media(max-width:767px){
      [data-testid="stHeader"]{min-height:calc(3.5rem + env(safe-area-inset-top,0px));padding-top:env(safe-area-inset-top,0px)}
      .block-container{padding:calc(4rem + env(safe-area-inset-top,0px)) env(safe-area-inset-right,0px) env(safe-area-inset-bottom,0px) env(safe-area-inset-left,0px)!important;min-width:0}
      [data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]{gap:0}
      [data-testid="stElementContainer"]:has(>[data-testid="stIFrame"]){height:calc(100dvh - 4rem - env(safe-area-inset-top,0px) - env(safe-area-inset-bottom,0px))!important;min-height:0!important;flex:0 0 auto!important}
      [data-testid="stIFrame"]{width:100%;height:calc(100dvh - 4rem - env(safe-area-inset-top,0px) - env(safe-area-inset-bottom,0px))}
    }
    </style>''', unsafe_allow_html=True)
    # iframe 只包含本專案固定 HTML，不嵌入使用者 HTML。
    components.html(document, height=1150, scrolling=True, tab_index=0)
