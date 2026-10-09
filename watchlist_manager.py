import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# 認証設定のキャッシュ化（不要な再接続を防ぎ高速化）
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    service_account_info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    return gspread.authorize(creds)

def get_watchlist_worksheet():
    """Secretsで指定されたスプレッドシートの1シート目を取得"""
    sheet_id = st.secrets.get("WATCHLIST_SPREADSHEET_ID")
    if not sheet_id:
        return None
    gc = get_gspread_client()
    sh = gc.open_by_key(sheet_id)
    return sh.get_worksheet(0)

def load_watchlist_from_sheet():
    """スプレッドシートからウォッチリストを取得"""
    try:
        ws = get_watchlist_worksheet()
        if not ws:
            return []
        records = ws.get_all_records()
        
        watchlist = []
        for r in records:
            c = str(r.get("code", "")).strip().upper()
            n = str(r.get("name", "")).strip()
            if c:
                watchlist.append({"code": c, "name": n})
        return watchlist
    except Exception as e:
        st.warning(f"スプレッドシートの読み込みに失敗しました（権限設定をご確認ください）: {e}")
        return []

def save_watchlist_to_sheet(items):
    """ウォッチリストをスプレッドシートへ全件上書き保存（変更時のみ1回実行）"""
    try:
        ws = get_watchlist_worksheet()
        if not ws:
            return
        # A列: code, B列: name
        rows = [["code", "name"]]
        for item in items:
            c = item.get("code") if isinstance(item, dict) else item
            n = item.get("name", "") if isinstance(item, dict) else ""
            rows.append([str(c).strip().upper(), str(n).strip()])
            
        ws.clear()
        ws.update("A1", rows)
    except Exception as e:
        st.error(f"スプレッドシートの保存に失敗しました: {e}")

def init_watchlist_state():
    """セッション状態の初期化（アプリ起動時の初回のみスプレッドシートから読み込む）"""
    if "watchlist" not in st.session_state:
        items = load_watchlist_from_sheet()
        # 初回でシートが完全に空の場合はデフォルトを用意
        if not items:
            items = [
                {"code": "6315", "name": "TOWA"},
                {"code": "6323", "name": "ローツェ"},
                {"code": "285A", "name": "キオクシアHD"},
                {"code": "6857", "name": "アドバンテスト"}
            ]
            save_watchlist_to_sheet(items)
        st.session_state.watchlist = items

def toggle_favorite(code, name=""):
    """お気に入りの追加 / 削除（新規は末尾に追加し即座にスプレッドシート保存）"""
    code_str = str(code).strip().upper()
    current = st.session_state.watchlist
    
    existing_codes = [item.get("code") if isinstance(item, dict) else item for item in current]
    
    if code_str in existing_codes:
        st.session_state.watchlist = [
            item for item in current 
            if (item.get("code") if isinstance(item, dict) else item) != code_str
        ]
    else:
        display_name = name if name else code_str
        st.session_state.watchlist.append({"code": code_str, "name": display_name})
        
    save_watchlist_to_sheet(st.session_state.watchlist)

def is_favorite(code):
    """登録済みかどうか判定"""
    code_str = str(code).strip().upper()
    current = st.session_state.get("watchlist", [])
    existing_codes = [item.get("code") if isinstance(item, dict) else item for item in current]
    return code_str in existing_codes

def remove_item(code):
    """銘柄コード指定で削除"""
    code_str = str(code).strip().upper()
    st.session_state.watchlist = [
        item for item in st.session_state.watchlist 
        if (item.get("code") if isinstance(item, dict) else item) != code_str
    ]
    save_watchlist_to_sheet(st.session_state.watchlist)

def move_item_by_code(code, direction):
    """銘柄の並び順を上下に変更（direction: -1は上、+1は下）"""
    items = st.session_state.watchlist
    idx = -1
    for i, it in enumerate(items):
        c = it.get("code") if isinstance(it, dict) else it
        if c == code:
            idx = i
            break
    if idx == -1: return
    new_idx = idx + direction
    if 0 <= new_idx < len(items):
        items[idx], items[new_idx] = items[new_idx], items[idx]
        st.session_state.watchlist = items
        save_watchlist_to_sheet(items)

def render_watchlist_ui():
    """ウォッチリストUI（スプレッドシート完全永続化 ＆ テキスト一括並び替え対応）"""
    watchlist = st.session_state.watchlist
    if not watchlist:
        st.info("「★ 追加」でお気に入り銘柄を登録できます")
        return

    # サイドバーのボタンスタイル調整
    st.markdown("""
        <style>
        div[data-testid="stSidebar"] div.row-widget.stButton > button {
            text-align: left !important;
            padding: 6px 10px !important;
            font-size: 13.5px !important;
            font-weight: 500 !important;
            min-height: 38px !important;
            border-radius: 6px !important;
            border: 1px solid #e0e0e0 !important;
            background-color: #ffffff !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
        }
        div[data-testid="stSidebar"] div.row-widget.stButton > button:hover {
            border-color: #2962ff !important;
            color: #2962ff !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # 1. 銘柄一覧（クリック切り替え & ✕削除）
    for idx, item in enumerate(watchlist):
        c_code = item.get("code") if isinstance(item, dict) else item
        c_name = item.get("name") if isinstance(item, dict) else ""
        
        col_main, col_del = st.columns([0.82, 0.18])
        
        with col_main:
            label = f"**{c_code}**  {c_name[:5]}" if c_name else f"**{c_code}**"
            if st.button(label, key=f"btn_sel_{c_code}_{idx}", use_container_width=True):
                st.session_state.current_ticker = c_code
                st.rerun()

        with col_del:
            if st.button("✕", key=f"btn_del_{c_code}_{idx}", help=f"{c_code} を削除", use_container_width=True):
                remove_item(c_code)
                st.rerun()

    st.markdown("---")

    # 2. テキストで一括並び替え（スプレッドシートへ自動同期）
    with st.expander("📝 テキストで一括並び替え", expanded=False):
        st.caption("行をカット＆ペーストで並び替えて「並び順を反映」を押してください")
        
        lines = []
        for it in watchlist:
            code = it.get("code") if isinstance(it, dict) else it
            name = it.get("name", "") if isinstance(it, dict) else ""
            lines.append(f"{code} {name}".strip())
        current_text = "\n".join(lines)
        
        edited_text = st.text_area("ウォッチリスト一覧（編集可）", value=current_text, height=180, key="batch_reorder_textarea")
        
        if st.button("並び順を反映", key="btn_apply_batch", use_container_width=True):
            new_lines = [l.strip() for l in edited_text.splitlines() if l.strip()]
            new_watchlist = []
            
            item_map = {
                (it.get("code") if isinstance(it, dict) else it): it 
                for it in watchlist
            }
            
            for line in new_lines:
                parts = line.split(maxsplit=1)
                c = parts[0].upper()
                n = parts[1] if len(parts) > 1 else ""
                
                if c in item_map:
                    orig = item_map[c]
                    orig_name = orig.get("name") if isinstance(orig, dict) else n
                    new_watchlist.append({"code": c, "name": orig_name})
                else:
                    new_watchlist.append({"code": c, "name": n})
            
            st.session_state.watchlist = new_watchlist
            save_watchlist_to_sheet(new_watchlist)
            st.rerun()

    # 3. 単品での並び順微調整
    with st.expander("↕️ 単品で並び順の微調整", expanded=False):
        options = [
            f"{it.get('code', '')} {it.get('name', '')}".strip() 
            for it in watchlist
        ]
        selected_target = st.selectbox("微調整する銘柄を選択", options, key="reorder_target_select")
        if selected_target:
            target_code = selected_target.split()[0]
            col_up, col_down = st.columns(2)
            with col_up:
                if st.button("⬆️ 上へ", use_container_width=True, key="btn_move_up"):
                    move_item_by_code(target_code, -1)
                    st.rerun()
            with col_down:
                if st.button("⬇️ 下へ", use_container_width=True, key="btn_move_down"):
                    move_item_by_code(target_code, 1)
                    st.rerun()
