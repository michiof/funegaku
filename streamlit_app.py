# For Streamlit online app

import streamlit as st
import pandas as pd
from openai import OpenAI
import pinecone
import tiktoken
import i18n

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"],)

# OpenAIのモデルの定義
EMBEDDING_MODEL = "text-embedding-ada-002"
GPT_MODEL = "gpt-3.5-turbo"

# 言語ファイルのパス
i18n.load_path.append('./lang')

# Streamlit setup
st.set_page_config(
   page_title="Accident Report Finder",
   page_icon="🔍",
   menu_items={
        'About': "**Accident Report Finder** v1.2.1 made by [Michio Fujii](https://github.com/michiof)",
    }
)

# プロンプトを作成する
def make_message(user_input, user_input_emb, num_of_output):
    related_data = get_relevant_data(user_input_emb)
    messages = [
        {"role": "system", "content": i18n.t('lang.prompt_for_search_system')},
        {"role": "user", "content": i18n.t('lang.prompt_for_search_user', 
                                            num_of_output=num_of_output, 
                                            user_input=user_input, 
                                            related_data=related_data
                                        )},
    ]
    return messages

# トークン数を計算する
def num_tokens(text: str, model: str) -> int:
    encoding = tiktoken.encoding_for_model(GPT_MODEL)
    return len(encoding.encode(text))

# Pineconeのmetadataを取得する
def get_metadata(match):
    info = []
    for key, value in match["metadata"].items():
        info.append(f"{key}: {value}\n")
    return "\n".join(info)

# Multiselectionの値からPinecone用のフィルターを作成し、session_stateに保存する
def make_pinecone_filter(filter_selection):
    filter = []
    if "Severity_2" in filter_selection:
        filter.append({"Severity": {"$in": ["2"]}})
    if "Cat3" in filter_selection:
        filter.append({"Cat_GrossTon": {"$in": ["Cat3"]}})
    
    if len(filter) > 1:
        filter_dic_for_pinecone = {"$and": filter}
    elif filter:
        filter_dic_for_pinecone = filter[0]
    else:
        filter_dic_for_pinecone = {}
    st.session_state['filter_dic'] = filter_dic_for_pinecone

# 類似ベクトルデータの抽出
def get_relevant_data(query_embedding, top_k=20):
    pinecone.init(api_key=st.secrets["PINECONE_API_KEY"], environment=st.secrets["PINECONE_ENVIRONMENT"])
    pinecone_index = pinecone.Index(st.secrets["PINECONE_INDEX"])
    token_budget = 4096 - 1500 #関連データのトークン上限値の設定
    relevant_data = ""
    filter_dic = st.session_state['filter_dic']
    for _ in range(3): # エラー発生時は3回までトライする
        try:
            results = pinecone_index.query(
                            vector=query_embedding,
                            filter=filter_dic,
                            top_k=top_k, 
                            include_metadata=True
                        )
            for i, match in enumerate(results["matches"], start=1):
                metadata = get_metadata(match)
                next_relevant_data = f"\n\nRelevant data {i}:\n{metadata}"
                if (
                    num_tokens(relevant_data + next_relevant_data, model=GPT_MODEL)
                    > token_budget
                ):
                    break
                else:
                    relevant_data += next_relevant_data
            return relevant_data
        except Exception as e:
            print(f"Error: {str(e)}")
            continue
    raise Exception("Error: Failed to retrieve relevant data after 3 attempts")

# Embeddingsの計算
def cal_embedding(user_input, model=EMBEDDING_MODEL):
    for _ in range(3): # エラー発生時は3回までトライする
        try:
            return client.embeddings.create(input=user_input, model=model).data[0].embedding
        except Exception as e:
            print(f"Error: {str(e)}")
            continue
    raise Exception("Failed to calculate embedding after 3 attempts")

# 検索画面での処理
def chat_page(num_of_output):
    new_msg = st.text_input(i18n.t('lang.label_msg_text_area'), value=st.session_state.sample_question, placeholder=i18n.t('lang.placeholder_text_area'))
    if st.button(i18n.t('lang.lable_load_sample')):
        st.session_state.sample_question = i18n.t('lang.placeholder_text_area') # load a sample question
    if st.button(i18n.t('lang.label_search_botton')):
        if new_msg:
            try:
                with st.spinner(i18n.t('lang.msg_while_searching')):
                    user_input = f"{i18n.t('lang.msg_header_search_text')}{new_msg}"
                    user_input_emb = cal_embedding(new_msg)
                    CHAT_INPUT_MESSAGES = make_message(user_input, user_input_emb, num_of_output)
                with st.spinner(i18n.t('lang.msg_gen_result')):
                    response_all = ""
                    temp_placeholder = st.empty()
                    stream = client.chat.completions.create(model=GPT_MODEL,messages=CHAT_INPUT_MESSAGES, temperature=0.0, stream=True)
                    for part in stream:
                        response_delta = (part.choices[0].delta.content or "")
                        response_all += response_delta
                        temp_placeholder.write(response_all)
                st.session_state.messages.append("---")
                st.session_state.messages.append(response_all)
                st.session_state.messages.append(user_input)
                temp_placeholder.empty() #Stream部分の非表示
                st.empty()
            except Exception as e:
                print(str(e))
                st.error(i18n.t('lang.error_message'))

    st.write("---")
    st.write(i18n.t('lang.label_results'))
    output_messages = ""
    for message in reversed(st.session_state.messages):
        st.write(message)
        output_messages += message + "\n\n"

    # 履歴のクリアボタン
    if st.button(i18n.t('lang.label_reset_button')):
        st.session_state.messages = []
        st.empty()
    
    st.download_button(i18n.t('lang.label_save_button'), output_messages)

def main():
    st.title("🔍 Accident Report Finder")
    language_selection = st.radio("Language", ("English", "日本語"), horizontal=True)
    if language_selection == "日本語":
        i18n.set('locale', 'ja')
    else:
        i18n.set('locale', 'en')

    st.caption(i18n.t('lang.caption_1'))
    st.caption(i18n.t('lang.caption_2'))
    st.write("---")
    st.sidebar.title("Accident Report Finder")
    with st.sidebar:
        st.write("Version: 1.2.1")
        st.write("Made by [Michio Fujii](https://github.com/michiof)")
        st.write("---")
        
        # 最大出力数の設定
        num_of_output = st.slider(i18n.t('lang.label_num_of_output'), 1, 5, 3)
        # filter設定
        label_filter_severity = i18n.t('lang.label_filter_severity')
        label_filter_cat = i18n.t('lang.label_filter_cat')
        filter_selection = st.multiselect(i18n.t('lang.label_filter_title'),
                                [label_filter_severity, label_filter_cat],
                                [label_filter_severity, label_filter_cat]
                            )
        converted_filter_selection = [text.replace(label_filter_severity,"Severity_2").replace(label_filter_cat, "Cat3") for text in filter_selection]
        make_pinecone_filter(converted_filter_selection)

    if "messages" not in st.session_state:
        st.session_state['messages']= []
    if 'sample_question' not in st.session_state:
        st.session_state['sample_question'] = ""

    chat_page(num_of_output)

if __name__ == "__main__":
    main()
