import json
import os
from typing import List, Dict, Any, Optional

import streamlit as st
from newspaper import Article
from newspaper.article import ArticleException
from openai import OpenAI
import anthropic


def get_anthropic_client(api_key: Optional[str] = None) -> anthropic.Anthropic:
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=api_key)


def get_openai_client(api_key: Optional[str] = None) -> OpenAI:
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    return OpenAI(api_key=api_key)


def extract_article_from_url(url: str) -> str:
    """
    newspaper3k を使って URL から本文テキストを抽出する。
    失敗した場合は例外を投げる。
    """
    article = Article(url, language="en")
    article.download()
    article.parse()
    if not article.text.strip():
        raise ArticleException("本文を抽出できませんでした。")
    return article.text


def build_prompt(passage: str) -> Dict[str, str]:
    system_prompt = (
        "You are an expert TOEIC Part 7 creator and professional English teacher. "
        "You must strictly follow the output JSON schema.\n\n"
        "【Task / タスク】\n"
        "- The user gives you an English passage.\n"
        "- Create 3 TOEIC Part 7 style reading comprehension questions based ONLY on that passage.\n"
        "- Each question must have 4 options (A, B, C, D).\n"
        "- Provide the correct answer key and a short explanation in Japanese.\n\n"
        "【Output format / 出力フォーマット】\n"
        "Return ONLY a JSON object, no additional text, in the following exact structure:\n"
        "{\n"
        "  \"questions\": [\n"
        "    {\n"
        "      \"question\": \"string, the question in English\",\n"
        "      \"options\": {\n"
        "        \"A\": \"string\",\n"
        "        \"B\": \"string\",\n"
        "        \"C\": \"string\",\n"
        "        \"D\": \"string\"\n"
        "      },\n"
        "      \"answer\": \"A|B|C|D (the correct option letter)\",\n"
        "      \"explanation_ja\": \"string, brief explanation in Japanese\"\n"
        "    },\n"
        "    ... (total 3 questions)\n"
        "  ]\n"
        "}\n"
        "Do not wrap the JSON in markdown code fences.\n"
    )

    user_prompt = (
        "以下の英文を読んで、TOEIC Part 7 形式の読解問題を3問作成してください。\n"
        "- 各問題は 4 択 (A, B, C, D)\n"
        "- 問題文と選択肢は英語\n"
        "- 正解と、なぜその選択肢が正しいかの簡潔な日本語解説を付けてください。\n\n"
        "【英文パッセージ】\n"
        f"{passage}\n"
    )
    return {"system": system_prompt, "user": user_prompt}


def call_anthropic(system_prompt: str, user_prompt: str, api_key: Optional[str]) -> str:
    client = get_anthropic_client(api_key)
    response = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1500,
        temperature=0.6,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    # anthropic-python v0.34 returns a list of content blocks
    return "".join(block.text for block in response.content if hasattr(block, "text"))


def call_openai(system_prompt: str, user_prompt: str, api_key: Optional[str]) -> str:
    client = get_openai_client(api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.6,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""


def parse_questions(raw: str) -> List[Dict[str, Any]]:
    """
    モデルからの JSON 文字列を安全にパースし、
    questions 配列を取り出して返す。
    """
    # もし ``` などで囲まれていたら取り除く簡易処理
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        # 言語タグがついている場合を想定して最初の改行まで削除
        first_brace = cleaned.find("{")
        if first_brace != -1:
            cleaned = cleaned[first_brace:]

    data = json.loads(cleaned)
    questions = data.get("questions", [])
    if not isinstance(questions, list):
        raise ValueError("questions が配列ではありません。")
    return questions


def render_questions(questions: List[Dict[str, Any]]) -> None:
    for idx, q in enumerate(questions, start=1):
        with st.container(border=True):
            st.markdown(f"### Question {idx}")
            st.markdown(q.get("question", ""))

            options = q.get("options", {})
            st.markdown("**Choices**")
            for label in ["A", "B", "C", "D"]:
                text = options.get(label, "")
                st.markdown(f"- **{label}.** {text}")

            answer = q.get("answer", "")
            explanation = q.get("explanation_ja", "")
            st.markdown("---")
            st.markdown(f"**正解: {answer}**")
            if explanation:
                st.markdown(f"**解説 (日本語)**")
                st.markdown(explanation)


def main():
    st.set_page_config(
        page_title="TOEIC Part 7 問題自動生成ツール",
        page_icon="📚",
        layout="wide",
    )

    st.title("TOEIC Part 7 問題生成アプリ")
    st.write(
        "X（旧Twitter）の英文ポストやニュース記事の URL、または英文テキストから、"
        "TOEIC Part 7 形式の読解問題（4択×3問）を自動生成します。"
    )

    # サイドバー: モデル・APIキー設定
    st.sidebar.header("モデル設定")
    provider = st.sidebar.selectbox(
        "使用するモデル",
        options=["Anthropic (Claude 3.5 Sonnet 推奨)", "OpenAI (GPT-4o)"],
        index=0,
    )

    if "Anthropic" in provider:
        default_key = os.getenv("ANTHROPIC_API_KEY", "")
        sidebar_label = "Anthropic API Key（未設定なら環境変数 / secrets から取得を試みます）"
    else:
        default_key = os.getenv("OPENAI_API_KEY", "")
        sidebar_label = "OpenAI API Key（未設定なら環境変数 / secrets から取得を試みます）"

    api_key_input = st.sidebar.text_input(
        sidebar_label,
        value=default_key,
        type="password",
    )

    st.sidebar.info(
        "セキュリティのため、可能であれば `st.secrets` や環境変数に API キーを設定してください。"
    )

    # メイン入力
    st.subheader("1. 英文ソースの入力")
    url = st.text_input("URL（Xのポストやニュース記事など）", placeholder="https://...")
    text_input = st.text_area(
        "または、英文テキストを直接貼り付け",
        height=200,
        placeholder="ここに英文を貼り付けてください（URLがうまく読み取れない場合のバックアップ用）",
    )

    st.caption(
        "※ URL が指定されている場合は、まず URL から記事本文の抽出を試みます。"
        "失敗した場合は、テキストエリアの内容を使用します。"
    )

    if st.button("問題を生成する", type="primary"):
        if not url and not text_input.strip():
            st.error("URL または 英文テキストのどちらか一方は必ず入力してください。")
            return

        # APIキーの解決（入力 > secrets > 環境変数）
        api_key = api_key_input.strip()
        if not api_key:
            # st.secrets が設定されていない環境でもエラーにならないように安全に参照
            secrets_dict = getattr(st, "secrets", None)
            if "Anthropic" in provider:
                if secrets_dict and "ANTHROPIC_API_KEY" in secrets_dict:
                    api_key = secrets_dict["ANTHROPIC_API_KEY"]
                else:
                    api_key = os.getenv("ANTHROPIC_API_KEY", "")
            else:
                if secrets_dict and "OPENAI_API_KEY" in secrets_dict:
                    api_key = secrets_dict["OPENAI_API_KEY"]
                else:
                    api_key = os.getenv("OPENAI_API_KEY", "")

        if not api_key:
            st.error("API キーが見つかりません。サイドバーまたは環境変数 / secrets に設定してください。")
            return

        passage = ""
        article_error = None

        if url:
            with st.spinner("URL から記事本文を抽出しています..."):
                try:
                    passage = extract_article_from_url(url)
                except Exception as e:
                    article_error = str(e)

        if not passage and text_input.strip():
            passage = text_input.strip()

        if not passage:
            st.error(
                "URL から本文を抽出できず、テキストエリアにも有効な英文が見つかりませんでした。\n"
                "英文テキストを直接貼り付けて再度お試しください。"
            )
            if article_error:
                with st.expander("URL 抽出エラーの詳細"):
                    st.error(article_error)
            return

        if article_error:
            st.warning(
                "URL からの本文抽出で問題が発生したため、テキストエリアの内容（または抽出できた範囲）を使用しています。"
            )

        prompts = build_prompt(passage)

        with st.spinner("AI がTOEIC Part 7形式の問題を作成中です...（数秒〜十数秒かかる場合があります）"):
            try:
                if "Anthropic" in provider:
                    raw_output = call_anthropic(
                        prompts["system"],
                        prompts["user"],
                        api_key,
                    )
                else:
                    raw_output = call_openai(
                        prompts["system"],
                        prompts["user"],
                        api_key,
                    )

                questions = parse_questions(raw_output)

            except Exception as e:
                st.error("問題の生成またはパース中にエラーが発生しました。")
                with st.expander("エラーの詳細を見る"):
                    st.exception(e)
                    st.text("=== モデルの生出力 ===")
                    st.write(raw_output if "raw_output" in locals() else "(出力なし)")
                return

        st.subheader("2. 生成された問題")
        with st.expander("元の英文パッセージを表示する", expanded=False):
            st.write(passage)

        render_questions(questions)


if __name__ == "__main__":
    main()

