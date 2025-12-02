const API = {
  async createConversation(title = "New Conversation") {
    const response = await fetch(Config.getApiUrl("/conversations"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!response.ok) throw new Error("Failed to create conversation");
    return response.json();
  },

  async getConversations() {
    const response = await fetch(Config.getApiUrl("/conversations"));
    if (!response.ok) throw new Error("Failed to get conversations");
    return response.json();
  },

  async updateConversation(id, updates) {
    const response = await fetch(Config.getApiUrl(`/conversations/${id}`), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!response.ok) throw new Error("Failed to update conversation");
    return response.json();
  },

  async deleteConversation(id) {
    const response = await fetch(Config.getApiUrl(`/conversations/${id}`), {
      method: "DELETE",
    });
    if (!response.ok) throw new Error("Failed to delete conversation");
  },

  async getMessages(conversationId) {
    const response = await fetch(
      Config.getApiUrl(`/conversations/${conversationId}/messages`)
    );
    if (!response.ok) throw new Error("Failed to get messages");
    return response.json();
  },

  async sendMessage(conversationId, content) {
    const response = await fetch(
      Config.getApiUrl(`/conversations/${conversationId}/messages`),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, role: "user" }),
      }
    );
    if (!response.ok) throw new Error("Failed to send message");
    return response.json();
  },

  async getAssistantResponse(conversationId, message) {
    // const response = await fetch(
    //   Config.getApiUrl(
    //     `/conversations/${conversationId}/messages/${messageId}/response`
    //   )
    // );
    const response = await fetch(Config.getApiUrl(`/ask`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, role: "user" }),
    });
    if (!response.ok) throw new Error("Failed to get assistant response");
    return response.json();
  },

  async getUserPreferences() {
    const response = await fetch(Config.getApiUrl("/preferences"));
    if (!response.ok) throw new Error("Failed to get preferences");
    return response.json();
  },

  async updateUserPreferences(preferences) {
    const response = await fetch(Config.getApiUrl("/preferences"), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(preferences),
    });
    if (!response.ok) throw new Error("Failed to update preferences");
    return response.json();
  },
};
