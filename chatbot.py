import os
import threading
import time
from typing import Iterable
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from streamlit.runtime.scriptrunner import get_script_run_ctx

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
STOP_REQUEST_FILE = PROJECT_ROOT / ".streamlit" / "chatbot.stop"


def _watch_for_stop_request() -> None:
    while True:
        if STOP_REQUEST_FILE.exists():
            try:
                STOP_REQUEST_FILE.unlink()
            except OSError:
                pass
            os._exit(0)
        time.sleep(1)


@st.cache_resource
def start_stop_watcher() -> bool:
    thread = threading.Thread(target=_watch_for_stop_request, daemon=True)
    thread.start()
    return True


if get_script_run_ctx() is not None:
    if STOP_REQUEST_FILE.exists():
        try:
            STOP_REQUEST_FILE.unlink()
        except OSError:
            pass

    start_stop_watcher()

st.set_page_config(page_title="ChatGPT Clone", page_icon="💬", layout="wide")
st.title("💬 ChatGPT-like Chatbot")


def build_messages(chat_history: list[dict[str, str]]) -> list[HumanMessage | AIMessage]:
    return [
        HumanMessage(content=msg["content"]) if msg["role"] == "user" else AIMessage(content=msg["content"])
        for msg in chat_history
    ]


def stream_response(llm: ChatOpenAI, messages: list[HumanMessage | AIMessage]) -> Iterable[str]:
    for chunk in llm.stream(messages):
        if chunk.content:
            yield chunk.content


with st.sidebar:
    st.header("Settings")
    
    api_key = st.text_input(
        "Enter your OpenAI API Key:",
        type="password",
        value=os.getenv("OPENAI_API_KEY", "")
    )
    
    if not api_key:
        st.warning("Please enter your OpenAI API Key to continue.")
    
    model = st.selectbox("Select Model:", ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"], index=0)
    
    temperature = st.slider(
        "Temperature:",
        min_value=0.0,
        max_value=2.0,
        value=0.7,
        step=0.1,
        help="Lower = more focused, Higher = more creative"
    )
    
    max_tokens = st.number_input("Max Tokens:", min_value=100, max_value=4096, value=2048, step=100)
    
    if st.button("Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.success("Chat history cleared!")

if "messages" not in st.session_state:
    st.session_state.messages = []

if api_key:
    chat = ChatOpenAI(
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_input := st.chat_input("What would you like to know?"):
        st.session_state.messages.append({"role": "user", "content": user_input})

        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            messages = build_messages(st.session_state.messages)
            assistant_message = st.write_stream(stream_response(chat, messages))
            st.session_state.messages.append({"role": "assistant", "content": assistant_message})
else:
    st.info("👈 Please enter your OpenAI API Key in the sidebar to start chatting.")
