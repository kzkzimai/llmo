from flask import Flask, request, render_template, send_file, Response
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from bs4 import BeautifulSoup
import tempfile
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()  # .env を読み込む
openai_api_key = os.getenv("OPENAI_API_KEY")  # 変数を取得

client = OpenAI()

app = Flask(__name__)
auth = HTTPBasicAuth()

# BASIC認証ユーザー定義（例）
users = {
    "admin": generate_password_hash("password123")
}

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username

# メタ情報取得（文字化け対策付き）
def fetch_metadata(url):
    try:
        response = requests.get(url, timeout=5)
        response.encoding = response.apparent_encoding  # ← 文字化け防止の追加行
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string.strip() if soup.title else "No Title"
        desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        description = desc_tag["content"].strip() if desc_tag and "content" in desc_tag.attrs else "No description available."
        return title, description
    except Exception as e:
        return "Error fetching page", str(e)

# OpenAI要約（新API対応）
def generate_summary(pairs):
    context = "\n".join([f"- {title}: {desc}" for title, desc in pairs])
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional marketing content analyst. "
                    "You are skilled at interpreting multiple article titles and descriptions from a website "
                    "to infer its purpose, positioning, services, and strengths."
                )
            },
            {
                "role": "user",
                "content": (
                    "以下はある企業サイトに掲載されている記事やページのタイトルと説明文です。\n"
                    "これらをもとに、そのサイト全体の要約を「Markdown形式の引用（>）」で1段落書いてください。\n"
                    "以下の点を重視して要約してください：\n"
                    "- 企業の目的・使命（何のために存在するか）\n"
                    "- どんな価値を、どんな手法で提供しているか（事業やサービスの特徴）\n"
                    "- 他社と差別化される視点（独自性や姿勢など）\n"
                    "- 書き出しは「株式会社〇〇は、」または同義の企業紹介から自然に始めてください\n\n"
                    "【タイトルと説明文の一覧】\n\n"
                    f"{context}"
                )
            }
        ]
    )
    return response.choices[0].message.content.strip()


@app.route('/', methods=['GET', 'POST'])
@auth.login_required
def index():
    if request.method == 'POST':
        urls = request.form['urls'].splitlines()
        urls = [u.strip() for u in urls if u.strip()]

        pairs = []
        for url in urls:
            title, description = fetch_metadata(url)
            pairs.append((title, description, url))

        summary = generate_summary([(t, d) for t, d, _ in pairs])

        markdown_lines = [
            "# llms.txt",
            "",
            summary,
            "",
            "## URLs and Descriptions",
            ""
        ]
        for title, desc, url in pairs:
            markdown_lines.append(f"- [{title}]({url}): {desc}")

        content = "\n".join(markdown_lines)
        tmpfile = tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.txt')
        tmpfile.write(content)
        tmpfile.close()
        return send_file(tmpfile.name, as_attachment=True, download_name='llms.txt')

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)