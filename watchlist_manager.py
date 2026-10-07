import json
import os
import streamlit as st
from streamlit_sortables import sort_items

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
    """TradingView風UI：クリック切り替え・✕削除・ドラッグ＆ドロップ並び替え対応"""
    watchlist = st.session_state.watchlist
    if not watchlist:
        st.info("「★ 追加」でお気に入り銘柄を登録できます")
        return

    # ボタンの余白を極限までコンパクトにし、白抜き文字欠けを防ぐCSS
    st.markdown("""
        <style>
        /* サイドバー内のボタンのスタイリング */
        div[data-testid="stSidebar"] div.stButton > button {
            padding: 4px 6px !important;
            font-size: 13px !important;
            min-height: 34px !important;
            line-height: 1.2 !important;
            border-radius: 6px !important;
        }
        /* ✕削除ボタンのスタイリング */
        div[data-testid="stSidebar"] div.stButton > button:has(div:contains("✕")),
        div[data-testid="stSidebar"] div.stButton > button[kind="secondary"] {
            color: #888 !important;
        }
        div[data-testid="stSidebar"] div.stButton > button:hover {
            color: #d32f2f !important;
            border-color: #d32f2f !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # 1. 各銘柄のクリック切り替え & ✕削除ボタン
    for item in watchlist:
        c_code = item.get("code") if isinstance(item, dict) else item
        c_name = item.get("name") if isinstance(item, dict) else ""
        
        col_main, col_del = st.columns([0.82, 0.18])
        with col_main:
            # 銘柄名をクリックすると100%確実にメイン画面を切り替え
            label = f"📊 {c_code} {c_name[:5]}" if c_name else f"📊 {c_code}"
            if st.button(label, key=f"wl_sel_{c_code}", use_container_width=True):
                st.session_state.current_ticker = c_code
                st.rerun()
                
        with col_del:
            # ✕ボタンをクリックすると100%確実に削除
            if st.button("✕", key=f"wl_del_{c_code}", help=f"{c_code} をリストから削除", use_container_width=True):
                remove_item(c_code)
                st.rerun()

    # 2. ドラッグ＆ドロップ並び替え用のアコーディオン
    with st.expander("↕️ ドラッグ＆ドロップで並び替え", expanded=False):
        st.caption("カードをつかんで上下に並び替えると即座に反映されます")
        
        display_labels = [
            f"{it.get('code', '')} {it.get('name', '')}".strip() 
            for it in watchlist
        ]
        
        sorted_labels = sort_items(display_labels, key="wl_sortable")
        
        # 順番が変わった場合に検知して保存
        if sorted_labels != display_labels:
            new_watchlist = []
            for lab in sorted_labels:
                code_part = lab.split()[0]
                matching = next((it for it in watchlist if (it.get("code") if isinstance(it, dict) else it) == code_part), None)
                if matching:
                    new_watchlist.append(matching)
            st.session_state.watchlist = new_watchlist
            save_watchlist(new_watchlist)
            st.rerun()
