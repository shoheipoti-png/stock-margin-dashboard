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
    # 初期のデフォルト銘柄（例）
    return ["6315", "6323", "285A"]

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
    
    # すでに登録されているかチェック
    existing_codes = [item if isinstance(item, str) else item.get("code") for item in current]
    
    if code_str in existing_codes:
        # 削除
        st.session_state.watchlist = [item for item in current if (item if isinstance(item, str) else item.get("code")) != code_str]
    else:
        # 追加
        item_obj = {"code": code_str, "name": name if name else code_str}
        st.session_state.watchlist.append(item_obj)
        
    save_watchlist(st.session_state.watchlist)

def is_favorite(code):
    """登録済みかどうか判定"""
    code_str = str(code).strip().upper()
    current = st.session_state.get("watchlist", [])
    existing_codes = [item if isinstance(item, str) else item.get("code") for item in current]
    return code_str in existing_codes

def move_item(index, direction):
    """銘柄の並び順を上下に変更（direction: -1は上、+1は下）"""
    items = st.session_state.watchlist
    new_idx = index + direction
    if 0 <= new_idx < len(items):
        items[index], items[new_idx] = items[new_idx], items[index]
        st.session_state.watchlist = items
        save_watchlist(items)

def remove_item(index):
    """インデックス指定で削除"""
    items = st.session_state.watchlist
    if 0 <= index < len(items):
        items.pop(index)
        st.session_state.watchlist = items
        save_watchlist(items)
