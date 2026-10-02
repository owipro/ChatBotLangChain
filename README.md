# ChatGPT-like Chatbot with Streamlit & LangChain

A simple, user-friendly ChatGPT clone built with Streamlit and LangChain that can connect to either OpenAI or a local Ollama model.

## Features

✨ **Simple & Intuitive UI** - Clean chat interface with message history
🔐 **Secure API Key Input** - Enter your API key directly in the app (or via .env file)
🏠 **Local LLM Support** - Switch to Ollama by entering a URL like `http://localhost:11434`
🔎 **Auto-Detected Ollama Models** - The app reads available local models from `/api/tags`
🗂️ **Persistent Chat History** - Chats are stored in a local SQLite database and can be continued later
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

## Usage

1. **Choose your provider**: OpenAI or Ollama in the sidebar
2. **Browse previous chats**: Select a saved conversation to continue it
3. **Add your credentials**: OpenAI API key or Ollama URL ending in `:11434`
4. **Select your preferences**: Choose model, temperature, and max tokens in the sidebar
   - Ollama models are pulled automatically from the local Ollama server
   - Local Ollama defaults to a smaller token budget that is better for CPU inference
5. **Start chatting**: Type your message and press Enter
6. **Use private chat**: Click "Private" to keep a temporary, non-persisted conversation
7. **Delete chats**: Remove any saved conversation from the sidebar

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

### Chat Storage
- Saved chats are stored locally in `.streamlit/chat_history.sqlite3`
- Private chats are not written to disk
- You can continue, delete, or start a fresh chat from the sidebar

## Project Structure

```
├── chatbot.py          # Main Streamlit application
├── requirements.txt    # Python dependencies
├── start.ps1           # PowerShell launcher
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
- **langchain-ollama** - Ollama integration for LangChain
- **python-dotenv** - Environment variable management

## License

Free to use and modify for personal and commercial projects.

## Contributing

Feel free to fork and improve this project!

---

**Enjoy chatting! 🚀**
