const ChatComponent = {
  create(conversation, user) {
    const chatView = document.createElement("div");
    chatView.className = "chat-view";

    let messages = [];
    let isStreaming = false;
    let currentStreamingMessageId = null;

    const loadMessages = async () => {
      try {
        // // const data = await API.getMessages(conversation.id);
        // messages = data.messages || [];
        messages = conversation.messages || [];
        render();
        scrollToBottom();
      } catch (error) {
        console.error("Error loading messages:", error);
      }
    };

    const handleSendMessage = async (content) => {
      if (!content.trim() || isStreaming) return;

      try {
        // const userMessage = await API.sendMessage(conversation.id, content);
        const userMessage = {
          id: Date.now().toString(),
          role: "user",
          content: content,
          is_streaming: false,
          conversation_id: conversation.id,
        };

        messages.push(userMessage);
        render();
        scrollToBottom();

        const assistantMessage = {
          id: Date.now().toString(),
          role: "system",
          content: "",
          is_streaming: true,
          conversation_id: conversation.id,
          metadata: { is_fetching: true },
        };

        messages.push(assistantMessage);
        currentStreamingMessageId = assistantMessage.id;
        isStreaming = true;
        render();
        this.startSearchIndicator(currentStreamingMessageId);
        scrollToBottom();

        const responseData = await API.getAssistantResponse(
          conversation.id,
          userMessage
        );
        console.log("Assistant Response Data:", responseData);

        this.stopSearchIndicator();
        updateMessageRoleAndFetchingStatus("assistant", false);
        render();

        await simulateStreaming(
          currentStreamingMessageId,
          responseData.response || this.generateResponse(content)
        );
      } catch (error) {
        console.error("Error sending message:", error);
        alert(`[ChatRoom Error]`);
        isStreaming = false;
        currentStreamingMessageId = null;
        render();
      } finally {
        this.stopSearchIndicator();
      }
    };

    const updateMessageRoleAndFetchingStatus = (role, fetchStatus) => {
      const messageIndex = messages.findIndex(
        (m) => m.id === currentStreamingMessageId
      );
      if (messageIndex !== -1) {
        messages[messageIndex].role = role; // Switch role to show content
        messages[messageIndex].metadata.is_fetching = fetchStatus;
      }
    };

    const simulateStreaming = async (messageId, responseText) => {
      const words = responseText.split(" ");
      let accumulated = "";

      for (let i = 0; i < words.length; i++) {
        if (!isStreaming) break;

        accumulated += words[i] + " ";

        const messageIndex = messages.findIndex((m) => m.id === messageId);
        if (messageIndex !== -1) {
          messages[messageIndex].content = accumulated.trim();
          updateMessageDisplay(messageId, accumulated.trim());
        }

        await new Promise((resolve) =>
          setTimeout(resolve, 30 + Math.random() * 30)
        );
      }

      if (isStreaming) {
        isStreaming = false;
        currentStreamingMessageId = null;
        render();
      }
    };

    const stopStreaming = () => {
      if (isStreaming && currentStreamingMessageId) {
        isStreaming = false;
        currentStreamingMessageId = null;
        render();
      }
    };

    const updateMessageDisplay = (messageId, content) => {
      const messageEl = chatView.querySelector(
        `[data-message-id="${messageId}"] .message-content`
      );
      if (messageEl) {
        messageEl.innerHTML = MarkdownParser.parse(content);
      }
    };

    const scrollToBottom = () => {
      setTimeout(() => {
        const messagesContainer = chatView.querySelector(".messages-container");
        if (messagesContainer) {
          messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
      }, 100);
    };

    const renderMessage = (message) => {
      const isUser = message.role === "user";
      const isSystem =
        message.role === "system" || message.role === "assistant";
      const isFetching = message.metadata?.is_fetching;

      if (message.metadata && message.metadata.tool_call) {
        return this.renderToolCallMessage(message);
      }

      return `
        <div class="message ${
          isUser
            ? "user-message"
            : isSystem
            ? "system-message"
            : "assistant-message"
        }" data-message-id="${message.id}">
          ${
            !isUser
              ? `
            <div class="message-avatar">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 6v6l4 2" stroke="white" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </div>
          `
              : ""
          }
          <div class="message-bubble">
          ${
            !isUser && isFetching
              ? `<div id="search-status-${message.id}" class="search-status">
                <span id="search-text-${message.id}">
                  Searching
                </span>
                <span id="search-dots-${message.id}"></span>
              </div>`
              : `<div class="message-content" id="content-${message.id}">
                ${MarkdownParser.parse(message.content)}
              </div>`
          }
            
            ${
              !isUser && !message.is_streaming && !isFetching
                ? `
              <div class="message-actions">
                <button class="action-btn" title="Copy" onclick="ChatComponent.copyMessage(this)">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                  </svg>
                </button>
              </div>
            `
                : ""
            }
          </div>
        </div>
      `;
    };

    const render = () => {
      chatView.innerHTML = `
        <div class="chat-header">
          <button class="mobile-menu-btn" id="mobile-menu-btn">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
          <h2>${this.escapeHtml(conversation.title)}</h2>
        </div>

        <div class="messages-container" id="messages-container">
          ${
            messages.length === 0
              ? `
            <div class="welcome-message">
              <h1>How can I help you today?</h1>
              <p>Ask me anything - I can help with coding, research, analysis, and more.</p>
            </div>
          `
              : ""
          }

          ${messages.map((m) => renderMessage(m)).join("")}

          ${
            isStreaming
              ? `
            <div class="thinking-indicator">
              <div class="thinking-dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          `
              : ""
          }
        </div>

        <div class="input-container">
          ${
            isStreaming
              ? `
            <button class="stop-btn" id="stop-btn">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2"/>
              </svg>
              Stop generating
            </button>
          `
              : ""
          }
          <div class="input-wrapper">
            <textarea
              class="message-input"
              id="message-input"
              placeholder="Find trials for stage 3 melanoma in the US..."
              rows="1"
            ></textarea>
            <button class="send-btn" id="send-btn" ${
              isStreaming ? "disabled" : ""
            }>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="22" y1="2" x2="11" y2="13"/>
                <polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>
        </div>

        <button class="scroll-to-bottom" id="scroll-to-bottom">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M19 12l-7 7-7-7"/>
          </svg>
        </button>
      `;

      const input = chatView.querySelector("#message-input");
      const sendBtn = chatView.querySelector("#send-btn");
      const stopBtn = chatView.querySelector("#stop-btn");
      const scrollBtn = chatView.querySelector("#scroll-to-bottom");
      const mobileMenuBtn = chatView.querySelector("#mobile-menu-btn");

      input.addEventListener("input", () => {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 200) + "px";
      });

      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          handleSendMessage(input.value);
          input.value = "";
          input.style.height = "auto";
        }
      });

      sendBtn.addEventListener("click", () => {
        handleSendMessage(input.value);
        input.value = "";
        input.style.height = "auto";
      });

      if (stopBtn) {
        stopBtn.addEventListener("click", stopStreaming);
      }

      if (scrollBtn) {
        scrollBtn.addEventListener("click", scrollToBottom);

        const messagesContainer = chatView.querySelector("#messages-container");
        messagesContainer.addEventListener("scroll", () => {
          const isNearBottom =
            messagesContainer.scrollHeight -
              messagesContainer.scrollTop -
              messagesContainer.clientHeight <
            100;
          scrollBtn.style.display = isNearBottom ? "none" : "flex";
        });
      }

      if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener("click", () => {
          const sidebar = document.getElementById("sidebar");
          if (sidebar) {
            sidebar.classList.toggle("mobile-open");
          }
        });
      }
    };

    loadMessages();

    return chatView;
  },

  renderToolCallMessage(message) {
    return `
      <div class="tool-call-message" data-message-id="${message.id}">
        <div class="tool-call-header">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
          </svg>
          <span>Tool: ${message.metadata.tool_name || "Unknown Tool"}</span>
        </div>
        <div class="tool-call-content">
          ${MarkdownParser.parse(message.content)}
        </div>
      </div>
    `;
  },

  dotInterval: null,
  messageInterval: null,

  statusMessages: [
    "Searching database",
    "Fetching clinical trials",
    "Filtering studies",
    "Analyzing results",
    "Summarizing findings",
  ],

  startSearchIndicator(currentMessageId) {
    if (!currentMessageId) return;

    const statusEl = document.getElementById(
      `search-status-${currentMessageId}`
    );
    const textEl = document.getElementById(`search-text-${currentMessageId}`);
    const dotsEl = document.getElementById(`search-dots-${currentMessageId}`);

    if (!statusEl) return;

    statusEl.classList.remove("hidden");
    textEl.textContent = this.statusMessages[0];
    dotsEl.textContent = "";

    let dotCount = 0;
    this.dotInterval = setInterval(() => {
      dotCount = (dotCount + 1) % 4;
      dotsEl.textContent = ".".repeat(dotCount);
    }, 450);

    let messageIndex = 1;
    this.messageInterval = setInterval(() => {
      if (messageIndex < this.statusMessages.length) {
        textEl.textContent = this.statusMessages[messageIndex];
        messageIndex++;
      } else {
        messageIndex = 0;
        textEl.textContent = this.statusMessages[messageIndex];
      }
    }, 2500);
  },

  stopSearchIndicator() {
    clearInterval(this.dotInterval);
    clearInterval(this.messageInterval);

    const statusEl = document.getElementById("search-status");
    if (statusEl) {
      statusEl.classList.add("hidden");
    }
  },

  generateResponse(userMessage) {
    const lowerMessage = userMessage.toLowerCase();

    if (lowerMessage.includes("tool") || lowerMessage.includes("api")) {
      return `I'll help you with that. Let me use the appropriate tools to gather the information you need.

      **Tool Call: run_study_fields**
      - search: "${userMessage}"
      - max_studies: 20
      - Processing...

      Based on the tool results, I found several relevant entries. Here's a summary:

      1. **First Result**: This shows promising data with a success rate of 78%
      2. **Second Result**: Additional findings support the initial hypothesis
      3. **Third Result**: Further analysis reveals interesting patterns

      The data suggests a strong correlation between the variables we examined. Would you like me to dive deeper into any specific aspect?`;
    }

    if (
      lowerMessage.includes("code") ||
      lowerMessage.includes("python") ||
      lowerMessage.includes("javascript")
    ) {
      return `Here's a solution using best practices:

\`\`\`python
def process_data(items):
    """
    Process a list of items and return filtered results
    """
    result = []
    for item in items:
        if item.is_valid():
            result.append(item.transform())
    return result

result = process_data(my_items)
print(f"Processed {len(result)} items")
\`\`\`

This code:
- Uses clear function naming
- Includes documentation
- Handles validation
- Returns processed results

Would you like me to explain any part in more detail?`;
    }

    return `That's a great question! Let me provide you with a comprehensive answer.

## Key Points

Here's what you need to know:

1. **First Aspect**: This is fundamental to understanding the concept
2. **Second Aspect**: Building on the first point, we can see that...
3. **Third Aspect**: Finally, this ties everything together

> **Note**: This is particularly important in modern applications

You can also consider these **alternatives**:
- Option A: Simpler but less flexible
- Option B: More robust with better performance
- Option C: Best for scalability

Is there anything specific you'd like me to elaborate on?`;
  },

  escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  },

  copyMessage(button) {
    const messageContent = button
      .closest(".message-bubble")
      .querySelector(".message-content");

    const text = messageContent.innerText;
    navigator.clipboard.writeText(text).then(() => {
      button.innerHTML = "✓";
      setTimeout(() => {
        button.innerHTML =
          '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
      }, 2000);
    });
  },
};
