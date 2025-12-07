import streamlit as st
import json
import os
from datetime import datetime
import uuid
from github import Github, GithubException

# --- 設定 ---
# 保存するデータファイル名
DATA_FILE = 'manga_data.json'

# --- データ管理クラス ---
class MangaManager:
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

        # 初期データ構造（漫画用）
        return {
            "folders": ["未分類", "連載中", "完結済み", "購入予定", "少年漫画", "少女漫画"],
            "mangas": []
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
                    message=f"Update manga data: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    content=content,
                    sha=contents.sha,
                    branch=branch
                )
            except GithubException as e:
                if e.status == 404:
                    # 作成 (Create)
                    repo.create_file(
                        path=remote_file_path,
                        message=f"Create manga data: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        content=content,
                        branch=branch
                    )
                    st.toast("GitHubに新規保存しました", icon="📚")
        except Exception as e:
            st.warning(f"GitHub同期エラー（ローカルには保存されています）: {e}")

    def add_folder(self, folder_name):
        if folder_name and folder_name not in self.data["folders"]:
            self.data["folders"].append(folder_name)
            self.save_data()
            return True
        return False

    def add_manga(self, title, folder, author, volumes, status, memo):
        new_manga = {
            "id": str(uuid.uuid4()),
            "title": title,
            "folder": folder,
            "author": author,
            "volumes": volumes,  # 所持巻数など
            "status": status,    # 連載状況など
            "memo": memo,        # あらすじやメモ
            "logs": []           # 読書ログ・購入履歴
        }
        self.data["mangas"].append(new_manga)
        self.save_data()

    def add_log(self, manga_id, log_text):
        for manga in self.data["mangas"]:
            if manga["id"] == manga_id:
                log_entry = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "text": log_text
                }
                manga["logs"].insert(0, log_entry)
                self.save_data()
                return True
        return False

    def get_mangas_by_folder(self, folder_name):
        if folder_name == "すべて":
            return self.data["mangas"]
        return [m for m in self.data["mangas"] if m["folder"] == folder_name]

    def delete_manga(self, manga_id):
        self.data["mangas"] = [m for m in self.data["mangas"] if m["id"] != manga_id]
        self.save_data()

    def update_manga_volumes(self, manga_id, new_volumes):
        """巻数情報を更新するヘルパー"""
        for manga in self.data["mangas"]:
            if manga["id"] == manga_id:
                manga["volumes"] = new_volumes
                self.save_data()
                return True
        return False

# --- アプリケーション本体 ---
def main():
    st.set_page_config(page_title="Manga Manager", layout="wide", page_icon="📚")
    
    st.markdown("""
    <style>
    .log-box {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 8px;
        border-left: 5px solid #4CAF50;
    }
    </style>
    """, unsafe_allow_html=True)

    st.title("📚 私の漫画管理棚")
    
    manager = MangaManager(DATA_FILE)

    menu = st.sidebar.radio("メニュー", ["本棚を見る (一覧)", "新しく登録する", "フォルダ(本棚)管理"])

    # ---------------------------------------------------------
    # 1. 本棚を見る
    # ---------------------------------------------------------
    if menu == "本棚を見る (一覧)":
        st.header("📖 登録済み漫画リスト")

        # フォルダフィルタ
        folder_options = ["すべて"] + manager.data["folders"]
        selected_folder = st.selectbox("📂 カテゴリで絞り込み", folder_options)

        mangas = manager.get_mangas_by_folder(selected_folder)

        if not mangas:
            st.info("まだ登録がありません。「新しく登録する」から追加してください。")
        
        for manga in mangas:
            # エクスパンダーのラベル作成
            label = f"【{manga['folder']}】 {manga['title']} （{manga['volumes']}）"
            
            with st.expander(label):
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.markdown(f"**👤 作者:** {manga['author']}")
                    st.markdown(f"**🏷️ ステータス:** {manga['status']}")
                    
                    # 巻数クイック更新
                    new_vol = st.text_input("所持巻数を更新", value=manga['volumes'], key=f"vol_{manga['id']}")
                    if new_vol != manga['volumes']:
                        manager.update_manga_volumes(manga['id'], new_vol)
                        st.toast(f"{manga['title']}の巻数を更新しました")
                        st.rerun()

                with col2:
                    st.markdown("**📝 メモ・あらすじ:**")
                    st.info(manga['memo'] if manga['memo'] else "メモなし")

                st.markdown("---")
                
                # --- 読書・購入ログ ---
                st.subheader("🔖 読書・購入ログ")
                
                with st.form(key=f"log_form_{manga['id']}"):
                    col_log, col_btn = st.columns([3, 1])
                    with col_log:
                        new_log = st.text_input("ログを追加 (例: 12巻購入, アニメ化決定！)", key=f"input_{manga['id']}")
                    with col_btn:
                        submit_log = st.form_submit_button("記録")
                    
                    if submit_log and new_log:
                        manager.add_log(manga['id'], new_log)
                        st.success("記録しました")
                        st.rerun()

                if manga['logs']:
                    for log in manga['logs']:
                        st.markdown(f"""
                        <div class="log-box">
                            <small>{log['date']}</small> : {log['text']}
                        </div>
                        """, unsafe_allow_html=True)

                if st.button("🗑️ この漫画を削除", key=f"del_{manga['id']}"):
                    manager.delete_manga(manga['id'])
                    st.rerun()

    # ---------------------------------------------------------
    # 2. 新しく登録する
    # ---------------------------------------------------------
    elif menu == "新しく登録する":
        st.header("✍️ 新規漫画登録")
        
        with st.form("add_manga_form"):
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input("タイトル (必須)")
                author = st.text_input("作者")
            with col2:
                folder = st.selectbox("カテゴリ(フォルダ)", manager.data["folders"])
                status = st.selectbox("ステータス", ["連載中", "完結", "休載中", "未購入"])

            volumes = st.text_input("所持巻数 (例: 1-15巻, 全巻)", placeholder="1-5巻")
            memo = st.text_area("メモ・あらすじ・備考", height=100)
            
            submitted = st.form_submit_button("登録する")
            
            if submitted:
                if title:
                    manager.add_manga(title, folder, author, volumes, status, memo)
                    st.success(f"「{title}」を本棚に追加しました！")
                else:
                    st.error("タイトルは必須です。")

    # ---------------------------------------------------------
    # 3. フォルダ管理
    # ---------------------------------------------------------
    elif menu == "フォルダ(本棚)管理":
        st.header("📂 カテゴリ管理")
        st.write("現在のカテゴリ一覧:")
        st.write(manager.data["folders"])
        
        with st.form("add_folder"):
            new_folder = st.text_input("新しいカテゴリ名 (例: 電子書籍, ジャンプ作品)")
            if st.form_submit_button("追加"):
                if manager.add_folder(new_folder):
                    st.success(f"「{new_folder}」を追加しました。")
                    st.rerun()
                else:
                    st.warning("既にあるか、無効な名前です。")

if __name__ == "__main__":
    main()
