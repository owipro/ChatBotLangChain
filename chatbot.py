import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

import streamlit as st
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from streamlit.runtime.scriptrunner import get_script_run_ctx

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / ".streamlit"
STOP_REQUEST_FILE = DATA_DIR / "chatbot.stop"
CHAT_DB_FILE = DATA_DIR / "chat_history.sqlite3"

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "qwen3:4b"
DEFAULT_OPENAI_MAX_TOKENS = 2048
DEFAULT_OLLAMA_MAX_TOKENS = 256


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


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
    ensure_data_dir()
    if STOP_REQUEST_FILE.exists():
        try:
            STOP_REQUEST_FILE.unlink()
        except OSError:
            pass
    start_stop_watcher()

st.set_page_config(page_title="ChatGPT Clone", page_icon="💬", layout="wide")
st.title("💬 ChatGPT-like Chatbot")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_db_connection() -> sqlite3.Connection:
    ensure_data_dir()
    connection = sqlite3.connect(CHAT_DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def init_chat_db() -> None:
    with get_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                ollama_url TEXT,
                temperature REAL NOT NULL,
                max_tokens INTEGER NOT NULL,
                is_private INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id, id)")


def list_chats() -> list[sqlite3.Row]:
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, title, provider, model, ollama_url, temperature, max_tokens, is_private, created_at, updated_at
            FROM chats
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    return list(rows)


def load_chat(chat_id: str) -> tuple[sqlite3.Row | None, list[dict[str, str]]]:
    with get_db_connection() as connection:
        chat_row = connection.execute(
            """
            SELECT id, title, provider, model, ollama_url, temperature, max_tokens, is_private, created_at, updated_at
            FROM chats
            WHERE id = ?
            """,
            (chat_id,),
        ).fetchone()

        if chat_row is None:
            return None, []

        message_rows = connection.execute(
            """
            SELECT role, content
            FROM messages
            WHERE chat_id = ?
            ORDER BY id ASC
            """,
            (chat_id,),
        ).fetchall()

    messages = [{"role": row["role"], "content": row["content"]} for row in message_rows]
    return chat_row, messages


def create_chat(
    title: str,
    provider: str,
    model: str,
    ollama_url: str | None,
    temperature: float,
    max_tokens: int,
    is_private: bool,
) -> str:
    chat_id = f"chat-{int(time.time() * 1000)}-{os.getpid()}"
    timestamp = utc_now_iso()
    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO chats (
                id, title, provider, model, ollama_url, temperature, max_tokens, is_private, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                title,
                provider,
                model,
                ollama_url,
                temperature,
                max_tokens,
                1 if is_private else 0,
                timestamp,
                timestamp,
            ),
        )
    return chat_id


def update_chat_metadata(
    chat_id: str,
    title: str,
    provider: str,
    model: str,
    ollama_url: str | None,
    temperature: float,
    max_tokens: int,
) -> None:
    with get_db_connection() as connection:
        connection.execute(
            """
            UPDATE chats
            SET title = ?, provider = ?, model = ?, ollama_url = ?, temperature = ?, max_tokens = ?, updated_at = ?
            WHERE id = ?
            """,
            (title, provider, model, ollama_url, temperature, max_tokens, utc_now_iso(), chat_id),
        )


def save_message(chat_id: str, role: str, content: str) -> None:
    with get_db_connection() as connection:
        connection.execute(
            "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, utc_now_iso()),
        )
        connection.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?",
            (utc_now_iso(), chat_id),
        )


def delete_chat(chat_id: str) -> None:
    with get_db_connection() as connection:
        connection.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        connection.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


def derive_chat_title(prompt: str) -> str:
    clean = " ".join(prompt.strip().split())
    if not clean:
        return "Untitled chat"
    if len(clean) <= 48:
        return clean
    return clean[:45].rstrip() + "..."


def ensure_session_defaults() -> None:
    defaults = {
        "messages": [],
        "chat_mode": "existing",
        "current_chat_id": None,
        "current_chat_title": None,
        "provider": "OpenAI",
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "ollama_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "ollama_model": DEFAULT_OLLAMA_MODEL,
        "temperature": 0.7,
        "max_tokens": DEFAULT_OPENAI_MAX_TOKENS,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_to_new_chat(private: bool) -> None:
    st.session_state.chat_mode = "private" if private else "new"
    st.session_state.current_chat_id = None
    st.session_state.current_chat_title = "Private chat" if private else "New chat"
    st.session_state.messages = []


def load_chat_into_state(chat_row: sqlite3.Row, messages: list[dict[str, str]]) -> None:
    st.session_state.chat_mode = "existing"
    st.session_state.current_chat_id = chat_row["id"]
    st.session_state.current_chat_title = chat_row["title"]
    st.session_state.selected_chat_id = chat_row["id"]
    st.session_state.provider = chat_row["provider"]
    st.session_state.temperature = float(chat_row["temperature"])
    st.session_state.max_tokens = int(chat_row["max_tokens"])
    st.session_state.messages = messages

    if chat_row["provider"] == "Ollama":
        st.session_state.ollama_url = chat_row["ollama_url"] or st.session_state.ollama_url
        st.session_state.ollama_model = chat_row["model"]
    else:
        st.session_state.openai_api_key = st.session_state.openai_api_key or os.getenv("OPENAI_API_KEY", "")


def build_messages(chat_history: list[dict[str, str]]) -> list[HumanMessage | AIMessage]:
    return [
        HumanMessage(content=msg["content"]) if msg["role"] == "user" else AIMessage(content=msg["content"])
        for msg in chat_history
    ]


def stream_response(llm: BaseChatModel, messages: list[HumanMessage | AIMessage]) -> Iterable[str]:
    for chunk in llm.stream(messages):
        if chunk.content:
            yield chunk.content


def validate_ollama_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.port != 11434:
        raise ValueError("Ollama URL must be a valid http(s) URL ending in :11434, such as http://localhost:11434.")
    return url.rstrip("/")


@st.cache_data(ttl=30)
def fetch_ollama_models(ollama_url: str) -> list[str]:
    request_url = ollama_url.rstrip("/") + "/api/tags"
    try:
        with urlopen(request_url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"Could not load Ollama models from {request_url}: {exc}") from exc

    models: list[str] = []
    for item in payload.get("models", []):
        name = item.get("name")
        if name:
            models.append(name)

    return sorted(models)


def format_chat_label(chat_row: sqlite3.Row) -> str:
    updated = chat_row["updated_at"].replace("T", " ").replace("Z", "")
    private_suffix = " · private" if chat_row["is_private"] else ""
    return f"{chat_row['title']} · {chat_row['provider']} · {chat_row['model']}{private_suffix} · {updated[:16]}"


init_chat_db()
ensure_session_defaults()

persisted_chats = list_chats()
if st.session_state.chat_mode == "existing" and not st.session_state.current_chat_id and persisted_chats:
    load_chat_into_state(persisted_chats[0], load_chat(persisted_chats[0]["id"])[1])

if st.session_state.chat_mode == "existing" and st.session_state.current_chat_id:
    chat_row, loaded_messages = load_chat(st.session_state.current_chat_id)
    if chat_row is None:
        reset_to_new_chat(private=False)
    elif st.session_state.messages == [] and loaded_messages:
        load_chat_into_state(chat_row, loaded_messages)

with st.sidebar:
    st.header("Chats")

    persisted_chats = list_chats()
    if persisted_chats:
        if st.session_state.chat_mode == "existing":
            chat_ids = [row["id"] for row in persisted_chats]
            labels = {row["id"]: format_chat_label(row) for row in persisted_chats}
            default_index = 0
            if st.session_state.current_chat_id in chat_ids:
                default_index = chat_ids.index(st.session_state.current_chat_id)

            selected_chat_id = st.selectbox(
                "Previous chats",
                options=chat_ids,
                index=default_index,
                format_func=lambda chat_id: labels.get(chat_id, chat_id),
                key="selected_chat_id",
            )

            if selected_chat_id != st.session_state.current_chat_id:
                selected_chat, selected_messages = load_chat(selected_chat_id)
                if selected_chat is not None:
                    load_chat_into_state(selected_chat, selected_messages)
                    st.rerun()
        else:
            st.caption("Click 'Continue existing' to browse previous chats.")
    else:
        st.caption("No saved chats yet.")

    chat_actions = st.columns(3)
    if chat_actions[0].button("Continue existing", use_container_width=True):
        if persisted_chats:
            selected_chat, selected_messages = load_chat(persisted_chats[0]["id"])
            if selected_chat is not None:
                load_chat_into_state(selected_chat, selected_messages)
        else:
            st.session_state.chat_mode = "new"
            st.session_state.messages = []
            st.session_state.current_chat_id = None
            st.session_state.current_chat_title = "New chat"
        st.rerun()

    if chat_actions[1].button("New chat", use_container_width=True):
        reset_to_new_chat(private=False)
        st.rerun()

    if chat_actions[2].button("Private", use_container_width=True):
        reset_to_new_chat(private=True)
        st.rerun()

    if st.session_state.chat_mode == "existing" and st.session_state.current_chat_id:
        if st.button("Delete current chat", use_container_width=True):
            delete_chat(st.session_state.current_chat_id)
            reset_to_new_chat(private=False)
            st.rerun()

    st.divider()
    st.header("Settings")

    provider = st.radio("LLM Provider", ["OpenAI", "Ollama"], horizontal=True, index=0 if st.session_state.provider == "OpenAI" else 1)
    st.session_state.provider = provider

    if provider == "OpenAI":
        api_key = st.text_input(
            "Enter your OpenAI API Key:",
            type="password",
            value=st.session_state.openai_api_key,
        )
        st.session_state.openai_api_key = api_key

        if not api_key:
            st.warning("Please enter your OpenAI API Key to continue.")

        model = st.selectbox("Select Model:", ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"], index=0)
        max_tokens_default = st.session_state.get("max_tokens_openai", DEFAULT_OPENAI_MAX_TOKENS)
        max_tokens_max = 4096
    else:
        api_key = ""
        ollama_url = st.text_input(
            "Ollama URL (must end with :11434):",
            value=st.session_state.ollama_url,
        )
        st.session_state.ollama_url = ollama_url

        ollama_url_valid = False
        ollama_models: list[str] = []
        try:
            ollama_url = validate_ollama_url(ollama_url)
            ollama_url_valid = True
        except ValueError as exc:
            st.error(str(exc))

        if ollama_url_valid:
            try:
                ollama_models = fetch_ollama_models(ollama_url)
            except RuntimeError as exc:
                st.error(str(exc))

        if ollama_models:
            current_model = st.session_state.ollama_model if st.session_state.ollama_model in ollama_models else ollama_models[0]
            model = st.selectbox("Ollama Model", ollama_models, index=ollama_models.index(current_model))
        else:
            model = st.text_input("Ollama Model", value=st.session_state.ollama_model or DEFAULT_OLLAMA_MODEL)
            st.caption("No Ollama models were detected. Enter a local model name manually.")

        st.session_state.ollama_model = model
        st.caption("Auto-detected from /api/tags. Example local models: qwen3:4b, llama3.2, mistral, qwen2.5")
        max_tokens_default = st.session_state.get("max_tokens_ollama", DEFAULT_OLLAMA_MAX_TOKENS)
        max_tokens_max = 1024

    temperature = st.slider(
        "Temperature:",
        min_value=0.0,
        max_value=2.0,
        value=float(st.session_state.temperature),
        step=0.1,
        help="Lower = more focused, Higher = more creative",
    )
    st.session_state.temperature = float(temperature)

    max_tokens = st.number_input(
        "Max Tokens:",
        min_value=32,
        max_value=max_tokens_max,
        value=int(max_tokens_default),
        step=32 if provider == "Ollama" else 100,
    )
    st.session_state.max_tokens = int(max_tokens)

    if provider == "OpenAI":
        st.session_state.max_tokens_openai = int(max_tokens)
    else:
        st.session_state.max_tokens_ollama = int(max_tokens)

if st.session_state.chat_mode == "existing" and st.session_state.current_chat_title:
    st.subheader(st.session_state.current_chat_title)
elif st.session_state.chat_mode == "private":
    st.subheader("Private chat")
    st.caption("This chat is not persisted.")
else:
    st.subheader("New chat")
    st.caption("This chat will be saved once you send the first message.")

chat: BaseChatModel | None = None
chat_ready = False

if provider == "OpenAI" and st.session_state.openai_api_key:
    chat = ChatOpenAI(
        api_key=st.session_state.openai_api_key,
        model=model,
        temperature=temperature,
        max_tokens=int(max_tokens),
    )
    chat_ready = True
elif provider == "Ollama":
    try:
        validated_ollama_url = validate_ollama_url(st.session_state.ollama_url)
    except ValueError:
        validated_ollama_url = None
    else:
        chat = ChatOllama(
            base_url=validated_ollama_url,
            model=model,
            temperature=temperature,
            num_predict=int(max_tokens),
        )
        chat_ready = True

if chat_ready:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_input := st.chat_input("What would you like to know?"):
        st.session_state.messages.append({"role": "user", "content": user_input})

        if st.session_state.chat_mode != "private":
            if st.session_state.current_chat_id is None:
                new_chat_title = derive_chat_title(user_input)
                ollama_url_for_chat = st.session_state.ollama_url if provider == "Ollama" else None
                st.session_state.current_chat_id = create_chat(
                    title=new_chat_title,
                    provider=provider,
                    model=model,
                    ollama_url=ollama_url_for_chat,
                    temperature=float(temperature),
                    max_tokens=int(max_tokens),
                    is_private=False,
                )
                st.session_state.current_chat_title = new_chat_title
                st.session_state.chat_mode = "existing"

            update_chat_metadata(
                st.session_state.current_chat_id,
                st.session_state.current_chat_title or derive_chat_title(user_input),
                provider,
                model,
                st.session_state.ollama_url if provider == "Ollama" else None,
                float(temperature),
                int(max_tokens),
            )
            save_message(st.session_state.current_chat_id, "user", user_input)

        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            messages = build_messages(st.session_state.messages)
            assistant_message = st.write_stream(stream_response(chat, messages))
            st.session_state.messages.append({"role": "assistant", "content": assistant_message})

        if st.session_state.chat_mode != "private" and st.session_state.current_chat_id:
            save_message(st.session_state.current_chat_id, "assistant", assistant_message)
            update_chat_metadata(
                st.session_state.current_chat_id,
                st.session_state.current_chat_title or derive_chat_title(user_input),
                provider,
                model,
                st.session_state.ollama_url if provider == "Ollama" else None,
                float(temperature),
                int(max_tokens),
            )
else:
    if provider == "OpenAI":
        st.info("👈 Please enter your OpenAI API Key in the sidebar to start chatting.")
    else:
        st.info("👈 Enter a valid Ollama URL ending in :11434 and a local model name to start chatting.")
