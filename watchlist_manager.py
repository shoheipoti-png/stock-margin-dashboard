import json
import os
import streamlit as st
import streamlit.components.v1 as components

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

def reorder_watchlist(new_codes):
    """ドラッグ＆ドロップで並び替えられた順番に更新"""
    current = st.session_state.watchlist
    item_map = {item["code"] if isinstance(item, dict) else item: item for item in current}
    new_list = []
    for c in new_codes:
        if c in item_map:
            new_list.append(item_map[c])
    st.session_state.watchlist = new_list
    save_watchlist(new_list)

def render_drag_and_drop_watchlist():
    """サイドバー用のドラッグ＆ドロップ対応ウォッチリストUI"""
    watchlist = st.session_state.watchlist
    if not watchlist:
        st.info("「★ 追加」でお気に入り銘柄を登録できます")
        return

    items_json = json.dumps(watchlist, ensure_ascii=False)

    # HTML5 Drag and Drop を実装したコンパクトなUI
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        margin: 0;
        padding: 4px;
        background: transparent;
        user-select: none;
      }}
      .list-container {{
        display: flex;
        flex-direction: column;
        gap: 6px;
      }}
      .item {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 6px;
        padding: 8px 10px;
        cursor: grab;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
      }}
      .item:hover {{
        border-color: #2962ff;
        box-shadow: 0 2px 6px rgba(41,98,255,0.15);
      }}
      .item.dragging {{
        opacity: 0.4;
        cursor: grabbing;
      }}
      .drag-handle {{
        color: #9e9e9e;
        margin-right: 8px;
        font-size: 14px;
        cursor: grab;
      }}
      .ticker-info {{
        flex-grow: 1;
        cursor: pointer;
        display: flex;
        align-items: baseline;
        gap: 8px;
        text-decoration: none;
      }}
      .ticker-code {{
        font-weight: 700;
        font-size: 14px;
        color: #1a1a1a;
      }}
      .ticker-name {{
        font-size: 12px;
        color: #616161;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 120px;
      }}
      .del-btn {{
        background: none;
        border: none;
        color: #b0bec5;
        font-size: 15px;
        cursor: pointer;
        padding: 2px 6px;
        border-radius: 4px;
        transition: color 0.15s, background 0.15s;
      }}
      .del-btn:hover {{
        color: #d32f2f;
        background: #ffebee;
      }}
    </style>
    </head>
    <body>
      <div id="watchlist" class="list-container"></div>

      <script>
        const items = {items_json};
        const container = document.getElementById('watchlist');

        function renderList() {{
          container.innerHTML = '';
          items.forEach((item, index) => {{
            const div = document.createElement('div');
            div.className = 'item';
            div.draggable = true;
            div.dataset.index = index;
            div.dataset.code = item.code || item;

            div.innerHTML = `
              <span class="drag-handle">☰</span>
              <div class="ticker-info" onclick="selectTicker('${{item.code || item}}')">
                <span class="ticker-code">${{item.code || item}}</span>
                <span class="ticker-name">${{item.name || ''}}</span>
              </div>
              <button class="del-btn" title="削除" onclick="removeItem('${{item.code || item}}')">✕</button>
            `;

            div.addEventListener('dragstart', handleDragStart);
            div.addEventListener('dragover', handleDragOver);
            div.addEventListener('drop', handleDrop);
            div.addEventListener('dragend', handleDragEnd);

            container.appendChild(div);
          }});
        }}

        let draggedIndex = null;

        function handleDragStart(e) {{
          draggedIndex = +this.dataset.index;
          this.classList.add('dragging');
          e.dataTransfer.effectAllowed = 'move';
        }}

        function handleDragOver(e) {{
          e.preventDefault();
          e.dataTransfer.dropEffect = 'move';
        }}

        function handleDrop(e) {{
          e.stopPropagation();
          const targetIndex = +this.dataset.index;
          if (draggedIndex !== null && draggedIndex !== targetIndex) {{
            const moved = items.splice(draggedIndex, 1)[0];
            items.splice(targetIndex, 0, moved);
            renderList();
            
            // Streamlitの親ウィンドウのURLクエリパラメータを書き換えて並び順を保存
            const codes = items.map(it => it.code || it).join(',');
            window.parent.postMessage({{
              type: 'streamlit:setComponentValue',
              value: {{ action: 'reorder', codes: codes }}
            }}, '*');
            
            // クエリパラメータを使って安全にリロード同期
            const parentUrl = new URL(window.parent.location.href);
            parentUrl.searchParams.set('reorder', codes);
            window.parent.history.replaceState(null, '', parentUrl.toString());
          }}
        }}

        function handleDragEnd() {{
          this.classList.remove('dragging');
        }}

        function selectTicker(code) {{
          const parentUrl = new URL(window.parent.location.href);
          parentUrl.searchParams.set('ticker', code);
          window.parent.location.href = parentUrl.toString();
        }}

        function removeItem(code) {{
          const parentUrl = new URL(window.parent.location.href);
          parentUrl.searchParams.set('del_ticker', code);
          window.parent.location.href = parentUrl.toString();
        }}

        renderList();
      </script>
    </body>
    </html>
    """
    calc_height = max(160, len(watchlist) * 44 + 20)
    components.html(html_code, height=calc_height, scrolling=False)
