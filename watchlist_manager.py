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
    """お気に入りの追加 / 削除（新規追加は末尾に追加）"""
    code_str = str(code).strip().upper()
    current = st.session_state.watchlist
    
    existing_codes = [item.get("code") if isinstance(item, dict) else item for item in current]
    
    if code_str in existing_codes:
        # 削除
        st.session_state.watchlist = [
            item for item in current 
            if (item.get("code") if isinstance(item, dict) else item) != code_str
        ]
    else:
        # 末尾に追加
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
        c = it.get("code") if isinstance(item, dict) else it
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
    """TradingView風ウォッチリスト（一括テキスト編集 & 上下移動対応）"""
    watchlist = st.session_state.watchlist
    if not watchlist:
        st.info("「★ 追加」でお気に入り銘柄を登録できます")
        return

    # サイドバーのボタンデザインを調整
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

    # 2. 解決策C：テキストで一括並び替え・編集
    with st.expander("📝 テキストで一括並び替え", expanded=False):
        st.caption("行をカット＆ペーストで並び替えて「並び順を反映」を押してください")
        
        # 1行ずつ "コード 社名" の形式で作成
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
            
            # 既存の銘柄情報をコードキーで引けるように辞書化
            item_map = {
                (it.get("code") if isinstance(it, dict) else it): it 
                for it in watchlist
            }
            
            for line in new_lines:
                parts = line.split(maxsplit=1)
                c = parts[0].upper()
                n = parts[1] if len(parts) > 1 else ""
                
                if c in item_map:
                    # 既存銘柄（元の名前情報を維持）
                    orig = item_map[c]
                    orig_name = orig.get("name") if isinstance(orig, dict) else n
                    new_watchlist.append({"code": c, "name": orig_name})
                else:
                    # テキスト編集で新しく追加されたコードの場合
                    new_watchlist.append({"code": c, "name": n})
            
            st.session_state.watchlist = new_watchlist
            save_watchlist(new_watchlist)
            st.rerun()

    # 3. 既存の1銘柄ずつの上下移動（そのまま残しています）
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
