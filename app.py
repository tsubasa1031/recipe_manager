import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime
import uuid
from github import Github, GithubException

# --- 設定 ---
DATA_FILE = 'recipe_data.json'

# --- 今回指定されたカテゴリ一覧 ---
DEFAULT_FOLDERS = [
    "未分類",
    "和食", "洋食", "フレンチ", "イタリアン",
    "中華料理", "鍋", "アジア"
]

# --- データ管理クラス ---
class RecipeManager:
    def __init__(self, filename):
        self.filename = filename
        self.data = self._load_data()

    def _load_data(self):
        # 1. ローカルファイルの確認
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # データのマイグレーション（古い形式のデータを新しい形式に変換）
                    self._migrate_data(data)
                    
                    # ★カテゴリの自動更新（新しいカテゴリ定義に含まれていて、ファイルにないものを追加）
                    current_folders = data.get("folders", [])
                    for folder in DEFAULT_FOLDERS:
                        if folder not in current_folders:
                            current_folders.append(folder)
                    data["folders"] = current_folders
                    
                    return data
            except json.JSONDecodeError:
                pass 

        # 初期データ構造（ファイルがない場合）
        return {
            "folders": DEFAULT_FOLDERS,
            "recipes": []
        }

    def _migrate_data(self, data):
        """古い形式のデータを修正する"""
        for recipe in data.get("recipes", []):
            # 作り方が文字列(旧形式)なら、リスト形式(新形式)に変換
            if isinstance(recipe.get("steps"), str):
                lines = recipe["steps"].split('\n')
                recipe["steps"] = [{"手順": line.strip()} for line in lines if line.strip()]

    def save_data(self):
        # 1. ローカル保存
        json_str = json.dumps(self.data, ensure_ascii=False, indent=4)
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.write(json_str)
        
        # 2. GitHubへ同期
        if "github" in st.secrets:
            self._sync_to_github(json_str)

    def _sync_to_github(self, content):
        try:
            gh_config = st.secrets["github"]
            token = gh_config["token"]
            repo_name = gh_config["repo"]
            branch = gh_config["branch"]

            g = Github(token)
            repo = g.get_repo(repo_name)
            remote_file_path = self.filename

            try:
                contents = repo.get_contents(remote_file_path, ref=branch)
                repo.update_file(
                    path=contents.path,
                    message=f"Update recipe data: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    content=content,
                    sha=contents.sha,
                    branch=branch
                )
            except GithubException as e:
                if e.status == 404:
                    repo.create_file(
                        path=remote_file_path,
                        message=f"Create recipe data: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        content=content,
                        branch=branch
                    )
                    st.toast("GitHubに保存しました", icon="🍳")
        except Exception as e:
            st.warning(f"GitHub同期エラー（ローカルには保存されています）: {e}")

    def add_folder(self, folder_name):
        if folder_name and folder_name not in self.data["folders"]:
            self.data["folders"].append(folder_name)
            self.save_data()
            return True
        return False

    def add_recipe(self, title, folder, ingredients, seasonings, steps_df):
        steps_list = steps_df.to_dict('records')
        new_recipe = {
            "id": str(uuid.uuid4()),
            "title": title,
            "folder": folder,
            "ingredients": ingredients,
            "seasonings": seasonings,
            "steps": steps_list,
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "logs": []
        }
        self.data["recipes"].append(new_recipe)
        self.save_data()

    def add_log(self, recipe_id, log_text):
        for recipe in self.data["recipes"]:
            if recipe["id"] == recipe_id:
                log_entry = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "text": log_text
                }
                recipe["logs"].insert(0, log_entry)
                self.save_data()
                return True
        return False

    def delete_recipe(self, recipe_id):
        self.data["recipes"] = [r for r in self.data["recipes"] if r["id"] != recipe_id]
        self.save_data()

# --- アプリケーション本体 ---
def main():
    st.set_page_config(page_title="My Cooking Lab", layout="wide", page_icon="🍳")
    
    st.markdown("""
    <style>
    .log-box {
        background-color: #fff5f5;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 8px;
        border-left: 5px solid #ff6b6b;
    }
    .stDataFrame { margin-top: 10px; }
    </style>
    """, unsafe_allow_html=True)

    st.title("🍳 My Cooking Lab (料理研究ノート)")
    
    manager = RecipeManager(DATA_FILE)
    menu = st.sidebar.radio("メニュー", ["レシピ一覧・検索", "新規レシピ登録", "フォルダ管理"])

    # ---------------------------------------------------------
    # 1. レシピ一覧・検索
    # ---------------------------------------------------------
    if menu == "レシピ一覧・検索":
        st.header("📖 レシピを探す")

        # --- 検索フィルター ---
        col_search1, col_search2 = st.columns([1, 2])
        with col_search1:
            # フォルダフィルタ
            folder_options = ["すべて"] + manager.data["folders"]
            selected_folder = st.selectbox("📂 フォルダ", folder_options)
        with col_search2:
            # 食材検索
            search_query = st.text_input("🔍 食材・料理名で検索", placeholder="例: 豚肉, カレー")

        # フィルタリング
        filtered_recipes = []
        for r in manager.data["recipes"]:
            is_folder_match = (selected_folder == "すべて") or (r["folder"] == selected_folder)
            
            is_word_match = True
            if search_query:
                query = search_query.lower()
                in_title = query in r["title"].lower()
                in_ingredients = query in r["ingredients"].lower()
                is_word_match = in_title or in_ingredients
            
            if is_folder_match and is_word_match:
                filtered_recipes.append(r)

        # --- 一覧表示 ---
        if not filtered_recipes:
            st.info("条件に合うレシピが見つかりません。")
        else:
            df_display = pd.DataFrame(filtered_recipes)[["title", "folder", "created_at"]]
            df_display.columns = ["料理名", "カテゴリ", "登録日"]
            
            st.write("▼ レシピを選択して詳細を表示")
            
            event = st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun"
            )

            if event.selection.rows:
                selected_index = event.selection.rows[0]
                recipe = filtered_recipes[selected_index]

                st.markdown("---")
                st.subheader(f"🍳 {recipe['title']}")
                st.caption(f"カテゴリ: {recipe['folder']} | 登録日: {recipe.get('created_at', '-')}")

                col1, col2 = st.columns([1, 1.2])
                
                with col1:
                    st.markdown("### 🥕 食材")
                    st.text(recipe['ingredients'])
                    st.markdown("### 🧂 調味料")
                    st.text(recipe['seasonings'])
                
                with col2:
                    st.markdown("### 🔥 作り方")
                    if isinstance(recipe['steps'], list):
                        steps_df = pd.DataFrame(recipe['steps'])
                        steps_df.index = steps_df.index + 1
                        st.dataframe(steps_df, use_container_width=True)
                    else:
                        st.text(recipe['steps'])

                st.markdown("---")
                st.subheader("📝 試行錯誤・気づきの記録 (PDCA)")
                
                with st.form(key=f"log_form_{recipe['id']}"):
                    col_log, col_btn = st.columns([4, 1])
                    with col_log:
                        new_log = st.text_input("気づき・メモを追加", placeholder="例: 次は塩を少し減らす", key=f"input_{recipe['id']}")
                    with col_btn:
                        submit_log = st.form_submit_button("記録")
                    
                    if submit_log and new_log:
                        manager.add_log(recipe['id'], new_log)
                        st.success("記録しました")
                        st.rerun()

                if recipe['logs']:
                    for log in recipe['logs']:
                        st.markdown(f"""
                        <div class="log-box">
                            <small>{log['date']}</small> : {log['text']}
                        </div>
                        """, unsafe_allow_html=True)
                
                with st.expander("設定・削除"):
                    if st.button("このレシピを削除する", key=f"del_{recipe['id']}"):
                        manager.delete_recipe(recipe['id'])
                        st.rerun()

    # ---------------------------------------------------------
    # 2. 新規レシピ登録
    # ---------------------------------------------------------
    elif menu == "新規レシピ登録":
        st.header("✍️ 新規レシピ登録")
        
        with st.form("add_recipe_form"):
            col_basic1, col_basic2 = st.columns([2, 1])
            with col_basic1:
                title = st.text_input("料理名 (必須)")
            with col_basic2:
                folder = st.selectbox("カテゴリ", manager.data["folders"])

            col1, col2 = st.columns(2)
            with col1:
                ingredients = st.text_area("食材リスト", height=150, placeholder="・豚バラ肉 200g\n・玉ねぎ 1個")
            with col2:
                seasonings = st.text_area("調味料リスト", height=150, placeholder="・醤油 大さじ1\n・みりん 大さじ1")
            
            st.markdown("### 作り方")
            st.caption("下に行を追加して手順を入力してください。")
            
            default_steps = pd.DataFrame([{"手順": ""}])
            
            edited_steps = st.data_editor(
                default_steps,
                num_rows="dynamic",
                use_container_width=True,
                key="editor_steps"
            )
            
            submitted = st.form_submit_button("レシピを保存する")
            
            if submitted:
                if title:
                    clean_steps = edited_steps[edited_steps["手順"].str.strip() != ""]
                    if clean_steps.empty:
                         st.error("作り方を1つ以上入力してください。")
                    else:
                        manager.add_recipe(title, folder, ingredients, seasonings, clean_steps)
                        st.success(f"「{title}」を保存しました！")
                else:
                    st.error("料理名は必須です。")

    # ---------------------------------------------------------
    # 3. フォルダ管理
    # ---------------------------------------------------------
    elif menu == "フォルダ管理":
        st.header("📂 カテゴリフォルダ管理")
        
        df_folders = pd.DataFrame(manager.data["folders"], columns=["フォルダ名"])
        st.dataframe(df_folders, hide_index=True)
        
        with st.form("add_folder_form"):
            new_folder_name = st.text_input("新しいフォルダ名を追加")
            submitted = st.form_submit_button("追加")
            
            if submitted:
                if manager.add_folder(new_folder_name):
                    st.success(f"フォルダ「{new_folder_name}」を追加しました。")
                    st.rerun()
                else:
                    st.warning("そのフォルダは既に存在するか、名前が無効です。")

if __name__ == "__main__":
    main()
