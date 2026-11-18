"""Task-first dashboard flow: connect, select context, load, then analyze/manage."""
from datetime import datetime, time, timedelta, date
import re
from urllib.parse import urlencode

import pandas as pd
import requests
import streamlit as st

from .dashboard import objective_view, physiology_view, stress_view, filter_diaries, BOOLS
from .dashboard_summary import overview_view, category_view
from .parsers import docter_sleep, docter_metrics, parse_sleep_file, canonical_metrics
from .platform import Platform
from .platform_data import combine_participants, load_platform_bundle, merge_records, diary_member
from .platform_view import all_platform_view
from .sleep import TZ, sleep_metrics
from .sleep_parameters_view import sleep_parameters_view
from .store import Store, StoreError, login
from .config import setting

PLATFORM = "手錶平台"
RESEARCH = "睡眠日誌與研究資料"


def diary_url(member=None, history=False):
    if st.session_state.get('_nsysu_cloud'):
        from .cloud import app_url
        base = app_url()
    else:
        base = setting("VTCA_DIARY_URL", "http://127.0.0.1:8000/")
    params = {}
    if member:
        params["member"] = member
    if history:
        params["view"] = "history"
    return base + (("&" if "?" in base else "?") + urlencode(params) if params else "")


def clear_workspace():
    for key in ("dashboard_data", "flow_platform_members", "platform_connection_error", "dashboard_tabs", "measurement_category"):
        st.session_state.pop(key, None)


def research_store():
    saved = st.session_state.get("supabase_session")
    if not saved:
        return None
    if saved.get("expires_at", 0) < datetime.now(TZ).timestamp() + 30:
        try:
            saved = Store().request("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": saved["refresh_token"]})
        except StoreError as error:
            if error.status in (401, 403):
                deny_research_access()
            raise
        st.session_state.supabase_session = saved
    store = Store(saved['access_token'])
    try:
        store.user()
    except StoreError as error:
        if error.status in (401, 403):
            deny_research_access()
        raise
    require_research_access(store)
    return store


def require_research_access(store):
    try:
        allowed = store.request('POST', '/rest/v1/rpc/diary_staff_status', {})
    except StoreError as error:
        if error.status not in (401, 403):
            raise
        allowed = False
    if allowed is not True:
        deny_research_access()


def deny_research_access():
    st.session_state.pop('supabase_session', None)
    st.session_state['_auth_clear'] = True
    st.session_state.pop('platform_token', None)
    clear_workspace()
    raise PermissionError('管理權限已變更，請重新登入')


def connected(mode):
    return bool(st.session_state.get("platform_token" if mode == PLATFORM else "supabase_session"))


def login_panel(mode):
    platform = mode == PLATFORM
    st.subheader("連接 DocterCloud" if platform else "管理者登入")
    st.write("請輸入已授權的 DocterCloud 帳密，以查看即時平台資料。" if platform else "登入後可使用管理工作區、受試者日誌 QR Code 與已授權研究資料。")
    with st.form("platform_login" if platform else "research_login"):
        account = st.text_input("平台帳號" if platform else "管理者帳號")
        password = st.text_input("平台密碼" if platform else "管理者密碼", type="password")
        submitted = st.form_submit_button("連接 DocterCloud" if platform else "登入管理工作區", type="primary")
    if submitted:
        if not account.strip() or not password:
            st.error("請填寫帳號與密碼。")
            return
        try:
            with st.spinner("正在確認登入…"):
                if platform:
                    st.session_state.platform_token = Platform().login(account, password)["access_token"]
                else:
                    st.session_state.supabase_session = login(account, password)
                    st.session_state.pop('_auth_clear', None)
                    research_store()
            clear_workspace()
            st.rerun()
        except Exception:
            st.error("登入未成功，請確認帳密、管理權限與連線。")
    if not platform:
        st.caption("DocterCloud 資料授權另行連接；管理者帳密不會傳送至手錶平台。")


def participants_for(mode, store):
    if mode == RESEARCH:
        rows = store.rows('research_participants') if store else []
        if connected(PLATFORM):
            try:
                return combine_participants(rows, participants_for(PLATFORM, store))
            except Exception:
                st.session_state.platform_connection_error = '平台會員清單未載入，先顯示已授權的日誌受試者。'
        return rows
    if "flow_platform_members" not in st.session_state:
        with st.spinner("正在讀取可查看的受試者…"):
            st.session_state.flow_platform_members = Platform(st.session_state.platform_token).members("ycc")
    return st.session_state.flow_platform_members


def member_key(row):
    return row.get("member_id") or row.get("identifier") or str(row["id"])


def member_label(row):
    key = member_key(row)
    profile = row.get('platform_profile') or {}
    label = row.get('display_name') or row.get('name') or profile.get('name')
    return f'{key} · {label}' if label and label != key else key


def load_records(mode, target, start_date, end_date, store):
    member = member_key(target)
    research_access = mode == RESEARCH and store is not None
    bundle = None
    if mode == RESEARCH:
        if store is None:
            raise ValueError("請先登入研究資料。")
        require_research_access(store)
        diaries = store.rows("sleep_logs", member_id="eq." + member, date="gte." + str(start_date), **{"and": f"(date.lte.{end_date})"}) if diary_member(member) else []
        sessions = store.rows("sleep_sessions", member_id="eq." + member, sleep_date="gte." + str(start_date), **{"and": f"(sleep_date.lte.{end_date})"})
        metrics = store.rows("physiological_metrics", member_id="eq." + member, measured_at="gte." + datetime.combine(start_date, time.min, TZ).isoformat(), **{"and": "(measured_at.lt." + datetime.combine(end_date + timedelta(days=1), time.min, TZ).isoformat() + ")"})
        imports = store.rows("data_imports", member_id="eq." + member)
        if target.get('platform_mapping_error'):
            st.session_state.platform_connection_error = '平台會員編號重複或與已設定對應不一致，未混入平台紀錄，請核對會員資料。'
        elif target.get('platform_profile') and connected(PLATFORM):
            bundle = load_platform_bundle(st.session_state.platform_token, target['platform_profile'], start_date, end_date)
            sessions = merge_records(sessions, bundle['sessions'])
            metrics = merge_records(metrics, bundle['metrics'], metric=True)
    else:
        bundle = load_platform_bundle(st.session_state.platform_token, target, start_date, end_date)
        sessions, metrics = bundle['sessions'], bundle['metrics']
        diaries, imports = [], []
        if store and member.startswith("ycc"):
            research_access = bool(store.rows("participant_access", member_id="eq." + member))
            if research_access:
                diaries = store.rows("sleep_logs", member_id="eq." + member, date="gte." + str(start_date), **{"and": f"(date.lte.{end_date})"})
    context = (bundle or {}).get('pre_sleep_context', [])
    context_status = (bundle or {}).get('pre_sleep_context_status', 'success')
    if research_access:
        try:
            previous = store.rows('physiological_metrics', member_id='eq.' + member, metric='in.(stress,fatigue)',
                                  measured_at='gte.' + datetime.combine(start_date - timedelta(days=2), time.min, TZ).isoformat(),
                                  **{'and': '(measured_at.lt.' + datetime.combine(start_date, time.min, TZ).isoformat() + ')'})
            context = merge_records(previous, context, metric=True)
        except (StoreError, requests.RequestException) as error:
            if isinstance(error, StoreError) and error.status in (401, 403):
                raise
            context_status = 'partial'
    return {"mode": mode, "member": member, "label": member_label(target), "start": str(start_date), "end": str(end_date),
            "diaries": diaries, "sessions": sessions, "metrics": metrics, "imports": imports, "platform_bundle": bundle,
            "pre_sleep_context": context, "pre_sleep_context_status": context_status,
            "loaded_at": datetime.now(TZ).isoformat(), "analysis_loaded": True, "research_access": research_access}


def diary_view(diaries, member, has_research_access):
    st.subheader("睡眠日誌")
    st.caption("自行填寫的主觀紀錄；與手錶量測分開保存。")
    if not diary_member(member):
        st.info('這位平台會員尚未對應日誌編號，平台原始資料仍可完整查看。')
        return
    cols = st.columns(2)
    cols[0].link_button("填寫這位受試者的日誌", diary_url(member))
    cols[1].link_button("查看／修改歷史紀錄", diary_url(member, history=True))
    if not has_research_access:
        st.info("這位受試者的日誌尚未連接或未授權。查看歷史需要使用研究團隊開通的日誌帳號。")
    elif not diaries:
        st.info("這段期間沒有可查看的日誌。可調整日期，或填寫新的日誌。")
    else:
        def boolean(value):
            return "是" if value is True else "否" if value is False else "未填／不確定"
        display = [{"日期": r["date"], "上床": str(r["bedtime"])[:5] if r.get("bedtime") else "待確認",
                    "開始嘗試入睡": str(r["lights_out_time"])[:5] if r.get("lights_out_time") else "未填",
                    "最後醒來": str(r.get("final_wake_time") or r["morning_wake_time"])[:5],
                    "離床": str(r.get("out_of_bed_time") or r["wake_time"])[:5], "主觀入睡分鐘": r["sleep_onset_min"],
                    "配戴手錶": boolean(r.get("wore_watch")), "助眠藥物": boolean(r.get("sleep_medication")), "飲酒": boolean(r.get("drank_alcohol")),
                    "日期狀態": "已確認" if r.get("date_definition") == "wake_date" else "舊日期待確認"} for r in diaries]
        st.dataframe(pd.DataFrame(display), hide_index=True, use_container_width=True)


def comparison_view(diaries, sessions):
    st.subheader("研究資料比較")
    with st.expander("依研究問項篩選"):
        cols = st.columns(3)
        factors = {key: BOOLS[col.selectbox(label, list(BOOLS))] for col, (key, label) in zip(cols, (("wore_watch", "手錶配戴"), ("sleep_medication", "助眠藥物"), ("drank_alcohol", "飲酒")))}
    rows = []
    for diary in filter_diaries(diaries, factors):
        matched = [s for s in sessions if diary.get("date_definition") == "wake_date" and s["sleep_date"] == diary["date"]]
        for session in matched or [{}]:
            rows.append({"受試者": diary["member_id"], "日期": diary["date"], "日誌 ID": diary["id"], "主觀 SOL 分鐘": diary["sleep_onset_min"],
                         "配戴手錶": diary.get("wore_watch"), "助眠藥物": diary.get("sleep_medication"), "飲酒": diary.get("drank_alcohol"),
                         "客觀來源": session.get("source"), "Session": session.get("external_session_id"), **sleep_metrics(diary, session)})
    if not rows:
        st.info("目前沒有符合條件的日誌比較資料。請確認日期、研究問項及日誌存取權限。")
        return
    st.caption("同日多筆日誌分列呈現；舊日期待確認者不自動配對。問項篩選只影響這張比較表。")
    frame = pd.DataFrame(rows)
    st.dataframe(frame, hide_index=True, use_container_width=True)
    st.download_button("下載比較 CSV", frame.to_csv(index=False).encode("utf-8-sig"), "research_comparison.csv", mime="text/csv")


def import_success(result):
    st.success(f"已儲存 {result.get('sessions', 0)} 份睡眠紀錄、{result.get('metrics', 0)} 筆生理指標。可回到「查看資料」重新載入。")


def data_manager(data, store):
    st.subheader("資料匯入與同步")
    member = data["member"]
    st.write(f"資料將儲存到受試者 {member}，查詢日期 {data['start']} 至 {data['end']}。")
    if store is None:
        st.info("查看手錶資料無需額外登入；若要保存或匯入，請先登入日誌與研究資料。")
        login_panel(RESEARCH)
        return
    grants = store.rows("participant_access", member_id="eq." + member)
    if not any(g.get("can_write") for g in grants):
        st.info("這個帳號沒有此受試者的寫入權限，請聯絡研究團隊開通。")
        return
    method = st.radio("資料取得方式", ["從手錶平台同步", "匯入已授權檔案"], horizontal=True)
    if method == "從手錶平台同步":
        if not connected(PLATFORM):
            login_panel(PLATFORM)
            return
        st.caption("只儲存平台確實提供的資料，重複同步會更新同一筆紀錄。")
        if st.button("同步並儲存這段期間", type="primary"):
            try:
                mapping = store.rows("research_participants", member_id="eq." + member)
                external_id = mapping[0].get("platform_user_id") if mapping else None
                if external_id is None:
                    raise ValueError("尚未完成平台會員對應，請聯絡研究團隊核對。")
                start = date.fromisoformat(data["start"])
                end = date.fromisoformat(data["end"])
                lower = int(datetime.combine(start - timedelta(days=1), time.min, TZ).timestamp())
                upper = int(datetime.combine(end + timedelta(days=1), time.min, TZ).timestamp())
                with st.spinner("正在取得並核對平台資料…"):
                    platform = Platform(st.session_state.platform_token)
                    raw = {kind: platform.fetch(kind, external_id, lower, upper) for kind in ("sleep", "hrv", "heart/rate")}
                    sessions = [docter_sleep(r) for r in raw["sleep"]]
                    metrics = docter_metrics(raw["hrv"]) + docter_metrics(raw["heart/rate"], "hr")
                    if not sessions and not metrics:
                        st.info("平台沒有提供這段期間的資料，沒有新增紀錄。")
                    else:
                        import_success(store.import_data(member, "doctercloud", sessions, metrics, raw))
            except Exception as error:
                st.error(f"這次同步未完成：{error}")
                try:
                    store.record_failure(member, "doctercloud", {"operation": "sync", "start": data["start"], "end": data["end"]}, str(error))
                except Exception:
                    st.caption("也無法寫入失敗紀錄，請檢查連線。")
    else:
        kind = st.selectbox("檔案內容", ["睡眠紀錄", "生理指標"])
        label = st.selectbox("檔案格式", ["手錶平台原始 JSON", "標準 JSON／CSV"] if kind == "睡眠紀錄" else ["標準 JSON／CSV"])
        adapter = "doctercloud_v5_4" if label == "手錶平台原始 JSON" else "canonical"
        source = "doctercloud"
        if adapter == "canonical":
            with st.expander("來源設定", expanded=True):
                source = st.text_input("固定來源代碼", value="authorized_export", help="同一個平台請固定使用同一代碼，避免重複匯入時混用來源。")
        uploaded = st.file_uploader("選擇已授權 JSON 或 CSV（最多 8 MB）", type=["json", "csv"])
        if st.button("核對並匯入", type="primary", disabled=uploaded is None):
            try:
                if uploaded is None:
                    return
                content = uploaded.getvalue()
                if len(content) > 8 * 1024 * 1024 or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,63}", source):
                    raise ValueError("檔案過大或來源代碼格式不正確。")
                file_format = uploaded.name.rsplit(".", 1)[-1]
                sessions = parse_sleep_file(content, file_format, adapter) if kind == "睡眠紀錄" else []
                metrics = canonical_metrics(content, file_format) if kind == "生理指標" else []
                import_success(store.import_data(member, source, sessions, metrics, content.decode("utf-8-sig")))
            except Exception as error:
                st.error(f"檔案尚未匯入：{error}")
                try:
                    store.record_failure(member, source, uploaded.name if uploaded else "file", str(error))
                except Exception:
                    st.caption("也無法寫入失敗紀錄，請檢查連線。")
    with st.expander("最近的同步紀錄"):
        imports = store.rows("data_imports", member_id="eq." + member)
        if not imports:
            st.caption("尚無同步紀錄。")
        else:
            st.dataframe(pd.DataFrame([{"時間": datetime.fromisoformat(r["imported_at"]).astimezone(TZ).strftime("%Y-%m-%d %H:%M"), "來源": r["source"], "狀態": "完成" if r["status"] == "success" else "未完成", "睡眠紀錄": r.get("session_count", 0), "生理指標": r.get("metric_count", 0), "訊息": r.get("error_message") or ""} for r in imports]), hide_index=True)


def main(configure_page=True):
    if configure_page:
        st.set_page_config(page_title="睡眠與生理研究", page_icon="🌙", layout="wide")
    st.markdown("""<style>
    .stApp{background:#f5f7fb}h1,h2,h3{color:#213e53}
    .block-container{max-width:1520px;padding-top:1.6rem}
    h1{font-size:2rem!important}
    section[data-testid='stSidebar']{background:#fff;border-right:1px solid #e3eaf0}
    div[data-testid='stVerticalBlockBorderWrapper']{border-color:#e1e8ef;background:#fff;border-radius:12px}
    div[data-testid='stMetric']{padding:8px 0;background:transparent}
    div[data-testid='stMetricValue']{font-size:1.65rem;color:#18394b}
    div[data-testid='stMetricLabel']{color:#567084}
    div[class*='st-key-summary-']{border-top:3px solid #00a3ac;min-height:200px;background:white}
    .st-key-sleep-platform-summary{background:white}
    .st-key-sleep-platform-summary [data-testid='stMetricValue']{color:#397e73;font-size:1.9rem}
    button[data-testid='stBaseButton-primary']{background:#009eaa;border-color:#009eaa}
    button[role='tab'][aria-selected='true']{color:#008c97}
    div[data-testid='stForm']{background:white}
    @media(max-width:640px){.block-container{padding:1.4rem 1rem}div[class*='st-key-summary-']{min-height:0}}
    </style>""", unsafe_allow_html=True)
    from .apple_theme import apply as apply_apple_theme
    apply_apple_theme()
    from .auth_bridge import home_link, synchronize
    if not synchronize(diary_url()):
        return
    st.title("睡眠與生理研究")
    st.caption("受試者健康總覽 · 生理量測 · 睡眠分析")
    st.sidebar.title("研究工作區")
    with st.sidebar:
        home_link(diary_url())
    mode = st.sidebar.radio("我要查看", [RESEARCH, PLATFORM], index=0, key="flow_mode")
    workspace = st.sidebar.radio("功能", ["查看資料", "資料管理"], key="workspace_page")
    if not connected(mode):
        st.markdown("### 先連接你要查看的資料")
        login_panel(mode)
        return
    st.sidebar.success("手錶平台已連接" if mode == PLATFORM else "管理者已登入")
    if st.sidebar.button("登出目前資料來源"):
        if mode == PLATFORM:
            st.session_state.pop("platform_token", None)
        else:
            st.session_state["_auth_clear"] = True
            saved = st.session_state.pop("supabase_session")
            st.session_state.pop('platform_token', None)
            try:
                Store(saved["access_token"]).request("POST", "/auth/v1/logout?scope=local")
            except Exception:
                pass
        clear_workspace()
        st.rerun()
    try:
        store = research_store()
        participants = participants_for(mode, store)
    except PermissionError:
        st.rerun()
    except Exception:
        st.error("暫時無法讀取受試者清單。請確認連線，必要時登出後重新登入。")
        return
    if not participants:
        st.info("目前帳號尚未取得受試者資料。請聯絡研究團隊確認授權。")
        return
    if mode == RESEARCH and not connected(PLATFORM) and workspace == '查看資料':
        st.info(st.session_state.get('platform_connection_error') or 'DocterCloud 尚未連線；既有日誌與研究資料仍可查看。')
        with st.expander('重新連接 DocterCloud'):
            login_panel(PLATFORM)
    choices = {member_key(row): row for row in participants}
    st.markdown("##### 選擇受試者與查詢日期")
    cols = st.columns([1.3, 1])
    selected_key = "subject_" + mode
    incoming = st.query_params.get('member')
    if selected_key not in st.session_state and incoming in choices:
        st.session_state[selected_key] = incoming
    member = cols[0].selectbox("選擇受試者", list(choices), index=0 if len(choices) == 1 else None, format_func=lambda key: member_label(choices[key]), placeholder="輸入或選擇受試者編號", key="subject_" + mode)
    retained = st.session_state.get('_research_context', {})
    if member:
        st.query_params['member'] = member
    periods = ["近 7 天", "近 30 天", "自訂"]
    period = cols[1].radio("日期範圍", periods, index=periods.index(retained.get('period', '近 7 天')), horizontal=True)
    today = datetime.now(TZ).date()
    if period == "自訂":
        cols = st.columns(2)
        start = cols[0].date_input("開始日期", today - timedelta(days=6))
        end = cols[1].date_input("結束日期", today)
    else:
        end, start = today, today - timedelta(days=6 if period == "近 7 天" else 29)
        st.caption(f"{start} 至 {end} · 台灣時間")
    st.session_state['_research_context'] = {'member': member, 'period': period, 'start': str(start), 'end': str(end)}
    if end < start:
        st.error("結束日期不能早於開始日期。")
        return
    requested = st.button("開啟資料管理" if workspace == "資料管理" else "查看資料", type="primary", disabled=member is None)
    data = st.session_state.get("dashboard_data")
    context = (mode, member, str(start), str(end))
    matched = data and (data["mode"], data["member"], data["start"], data["end"]) == context and (workspace == "資料管理" or data.get("analysis_loaded", True))
    if requested:
        try:
            with st.spinner("正在載入資料…"):
                data = ({"mode": mode, "member": member, "label": member_label(choices[member]), "start": str(start), "end": str(end), "loaded_at": datetime.now(TZ).isoformat(), "analysis_loaded": False} if workspace == "資料管理" else load_records(mode, choices[member], start, end, store))
            st.session_state.dashboard_data = data
            st.session_state.dashboard_tabs = '健康總覽'
            matched = True
        except Exception as error:
            st.error(f"這次資料尚未載入：{error}")
            return
    if not matched or data is None:
        st.info("選好受試者與日期後，按「查看資料」。" if data is None else "選項已變更，按「查看資料」更新結果。")
        return
    st.markdown('#### ' + data["label"])
    st.caption(f"目前顯示：{data['start']} 至 {data['end']} · {mode} · 更新於 {datetime.fromisoformat(data['loaded_at']).astimezone(TZ).strftime('%H:%M')}")
    if workspace == "資料管理":
        data_manager(data, store)
        return
    sessions, metrics, diaries = data["sessions"], data["metrics"], data["diaries"]
    pre_context = data.get('pre_sleep_context', [])
    with st.expander("進階篩選：來源與裝置"):
        sources = sorted({s["source"] for s in sessions} | {m.get("source", "unknown") for m in metrics + pre_context})
        selected_sources = st.multiselect("裝置／平台來源", sources, default=sources)
        devices = sorted({s.get("device_external_id") or "未提供" for s in sessions} | {m.get("device_external_id") or "未提供" for m in metrics + pre_context})
        selected_devices = st.multiselect("裝置識別", devices, default=devices)
    sessions = [s for s in sessions if s["source"] in selected_sources and (s.get("device_external_id") or "未提供") in selected_devices]
    metrics = [m for m in metrics if m.get("source", "unknown") in selected_sources and (m.get("device_external_id") or "未提供") in selected_devices]
    pre_context = [m for m in pre_context if m.get('source', 'unknown') in selected_sources and (m.get('device_external_id') or '未提供') in selected_devices]
    labels = ["健康總覽", "生理數據", "睡眠分析", "睡眠參數", "睡眠日誌", "壓力與疲倦", "研究比較", "原始資料／下載"]
    tabs = st.tabs(labels, default=labels[0], key='dashboard_tabs', on_change='rerun')
    with tabs[0]:
        overview_view(sessions, metrics, diaries, data.get('platform_bundle'))
    with tabs[1]:
        category_view(metrics)
    with tabs[2]:
        objective_view(sessions, diaries, metrics)
    with tabs[3]:
        sleep_parameters_view(sessions, diaries, metrics + pre_context, data.get('pre_sleep_context_status', 'not_loaded'))
    with tabs[4]:
        diary_view(diaries, member, data.get("research_access", False))
    with tabs[5]:
        stress_view(metrics)
    with tabs[6]:
        comparison_view(diaries, sessions)
        with st.expander('進階指標比較：雙軸／標準化'):
            physiology_view(metrics)
    with tabs[7]:
        all_platform_view(data.get('platform_bundle'), st.session_state.get('platform_connection_error'))
        with st.expander("查看睡眠來源與品質詳情"):
            st.dataframe(pd.DataFrame([{k: s.get(k) for k in ("sleep_date", "source", "device_external_id", "algorithm_version", "quality_status")} for s in sessions]), hide_index=True)
    auto = st.sidebar.checkbox("自動更新（每 30 秒）", value=False)

    @st.fragment(run_every=30 if auto else None)
    def refresh_clock():
        now = datetime.now(TZ).timestamp()
        last = st.session_state.setdefault("flow_refresh_tick", now)
        if auto and now - last >= 29:
            st.session_state.flow_refresh_tick = now
            try:
                current_store = research_store() if mode == RESEARCH else store
                st.session_state.dashboard_data = load_records(mode, choices[member], start, end, current_store)
                st.rerun()
            except PermissionError:
                st.rerun()
            except Exception:
                st.warning("本次自動更新未完成，先保留上次的資料。")
    refresh_clock()
