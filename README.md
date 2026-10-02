# Oscar's Chatbot with Streamlit & LangChain

A simple, user-friendly chatbot built with Streamlit and LangChain that can connect to either OpenAI or a local Ollama model.

## Features

✨ **Simple & Intuitive UI** - Clean chat interface with message history
🔐 **Secure API Key Input** - Enter your API key directly in the app (or via .env file)
🏠 **Local LLM Support** - Switch to Ollama by entering a URL like `http://192.168.50.23:11434`
🔎 **Auto-Detected Ollama Models** - The app reads available local models from `/api/tags`
🗂️ **Persistent Chat History** - Chats are stored in a local SQLite database and can be continued later
✏️ **Rename Chats** - Give any saved chat a custom title
🔎 **Search Chats** - Search across saved chat titles and message content
📤 **Export / Import** - Back up chats to JSON and restore them later
⚙️ **Customizable Settings** - Choose model, adjust temperature, set max tokens
🧠 **Multiple Models** - Support for GPT-4o-mini, GPT-4o, GPT-3.5-turbo, and local Ollama models
📝 **Full Chat History** - Maintain conversation context throughout your session
📡 **Streaming Responses** - Tokens appear live as the model generates them
🧹 **Delete Chats** - Remove stored conversations whenever you want
🔒 **Private Chats** - Start a chat that stays in memory only and is never persisted
🧹 **Clear History** - One-click button to reset the conversation

## Installation

### Prerequisites
- Python 3.8 or higher
- OpenAI API key (get it from https://platform.openai.com/api-keys)

### Setup

1. **Clone or download this project**

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up your model access** (choose one method):

   **Option A: Using environment file (Recommended for local dev)**
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key and/or Ollama URL
   ```

   **Option B: Enter in the app**
   - Run the app and choose OpenAI or Ollama in the sidebar
   - For OpenAI, paste your API key
   - For Ollama, enter a URL ending in `:11434` and pick from the auto-detected model list

4. **(Optional) Use the PowerShell launcher**
   ```powershell
   .\start.ps1
   ```

   On Ubuntu Server, use the Bash launcher instead:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

   To run it as a background service on Ubuntu Server, install the systemd unit:
   ```bash
   sudo cp oscars-chatbot.service /etc/systemd/system/oscars-chatbot.service
   sudo tee /etc/default/oscars-chatbot >/dev/null <<'EOF'
   PROJECT_ROOT=/home/oscar/MyOtherProject
   EOF
   ```
   Update `User=` in the unit so it matches the Linux account that should run the app.
   Update `PROJECT_ROOT=` in `/etc/default/oscars-chatbot` if you clone the repo somewhere else.
   Then enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now oscars-chatbot.service
   sudo systemctl status oscars-chatbot.service
   ```
   View logs with:
   ```bash
   journalctl -u oscars-chatbot.service -f
   ```

5. **(Optional) Stop the chatbot**
   ```powershell
   .\Stop-Chatbot.ps1
   ```

   This writes a stop request file that the app watches, so it does not need any elevated privileges.

## Running the Application

```bash
streamlit run chatbot.py
```

The app will open in your browser at `http://localhost:8501`

On Ubuntu Server, `start.sh` binds Streamlit to `0.0.0.0:8501` so you can reach it from another machine.

## Usage

1. **Choose your provider**: OpenAI or Ollama in the sidebar
2. **Search or browse previous chats**: Use the search box to find a saved conversation, then open it from the list
3. **Rename, export, or delete chats**: Manage conversations from the sidebar controls
4. **Add your credentials**: OpenAI API key or Ollama URL ending in `:11434`
5. **Select your preferences**: Choose model, temperature, and max tokens in the sidebar
   - Ollama models are pulled automatically from the local Ollama server
   - Local Ollama defaults to a smaller token budget that is better for CPU inference, but you can raise the max much higher for longer answers
6. **Start chatting**: Type your message and press Enter
7. **Use private chat**: Click "Private" to keep a temporary, non-persisted conversation
8. **Export / import chats**: Back up your conversations to JSON and restore them later

## Configuration

### Model Selection
- **gpt-4o-mini**: Fast, low-cost, and a great default
- **gpt-4o**: Stronger reasoning and writing quality
- **gpt-3.5-turbo**: Legacy option if you already use it
- **qwen3:4b / llama3.2 / mistral / qwen2.5**: Example local models when using Ollama

### Temperature Settings
- **0.0** - Deterministic, focused responses (good for factual questions)
- **0.7** - Balanced (default, good for general use)
- **2.0** - Maximum randomness and creativity

### Max Tokens
- Controls the maximum length of responses
- Default: 2048 tokens
- Adjust based on your needs
- For Ollama, the app now defaults to a higher token budget to avoid truncated replies on local models
- The Ollama max token slider now goes up to 16384 for longer generations

### Chat Storage
- Saved chats are stored locally in `.streamlit/chat_history.sqlite3`
- Private chats are not written to disk
- You can continue, rename, search, delete, export, import, or start a fresh chat from the sidebar

### Ubuntu Server Notes
- Use `start.sh` to create/update the virtual environment and start Streamlit headless
- The launcher binds to `0.0.0.0:8501` for remote access
- You can also run the app under `systemd` by installing `oscars-chatbot.service`
- The service reads `PROJECT_ROOT` from `/etc/default/oscars-chatbot`

## Project Structure

```
├── chatbot.py          # Main Streamlit application
├── requirements.txt    # Python dependencies
├── start.ps1           # PowerShell launcher
├── start.sh            # Bash launcher for Ubuntu/Linux
├── oscars-chatbot.service # systemd service unit for Ubuntu Server
├── Stop-Chatbot.ps1    # PowerShell stop script
├── .gitignore          # Git ignore rules
├── .env.example       # Example environment file
└── README.md          # This file
```

## Security Notes

⚠️ **Never commit your `.env` file or API key to version control**

The `.env` file is loaded automatically if it exists, allowing you to store sensitive information locally without exposing it.

## Troubleshooting

### "Invalid API Key" Error
- Verify your API key is correct at https://platform.openai.com/api-keys
- Make sure your account has available credits

### "Model not found" Error
- Verify you have access to the selected model in your OpenAI account
- gpt-4 access may require joining a waitlist

### Slow Responses
- This is normal for gpt-4. Consider using gpt-3.5-turbo for faster responses
- Check your internet connection

## Dependencies

- **streamlit** - Web app framework
- **langchain-openai** - OpenAI integration for LangChain
- **requests** - HTTP client used for direct Ollama API calls
- **python-dotenv** - Environment variable management

## License

Free to use and modify for personal and commercial projects.

## Contributing

Feel free to fork and improve this project!

---

**Enjoy chatting! 🚀**
