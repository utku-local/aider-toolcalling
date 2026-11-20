"""The commands a user types to change chat mode, as one paragraph for the model's system prompt.
Measured on the 27B in ask mode: asked how to get back to agent mode, it advised `/model` and a `/mode` command
"if it exists in your version", because nothing in its prompt described the program it runs in.
The text names only commands that exist here and tells the model to point to /help for anything else.
"""

AGENT_MODE = "agent"
SESSION_COMMANDS_NOTE = """
The user talks to you inside Aider and types its slash commands at the same prompt. If they ask how to use it:
/agent switches to agent mode (you work through tools: read, edit, run commands), /ask switches to ask mode
(answers only, no changes) and /code to plain edit mode; with a request on the same line, each runs that one
request and then returns to the current mode. /chat-mode NAME switches to any mode, /model NAME changes the model,
/undo-agent restores the files the agent changed in its latest request, and /help lists every command. Never
invent a command or flag; if you are not sure one exists, say so and point to /help.
"""
