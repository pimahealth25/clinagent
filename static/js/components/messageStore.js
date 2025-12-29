const messageStore = (() => {
  const messages = [];

  return {
    addMessage(message) {
      messages.push(message);
    },
    getMessage(id) {
      const idx = messages.findIndex((m) => m.id === id);
      if (idx === -1) {
        console.log("Message Store: message id doesn't exist:", id);
        return null;
      }
      return messages[idx];
    },
    removeMessage(id) {
      const idx = messages.findIndex((m) => m.id === id);
      if (idx !== -1) {
        messages.splice(idx, 1);
      }
    },
    updateMessage(id, newMessage) {
      const msg = messages.find((m) => m.id === id);
      if (msg) {
        msg.content = newContent;
      }
    },
    getAllMessages() {
      return [...messages];
    },
  };
})();
