import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
import requests
from streamlit.runtime.scriptrunner import get_script_run_ctx

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / ".streamlit"
STOP_REQUEST_FILE = DATA_DIR / "chatbot.stop"
CHAT_DB_FILE = DATA_DIR / "chat_history.sqlite3"

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "qwen3:4b"
DEFAULT_OPENAI_MAX_TOKENS = 2048
DEFAULT_OLLAMA_MAX_TOKENS = 4096


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

st.set_page_config(page_title="Oscar's Chatbot", page_icon="💬", layout="wide")
st.title("💬 Oscar's Chatbot")


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
    chat_id = f"chat-{int(time.time() * 1000)}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
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


def rename_chat(chat_id: str, new_title: str) -> None:
    with get_db_connection() as connection:
        connection.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
            (new_title.strip() or "Untitled chat", utc_now_iso(), chat_id),
        )


def derive_chat_title(prompt: str) -> str:
    clean = " ".join(prompt.strip().split())
    if not clean:
        return "Untitled chat"
    if len(clean) <= 48:
        return clean
    return clean[:45].rstrip() + "..."


def chat_to_payload(chat_row: sqlite3.Row, messages: list[dict[str, str]]) -> dict[str, object]:
    return {
        "id": chat_row["id"],
        "title": chat_row["title"],
        "provider": chat_row["provider"],
        "model": chat_row["model"],
        "ollama_url": chat_row["ollama_url"],
        "temperature": chat_row["temperature"],
        "max_tokens": chat_row["max_tokens"],
        "is_private": bool(chat_row["is_private"]),
        "created_at": chat_row["created_at"],
        "updated_at": chat_row["updated_at"],
        "messages": messages,
    }


def serialize_chat_payload(chat_row: sqlite3.Row, messages: list[dict[str, str]]) -> str:
    payload = {
        "app": "Oscar's Chatbot",
        "version": 1,
        "exported_at": utc_now_iso(),
        "chats": [chat_to_payload(chat_row, messages)],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def serialize_all_chats_payload(chat_ids: list[str] | None = None) -> str:
    selected_chat_ids = chat_ids if chat_ids is not None else [row["id"] for row in list_chats()]
    chats: list[dict[str, object]] = []
    for chat_id in selected_chat_ids:
        chat_row, messages = load_chat(chat_id)
        if chat_row is not None:
            chats.append(chat_to_payload(chat_row, messages))
    payload = {
        "app": "Oscar's Chatbot",
        "version": 1,
        "exported_at": utc_now_iso(),
        "chats": chats,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def serialize_current_session_payload() -> str:
    payload = {
        "app": "Oscar's Chatbot",
        "version": 1,
        "exported_at": utc_now_iso(),
        "chats": [
            {
                "id": st.session_state.current_chat_id or f"session-{uuid.uuid4().hex[:8]}",
                "title": st.session_state.current_chat_title or "Untitled chat",
                "provider": st.session_state.provider,
                "model": st.session_state.ollama_model if st.session_state.provider == "Ollama" else st.session_state.openai_model,
                "ollama_url": st.session_state.ollama_url if st.session_state.provider == "Ollama" else None,
                "temperature": float(st.session_state.temperature),
                "max_tokens": int(st.session_state.max_tokens),
                "is_private": st.session_state.chat_mode == "private",
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
                "messages": st.session_state.messages,
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def import_chat_record(chat_data: dict[str, object]) -> str:
    messages = chat_data.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    original_id = str(chat_data.get("id") or "")
    candidate_id = original_id or f"chat-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

    with get_db_connection() as connection:
        existing = connection.execute("SELECT 1 FROM chats WHERE id = ?", (candidate_id,)).fetchone()
        if existing is not None:
            candidate_id = f"{candidate_id}-{uuid.uuid4().hex[:8]}"

        title = str(chat_data.get("title") or "").strip()
        if not title:
            first_user_message = next(
                (str(message.get("content", "")) for message in messages if isinstance(message, dict) and message.get("role") == "user"),
                "",
            )
            title = derive_chat_title(first_user_message) if first_user_message else "Imported chat"

        provider = str(chat_data.get("provider") or "OpenAI")
        model = str(chat_data.get("model") or DEFAULT_OPENAI_MODEL)
        ollama_url = chat_data.get("ollama_url")
        ollama_url_value = str(ollama_url) if ollama_url else None
        temperature = float(chat_data.get("temperature") or 0.7)
        max_tokens = int(chat_data.get("max_tokens") or DEFAULT_OPENAI_MAX_TOKENS)
        is_private = False
        created_at = str(chat_data.get("created_at") or utc_now_iso())
        updated_at = str(chat_data.get("updated_at") or created_at)

        connection.execute(
            """
            INSERT INTO chats (
                id, title, provider, model, ollama_url, temperature, max_tokens, is_private, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                title,
                provider,
                model,
                ollama_url_value,
                temperature,
                max_tokens,
                1 if is_private else 0,
                created_at,
                updated_at,
            ),
        )

        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "assistant")
            content = str(message.get("content") or "")
            created = str(message.get("created_at") or utc_now_iso())
            connection.execute(
                "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (candidate_id, role, content, created),
            )

    return candidate_id


def import_chats_from_payload(payload: dict[str, object]) -> list[str]:
    chats = payload.get("chats")
    if not isinstance(chats, list):
        chats = [payload]

    imported_chat_ids: list[str] = []
    for chat_data in chats:
        if isinstance(chat_data, dict):
            imported_chat_ids.append(import_chat_record(chat_data))

    return imported_chat_ids


def search_chats(query: str) -> list[sqlite3.Row]:
    cleaned = query.strip().lower()
    if not cleaned:
        return list_chats()

    like_pattern = f"%{cleaned}%"
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT c.id, c.title, c.provider, c.model, c.ollama_url, c.temperature, c.max_tokens, c.is_private, c.created_at, c.updated_at
            FROM chats c
            LEFT JOIN messages m ON m.chat_id = c.id
            WHERE lower(c.title) LIKE ?
               OR lower(c.provider) LIKE ?
               OR lower(c.model) LIKE ?
               OR lower(coalesce(c.ollama_url, '')) LIKE ?
               OR lower(coalesce(m.content, '')) LIKE ?
            ORDER BY c.updated_at DESC, c.created_at DESC
            """,
            (like_pattern, like_pattern, like_pattern, like_pattern, like_pattern),
        ).fetchall()
    return list(rows)


def export_chat_filename(title: str, suffix: str = "json") -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in title.strip().lower())
    safe = "-".join(part for part in safe.split("-") if part)
    if not safe:
        safe = "chat-export"
    return f"{safe[:48]}.{suffix}"


def get_current_chat_export_json() -> str:
    if st.session_state.current_chat_id and not st.session_state.current_chat_is_private:
        chat_row, messages = load_chat(st.session_state.current_chat_id)
        if chat_row is not None:
            return serialize_chat_payload(chat_row, messages)

    return serialize_current_session_payload()


def ensure_session_defaults() -> None:
    defaults = {
        "messages": [],
        "chat_mode": "existing",
        "current_chat_id": None,
        "current_chat_title": None,
        "current_chat_is_private": False,
        "provider": "OpenAI",
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "openai_model": DEFAULT_OPENAI_MODEL,
        "ollama_url": os.getenv("OLLAMA_BASE_URL", "http://192.168.50.23:11434"),
        "ollama_model": DEFAULT_OLLAMA_MODEL,
        "temperature": 0.7,
        "max_tokens": DEFAULT_OPENAI_MAX_TOKENS,
        "chat_search_query": "",
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_to_new_chat(private: bool) -> None:
    st.session_state.chat_mode = "private" if private else "new"
    st.session_state.current_chat_id = None
    st.session_state.current_chat_title = "Private chat" if private else "New chat"
    st.session_state.current_chat_is_private = private
    st.session_state.messages = []


def load_chat_into_state(chat_row: sqlite3.Row, messages: list[dict[str, str]]) -> None:
    st.session_state.chat_mode = "existing"
    st.session_state.current_chat_id = chat_row["id"]
    st.session_state.current_chat_title = chat_row["title"]
    st.session_state.current_chat_is_private = bool(chat_row["is_private"])
    st.session_state.sidebar_chat_selector = chat_row["id"]
    st.session_state.selected_chat_id = chat_row["id"]
    st.session_state.provider = chat_row["provider"]
    st.session_state.temperature = float(chat_row["temperature"])
    st.session_state.max_tokens = int(chat_row["max_tokens"])
    st.session_state.messages = messages

    if chat_row["provider"] == "Ollama":
        st.session_state.ollama_url = chat_row["ollama_url"] or st.session_state.ollama_url
        st.session_state.ollama_model = chat_row["model"]
    else:
        st.session_state.openai_model = chat_row["model"]
        st.session_state.openai_api_key = st.session_state.openai_api_key or os.getenv("OPENAI_API_KEY", "")


def build_messages(chat_history: list[dict[str, str]]) -> list[HumanMessage | AIMessage]:
    return [
        HumanMessage(content=msg["content"]) if msg["role"] == "user" else AIMessage(content=msg["content"])
        for msg in chat_history
    ]


def stream_openai_response(llm: ChatOpenAI, messages: list[HumanMessage | AIMessage]) -> Iterable[str]:
    yielded_any = False
    for chunk in llm.stream(messages):
        content = getattr(chunk, "content", "")
        if content:
            yielded_any = True
            yield str(content)

    if not yielded_any:
        response = llm.invoke(messages)
        content = getattr(response, "content", "")
        if content:
            yield str(content)


def message_list_to_ollama_payload(messages: list[HumanMessage | AIMessage]) -> list[dict[str, str]]:
    payload_messages: list[dict[str, str]] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            role = "user"
        else:
            role = "assistant"
        payload_messages.append({"role": role, "content": str(message.content)})
    return payload_messages


def stream_ollama_response(
    ollama_url: str,
    model: str,
    messages: list[HumanMessage | AIMessage],
    temperature: float,
    max_tokens: int,
) -> Iterable[str]:
    payload = {
        "model": model,
        "messages": message_list_to_ollama_payload(messages),
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    yielded_any = False
    with requests.post(
        ollama_url.rstrip("/") + "/api/chat",
        json=payload,
        stream=True,
        timeout=300,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            chunk = json.loads(line)
            content = chunk.get("message", {}).get("content", "")
            if content:
                yielded_any = True
                yield str(content)
            if chunk.get("done"):
                break

    if not yielded_any:
        fallback_response = requests.post(
            ollama_url.rstrip("/") + "/api/chat",
            json={**payload, "stream": False},
            timeout=300,
        )
        fallback_response.raise_for_status()
        fallback_data = fallback_response.json()
        content = fallback_data.get("message", {}).get("content", "")
        if not content:
            thinking = fallback_data.get("message", {}).get("thinking", "")
            if thinking:
                content = thinking
        if content:
            yield str(content)


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


def sync_rename_input_state() -> str:
    rename_widget_key = "chat_rename_input_" + (st.session_state.current_chat_id or st.session_state.chat_mode)
    current_title = st.session_state.current_chat_title or ""
    if st.session_state.get(rename_widget_key) != current_title:
        st.session_state[rename_widget_key] = current_title
    return rename_widget_key


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

rename_widget_key = sync_rename_input_state()

with st.sidebar:
    st.header("Chats")

    st.text_input(
        "Search saved chats",
        key="chat_search_query",
        placeholder="Search titles or message text",
    )
    persisted_chats = search_chats(st.session_state.chat_search_query)

    selected_chat_id = None
    if persisted_chats:
        st.caption(f"{len(persisted_chats)} saved chat(s) found.")
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
            key="sidebar_chat_selector",
        )
        if st.button("Open selected chat", use_container_width=True):
            selected_chat, selected_messages = load_chat(selected_chat_id)
            if selected_chat is not None:
                load_chat_into_state(selected_chat, selected_messages)
                st.rerun()
    else:
        if st.session_state.chat_search_query.strip():
            st.caption("No saved chats matched your search.")
        else:
            st.caption("No saved chats yet.")

    chat_actions = st.columns(3)
    if chat_actions[0].button("New chat", use_container_width=True):
        reset_to_new_chat(private=False)
        st.rerun()

    if chat_actions[1].button("Private", use_container_width=True):
        reset_to_new_chat(private=True)
        st.rerun()

    delete_disabled = not (st.session_state.current_chat_id and not st.session_state.current_chat_is_private)
    if chat_actions[2].button("Delete", use_container_width=True, disabled=delete_disabled):
        if st.session_state.current_chat_id:
            delete_chat(st.session_state.current_chat_id)
        reset_to_new_chat(private=False)
        st.rerun()

    can_rename = st.session_state.current_chat_is_private or bool(st.session_state.current_chat_id)
    with st.form("rename_chat_form", clear_on_submit=False):
        rename_value = st.text_input(
            "Rename current chat",
            key=rename_widget_key,
            disabled=not can_rename,
            placeholder="Enter a new chat title",
        )
        rename_submitted = st.form_submit_button("Save title", disabled=not can_rename)

    if rename_submitted:
        new_title = rename_value.strip()
        if not new_title:
            st.error("Please enter a non-empty title.")
        else:
            st.session_state.current_chat_title = new_title
            st.session_state[rename_widget_key] = new_title
            if st.session_state.current_chat_is_private:
                st.session_state.chat_mode = "private"
            elif st.session_state.current_chat_id:
                rename_chat(st.session_state.current_chat_id, new_title)
            st.success("Chat title updated.")
            st.rerun()

    st.divider()
    with st.expander("Export / import chats", expanded=False):
        current_chat_title = st.session_state.current_chat_title or "chat"
        current_export_json = get_current_chat_export_json()
        st.download_button(
            "Export current chat",
            data=current_export_json,
            file_name=export_chat_filename(current_chat_title),
            mime="application/json",
            use_container_width=True,
        )
        st.download_button(
            "Export all chats",
            data=serialize_all_chats_payload(),
            file_name="oscars-chatbot-export.json",
            mime="application/json",
            use_container_width=True,
        )

        import_file = st.file_uploader("Import chats from JSON", type=["json"], accept_multiple_files=False)
        if st.button("Import selected file", use_container_width=True, disabled=import_file is None):
            try:
                imported_payload = json.loads(import_file.getvalue().decode("utf-8"))
                imported_chat_ids = import_chats_from_payload(imported_payload)
                if imported_chat_ids:
                    imported_chat, imported_messages = load_chat(imported_chat_ids[0])
                    if imported_chat is not None:
                        load_chat_into_state(imported_chat, imported_messages)
                    st.success(f"Imported {len(imported_chat_ids)} chat(s).")
                    st.rerun()
                else:
                    st.warning("No chats were found in the selected file.")
            except Exception as exc:
                st.error(f"Could not import chats: {exc}")

    st.divider()
    st.header("Settings")

    provider = st.radio("LLM Provider", ["OpenAI", "Ollama"], horizontal=True, index=0 if st.session_state.provider == "OpenAI" else 1)
    st.session_state.provider = provider

    if provider == "OpenAI":
        openai_models = [DEFAULT_OPENAI_MODEL, "gpt-4o", "gpt-3.5-turbo"]
        current_openai_model = st.session_state.openai_model if st.session_state.openai_model in openai_models else DEFAULT_OPENAI_MODEL
        api_key = st.text_input(
            "Enter your OpenAI API Key:",
            type="password",
            value=st.session_state.openai_api_key,
        )
        st.session_state.openai_api_key = api_key

        if not api_key:
            st.warning("Please enter your OpenAI API Key to continue.")

        model = st.selectbox("Select Model:", openai_models, index=openai_models.index(current_openai_model))
        st.session_state.openai_model = model
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
        max_tokens_default = max(st.session_state.get("max_tokens_ollama", DEFAULT_OLLAMA_MAX_TOKENS), DEFAULT_OLLAMA_MAX_TOKENS)
        max_tokens_max = 16384

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
        step=128 if provider == "Ollama" else 100,
    )
    st.session_state.max_tokens = int(max_tokens)

    if provider == "OpenAI":
        st.session_state.max_tokens_openai = int(max_tokens)
    else:
        st.session_state.max_tokens_ollama = int(max_tokens)

if st.session_state.chat_mode == "existing" and st.session_state.current_chat_title:
    st.subheader(st.session_state.current_chat_title)
elif st.session_state.chat_mode == "private":
    st.subheader(st.session_state.current_chat_title or "Private chat")
    st.caption("This chat is not persisted.")
else:
    st.subheader("New chat")
    st.caption("This chat will be saved once you send the first message.")

chat: ChatOpenAI | None = None
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
        chat_ready = True
    except ValueError:
        validated_ollama_url = None

if chat_ready:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_input := st.chat_input("What would you like to know?"):
        st.session_state.messages.append({"role": "user", "content": user_input})

        if st.session_state.current_chat_title in {None, "New chat", "Private chat", "Untitled chat"}:
            derived_title = derive_chat_title(user_input)
            st.session_state.current_chat_title = derived_title
            if st.session_state.current_chat_is_private:
                st.session_state.chat_mode = "private"

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
            try:
                if provider == "OpenAI" and chat is not None:
                    assistant_message = st.write_stream(stream_openai_response(chat, messages))
                elif provider == "Ollama" and validated_ollama_url:
                    assistant_message = st.write_stream(
                        stream_ollama_response(
                        validated_ollama_url,
                        model,
                        messages,
                        float(temperature),
                        int(max_tokens),
                    )
                    )
                else:
                    assistant_message = ""
            except Exception as exc:
                st.error(f"Chat model error: {exc}")
                assistant_message = ""

            if not assistant_message:
                st.error("The model returned an empty response. Check the selected model and server availability.")
            else:
                st.session_state.messages.append({"role": "assistant", "content": assistant_message})

        if assistant_message and st.session_state.chat_mode != "private" and st.session_state.current_chat_id:
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
