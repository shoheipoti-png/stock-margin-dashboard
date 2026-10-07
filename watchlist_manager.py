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

def move_item(index, direction):
    """銘柄の並び順を上下に変更（direction: -1は上、+1は下）"""
    items = st.session_state.watchlist
    new_idx = index + direction
    if 0 <= new_idx < len(items):
        items[index], items[new_idx] = items[new_idx], items[index]
        st.session_state.watchlist = items
        save_watchlist(items)

def remove_item(code):
    """銘柄コード指定で削除"""
    code_str = str(code).strip().upper()
    st.session_state.watchlist = [
        item for item in st.session_state.watchlist 
        if (item.get("code") if isinstance(item, dict) else item) != code_str
    ]
    save_watchlist(st.session_state.watchlist)

def reorder_watchlist(new_codes_list):
    """リスト順を更新"""
    current = st.session_state.watchlist
    item_map = {item.get("code") if isinstance(item, dict) else item: item for item in current}
    new_list = [item_map[c] for c in new_codes_list if c in item_map]
    st.session_state.watchlist = new_list
    save_watchlist(new_list)
