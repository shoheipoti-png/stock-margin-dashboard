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
        save_watchlist(items)

def render_watchlist_ui():
    """TradingView風ウォッチリスト（確実動作版）"""
    watchlist = st.session_state.watchlist
    if not watchlist:
        st.info("「★ 追加」でお気に入り銘柄を登録できます")
        return

    # サイドバーのボタンデザインをTradingView風カードに調整
    st.markdown("""
        <style>
        /* 銘柄カードボタン */
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

    # 銘柄リスト
    for idx, item in enumerate(watchlist):
        c_code = item.get("code") if isinstance(item, dict) else item
        c_name = item.get("name") if isinstance(item, dict) else ""
        
        col_main, col_del = st.columns([0.82, 0.18])
        
        with col_main:
            # 銘柄クリックで確実に切り替え
            label = f"**{c_code}**  {c_name[:5]}" if c_name else f"**{c_code}**"
            if st.button(label, key=f"btn_sel_{c_code}_{idx}", use_container_width=True):
                st.session_state.current_ticker = c_code
                st.rerun()

        with col_del:
            # ✕ボタンで確実に削除
            if st.button("✕", key=f"btn_del_{c_code}_{idx}", help=f"{c_code} を削除", use_container_width=True):
                remove_item(c_code)
                st.rerun()

    st.markdown("---")

    # シンプルで迷わない並び替えツール
    with st.expander("↕️ 並び順の変更", expanded=False):
        options = [
            f"{it.get('code', '')} {it.get('name', '')}".strip() 
            for it in watchlist
        ]
        selected_target = st.selectbox("移動する銘柄を選択", options, key="reorder_target_select")
        if selected_target:
            target_code = selected_target.split()[0]
            col_up, col_down = st.columns(2)
            with col_up:
                if st.button("⬆️ 上へ移動", use_container_width=True, key="btn_move_up"):
                    move_item_by_code(target_code, -1)
                    st.rerun()
            with col_down:
                if st.button("⬇️ 下へ移動", use_container_width=True, key="btn_move_down"):
                    move_item_by_code(target_code, 1)
                    st.rerun()
