import gradio as gr
from implementation.answer import answer_question_improved

theme = gr.themes.Soft(
    primary_hue=gr.themes.colors.amber,
    secondary_hue=gr.themes.colors.slate,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
).set(
    body_background_fill="#090e17",
    body_background_fill_dark="#090e17",
    background_fill_primary="#121b2b",
    background_fill_secondary="#090e17",
    button_primary_background_fill="#f59e0b",
    button_primary_background_fill_hover="#d97706",
    button_primary_text_color="#ffffff",
    button_secondary_background_fill="#1e293b",
    button_secondary_text_color="#f8fafc",
    body_text_color="#e2e8f0",
    block_background_fill="#121b2b",
    block_border_color="#1e293b",
    block_label_text_color="#f59e0b",
    block_title_text_color="#f1f5f9",
    block_radius="20px",
    input_background_fill="#0f1724",
    input_border_color="#1e293b",
)


custom_css = """
/* Smooth fonts and layout resets */
* { -webkit-font-smoothing: antialiased; }
.gradio-container { max-width: 920px !important; margin: auto !important; padding-top: 30px !important; }
footer, .footer, #component-0 > div:last-child a { display: none !important; }

/* Header Styling */
#app-header {
    text-align: center;
    padding: 10px 20px 30px 20px;
    margin-bottom: 10px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
#app-header h1 {
    font-size: 34px;
    font-weight: 800;
    background: linear-gradient(135deg, #f59e0b, #fbbf24);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0;
    letter-spacing: -0.5px;
}
#app-header p {
    color: #94a3b8;
    font-size: 15px;
    margin-top: 10px;
    font-weight: 400;
}

/* Chat Window */
#chat-window {
    border-radius: 20px !important;
    border: 1px solid #1e293b !important;
    background-color: #121b2b !important;
    box-shadow: 0 12px 40px -10px rgba(0, 0, 0, 0.6);
    overflow: hidden;
}

/* Message Bubbles */
.message-wrap .message.user {
    background: linear-gradient(135deg, #f59e0b, #d97706) !important;
    color: #ffffff !important;
    border-radius: 20px 20px 4px 20px !important;
    font-weight: 500;
    box-shadow: 0 4px 15px rgba(245, 158, 11, 0.25);
    padding: 14px 20px !important;
    border: none !important;
}
.message-wrap .message.bot {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    border-radius: 20px 20px 20px 4px !important;
    color: #f8fafc !important;
    padding: 14px 20px !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

/* Quick Chips (Suggestion Buttons) */
.quick-chip {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    justify-content: center;
    margin: 20px 0 10px 0 !important;
}
.quick-chip button {
    border-radius: 999px !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    padding: 8px 20px !important;
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #e2e8f0 !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
}
.quick-chip button:hover {
    border-color: #f59e0b !important;
    background: #f59e0b !important;
    color: #ffffff !important;
    transform: translateY(-3px);
    box-shadow: 0 6px 16px rgba(245, 158, 11, 0.35);
}

/* Input Row */
#input-row {
    align-items: flex-end;
    gap: 14px !important;
    margin-top: 5px !important;
}
#input-row > div:first-child { 
    border-radius: 20px !important;
    background: #0f1724 !important;
    border: 1px solid #1e293b !important;
    transition: all 0.25s ease;
}
#input-row > div:first-child:focus-within {
    border-color: #f59e0b !important;
    box-shadow: 0 0 0 1px #f59e0b !important;
}
#input-row textarea {
    font-size: 15px !important;
    padding: 16px 18px !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}
#send-btn {
    border-radius: 18px !important;
    font-weight: 600 !important;
    height: 56px !important;
    transition: all 0.25s ease !important;
    box-shadow: 0 4px 12px rgba(245, 158, 11, 0.2) !important;
    letter-spacing: 0.5px;
}
#send-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 18px rgba(245, 158, 11, 0.4) !important;
}

/* Disclaimer */
#disclaimer {
    text-align: center;
    color: #64748b;
    font-size: 12px;
    padding: 24px 0 10px 0;
    opacity: 0.7;
}
"""

QUICK_PROMPTS = [
    "🎒 What should I include in an emergency go-bag?",
    "🌊 How do I prepare for a flash flood warning?",
    "🧯 What do I do before a disaster?",
]


def user_submit(message, history):
    if not message.strip():
        return gr.update(), history, gr.update()
    history = history + [{"role": "user", "content": message}]
    # clear textbox, update history, disable input while bot responds
    return "", history, gr.update(interactive=False)


async def bot_respond(history):
    user_msg = history[-1]["content"]
    history.append({"role": "assistant", "content": ""})

    async for chunk in answer_question_improved(user_msg, history[:-1]):
        history[-1]["content"] = chunk   # replace, not +=
        yield history


def unlock_input():
    return gr.update(interactive=True)


with gr.Blocks(title="Disaster Preparedness Assistant") as demo:

    with gr.Column(elem_id="app-header"):
        gr.Markdown("# 🧭 Disaster Preparedness Assistant")
        gr.Markdown("Clear, reliable guidance on emergency procedures, resources, and safety planning.")

    chatbot = gr.Chatbot(
        elem_id="chat-window",
        height=520,
        avatar_images=(None, "🧭"),
        show_label=False,
    )

    with gr.Row(elem_classes="quick-chip"):
        chip_buttons = [gr.Button(p, size="sm") for p in QUICK_PROMPTS]

    with gr.Row(elem_id="input-row"):
        msg = gr.Textbox(
            placeholder="Ask about emergency kits, evacuation plans, warnings…",
            show_label=False,
            scale=8,
            container=False,
        )
        send = gr.Button("Send", variant="primary", scale=1, elem_id="send-btn")

    gr.Markdown(
        "This assistant provides general guidance only and is not a substitute for official emergency services.",
        elem_id="disclaimer",
    )

    # SINGLE consolidated trigger — prevents Enter + click double-firing
    gr.on(
        triggers=[msg.submit, send.click],
        fn=user_submit,
        inputs=[msg, chatbot],
        outputs=[msg, chatbot, msg],
    ).then(
        bot_respond, chatbot, chatbot
    ).then(
        unlock_input, None, msg
    )

    for btn in chip_buttons:
        btn.click(lambda p=btn.value: p.split(" ", 1)[1], None, msg)

if __name__ == "__main__":
    demo.launch(theme=theme, css=custom_css, inbrowser=True)