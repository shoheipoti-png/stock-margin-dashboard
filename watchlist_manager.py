import json
import os
import streamlit as st

WATCHLIST_FILE = "watchlist.json"

def load_watchlist():
    """ウォッチリストをJSONファイルから読み込む"""
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return [
        {"code": "6315", "name": "TOWA"},
        {"code": "6323", "name": "ローツェ"},
        {"code": "285A", "name": "キオクシアHD"},
        {"code": "6857", "name": "アドバンテスト"}
    ]

def save_watchlist(items):
    """ウォッチリストをJSONファイルに保存する"""
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def init_watchlist_state():
    """セッション状態の初期化"""
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = load_watchlist()

def toggle_favorite(code, name=""):
    """お気に入りの追加 / 削除"""
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
        
    save_watchlist(st.session_state.watchlist)

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
    save_watchlist(st.session_state.watchlist)

def render_watchlist_ui():
    """ウォッチリストUI：銘柄クリック切り替え & ✕削除"""
    watchlist = st.session_state.watchlist
    if not watchlist:
        st.info("「★ 追加」でお気に入り銘柄を登録できます")
        return

    # サイドバーボタンの余白とデザイン調整
    st.markdown("""
        <style>
        div[data-testid="stSidebar"] div.stButton > button {
            padding: 4px 8px !important;
            font-size: 13px !important;
            min-height: 36px !important;
            border-radius: 6px !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # 1. 銘柄一覧（クリックで即切り替え、✕で即削除）
    for item in watchlist:
        c_code = item.get("code") if isinstance(item, dict) else item
        c_name = item.get("name") if isinstance(item, dict) else ""
        
        col_main, col_del = st.columns([0.80, 0.20])
        with col_main:
            label = f"📊 {c_code} {c_name[:5]}" if c_name else f"📊 {c_code}"
            if st.button(label, key=f"wl_sel_{c_code}", use_container_width=True):
                st.session_state.current_ticker = c_code
                st.rerun()
                
        with col_del:
            if st.button("✕", key=f"wl_del_{c_code}", help=f"{c_code} を削除", use_container_width=True):
                remove_item(c_code)
                st.rerun()

    # 2. 並び順の変更（標準マルチセレクトによる安全・確実な並び替え）
    with st.expander("↕️ リストの並び順を変更", expanded=False):
        current_codes = [it.get("code") if isinstance(it, dict) else it for it in watchlist]
        new_order = st.multiselect(
            "表示したい順番に選択してください",
            options=current_codes,
            default=current_codes,
            key="reorder_select"
        )
        if st.button("並び順を保存", key="save_order_btn"):
            if set(new_order) == set(current_codes):
                item_map = {it.get("code") if isinstance(it, dict) else it: it for it in watchlist}
                st.session_state.watchlist = [item_map[c] for c in new_order]
                save_watchlist(st.session_state.watchlist)
                st.rerun()
