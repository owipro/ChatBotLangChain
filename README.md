# ChatGPT-like Chatbot with Streamlit & LangChain

A simple, user-friendly ChatGPT clone built with Streamlit and LangChain that connects to OpenAI's API.

## Features

✨ **Simple & Intuitive UI** - Clean chat interface with message history
🔐 **Secure API Key Input** - Enter your API key directly in the app (or via .env file)
⚙️ **Customizable Settings** - Choose model, adjust temperature, set max tokens
🧠 **Multiple Models** - Support for GPT-4o-mini, GPT-4o, and GPT-3.5-turbo
📝 **Full Chat History** - Maintain conversation context throughout your session
📡 **Streaming Responses** - Tokens appear live as the model generates them
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

3. **Set up your API key** (choose one method):

   **Option A: Using environment file (Recommended for local dev)**
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

   **Option B: Enter in the app**
   - Run the app and paste your API key in the sidebar text input

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

1. **Add your API Key**: Either in the `.env` file or in the sidebar text input
2. **Select your preferences**: Choose model, temperature, and max tokens in the sidebar
3. **Start chatting**: Type your message and press Enter
4. **Clear history**: Click "Clear Chat History" in the sidebar whenever you want to reset

## Configuration

### Model Selection
- **gpt-4o-mini**: Fast, low-cost, and a great default
- **gpt-4o**: Stronger reasoning and writing quality
- **gpt-3.5-turbo**: Legacy option if you already use it

### Temperature Settings
- **0.0** - Deterministic, focused responses (good for factual questions)
- **0.7** - Balanced (default, good for general use)
- **2.0** - Maximum randomness and creativity

### Max Tokens
- Controls the maximum length of responses
- Default: 2048 tokens
- Adjust based on your needs

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
- **langchain** - LLM orchestration library
- **langchain-openai** - OpenAI integration for LangChain
- **python-dotenv** - Environment variable management

## License

Free to use and modify for personal and commercial projects.

## Contributing

Feel free to fork and improve this project!

---

**Enjoy chatting! 🚀**
