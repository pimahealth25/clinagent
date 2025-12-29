class App {
  constructor() {
    this.root = document.getElementById("root");
    this.init();
  }

  async init() {
    console.log("Agent AI initialized");

    this.renderApp();
  }

  renderApp() {
    this.root.innerHTML = "";

    const appContainer = document.createElement("div");
    appContainer.className = "app-container";

    const placeholder = document.createElement("div");
    placeholder.className = "chat-view";
    placeholder.innerHTML = `
      <div class="welcome-message" style="margin: auto;">
        <h1>Welcome to Chat</h1>
        <p>Select a conversation or create a new one to get started</p>
      </div>
    `;

    appContainer.appendChild(placeholder);
    this.root.appendChild(appContainer);
    this.renderChatView();
  }

  renderChatView() {
    const appContainer = this.root.querySelector(".app-container");
    const existingChatView = appContainer.querySelector(".chat-view");

    if (existingChatView) {
      existingChatView.remove();
    }

    this.currentConversation = { id: 2, title: "Agentic AI", messages: [] };
    const chat = ChatComponent.create(this.currentConversation, this.user);
    appContainer.appendChild(chat);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  new App();
});
