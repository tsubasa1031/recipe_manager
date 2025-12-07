import streamlit as st
import json
import os
from datetime import datetime
import uuid
from github import Github, GithubException

# --- 設定 ---
# 保存するデータファイル名（レシピ専用）
DATA_FILE = 'recipe_data.json'

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
                    return json.load(f)
            except json.JSONDecodeError:
                pass 

        # 初期データ構造（レシピ用）
        # ユーザーの要望に合わせてカテゴリを初期設定
        return {
            "folders": ["未分類", "和食", "洋食", "中華", "パスタ", "スイーツ"],
            "recipes": []
        }

    def save_data(self):
        # 1. ローカル保存
        json_str = json.dumps(self.data, ensure_ascii=False, indent=4)
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.write(json_str)
        
        # 2. GitHubへ同期 (secrets.tomlの設定を使用)
        if "github" in st.secrets:
            self._sync_to_github(json_str)

    def _sync_to_github(self, content):
        """GitHub上のファイルを更新、または作成する"""
        try:
            gh_config = st.secrets["github"]
            token = gh_config["token"]
            repo_name = gh_config["repo"]
            branch = gh_config["branch"]

            g = Github(token)
            repo = g.get_repo(repo_name)
            
            remote_file_path = self.filename

            try:
                # 更新 (Update)
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
                    # 作成 (Create)
                    repo.create_file(
                        path=remote_file_path,
                        message=f"Create recipe data: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        content=content,
                        branch=branch
                    )
                    st.toast("GitHubに新規保存しました", icon="🍳")
        except Exception as e:
            st.warning(f"GitHub同期エラー（ローカルには保存されています）: {e}")

    def add_folder(self, folder_name):
        if folder_name and folder_name not in self.data["folders"]:
            self.data["folders"].append(folder_name)
            self.save_data()
            return True
        return False

    def add_recipe(self, title, folder, ingredients, seasonings, steps):
        new_recipe = {
            "id": str(uuid.uuid4()),
            "title": title,
            "folder": folder,
            "ingredients": ingredients,
            "seasonings": seasonings,
            "steps": steps,
            "logs": []  # 試行錯誤の記録用リスト
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
                recipe["logs"].insert(0, log_entry)  # 新しいものを上に
                self.save_data()
                return True
        return False

    def get_recipes_by_folder(self, folder_name):
        if folder_name == "すべて":
            return self.data["recipes"]
        return [r for r in self.data["recipes"] if r["folder"] == folder_name]

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
    </style>
    """, unsafe_allow_html=True)

    st.title("🍳 My Cooking Lab (料理研究ノート)")
    
    manager = RecipeManager(DATA_FILE)

    menu = st.sidebar.radio("メニュー", ["レシピを見る・研究する", "新しいレシピを登録", "フォルダ管理"])

    # ---------------------------------------------------------
    # 1. レシピを見る・研究する
    # ---------------------------------------------------------
    if menu == "レシピを見る・研究する":
        st.header("📖 レシピ一覧")

        # フォルダフィルタ
        folder_options = ["すべて"] + manager.data["folders"]
        selected_folder = st.selectbox("📂 カテゴリで絞り込み", folder_options)

        recipes = manager.get_recipes_by_folder(selected_folder)

        if not recipes:
            st.info("レシピがまだありません。「新しいレシピを登録」から追加してください。")
        
        for recipe in recipes:
            with st.expander(f"【{recipe['folder']}】 {recipe['title']}"):
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.subheader("🥕 食材")
                    st.text(recipe['ingredients'])
                    st.subheader("🧂 調味料")
                    st.text(recipe['seasonings'])
                
                with col2:
                    st.subheader("🔥 作り方")
                    st.text(recipe['steps'])

                st.markdown("---")
                
                # --- 試行錯誤ログセクション ---
                st.subheader("📝 試行錯誤・気づきの記録 (PDCA)")
                
                with st.form(key=f"log_form_{recipe['id']}"):
                    col_log, col_btn = st.columns([3, 1])
                    with col_log:
                        new_log = st.text_input("今回の気づきを入力 (例: 塩少なめでOK, 焼き時間+1分)", key=f"input_{recipe['id']}")
                    with col_btn:
                        submit_log = st.form_submit_button("記録を追加")
                    
                    if submit_log and new_log:
                        manager.add_log(recipe['id'], new_log)
                        st.success("記録を保存しました！")
                        st.rerun()

                # 過去のログ表示
                if recipe['logs']:
                    st.write("▼ 過去の記録")
                    for log in recipe['logs']:
                        st.markdown(f"""
                        <div class="log-box">
                            <small>{log['date']}</small><br>
                            {log['text']}
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.caption("まだ記録はありません。")

                # 削除ボタン
                if st.button("🗑️ このレシピを削除", key=f"del_{recipe['id']}"):
                    manager.delete_recipe(recipe['id'])
                    st.rerun()

    # ---------------------------------------------------------
    # 2. 新しいレシピを登録
    # ---------------------------------------------------------
    elif menu == "新しいレシピを登録":
        st.header("✍️ 新規レシピ登録")
        
        with st.form("add_recipe_form"):
            col_basic1, col_basic2 = st.columns([2, 1])
            with col_basic1:
                title = st.text_input("料理名 (必須)")
            with col_basic2:
                folder = st.selectbox("フォルダ", manager.data["folders"])

            col1, col2 = st.columns(2)
            with col1:
                ingredients = st.text_area("食材リスト", height=150, placeholder="例：\n豚バラ肉 200g\nキャベツ 1/4個")
            with col2:
                seasonings = st.text_area("調味料リスト", height=150, placeholder="例：\n醤油 大さじ1\nみりん 大さじ1")
            
            steps = st.text_area("作り方", height=200, placeholder="手順を記述してください")
            
            submitted = st.form_submit_button("レシピを保存する")
            
            if submitted:
                if title:
                    manager.add_recipe(title, folder, ingredients, seasonings, steps)
                    st.success(f"「{title}」を保存しました！")
                else:
                    st.error("料理名は必須です。")

    # ---------------------------------------------------------
    # 3. フォルダ管理
    # ---------------------------------------------------------
    elif menu == "フォルダ管理":
        st.header("📂 フォルダ(カテゴリ)の管理")
        
        st.write("現在のフォルダ一覧:")
        st.write(manager.data["folders"])
        
        with st.form("add_folder_form"):
            new_folder_name = st.text_input("新しいフォルダ名")
            submitted = st.form_submit_button("追加")
            
            if submitted:
                if manager.add_folder(new_folder_name):
                    st.success(f"フォルダ「{new_folder_name}」を追加しました。")
                    st.rerun()
                else:
                    st.warning("そのフォルダは既に存在するか、名前が無効です。")

if __name__ == "__main__":
    main()
