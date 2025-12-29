const PaginationComponent = {
  loadPreviousPage(messageId) {
    // const idx = ChatComponent.getMessageIndex(messageId, messages);
    // if (idx === -1) return;

    // const msg = messages[idx];
    const msg = messageStore.getMessage(messageId);
    console.log("PaginationComponent.loadPreviousPage msg:", msg);
    if (msg.currentPage <= 1) return;
    const chat = ChatComponent.create("conversation", "user");
    chat.loadPage(messageId, msg.currentPage);
  },

  loadNextPage(messageId) {
    // const idx = ChatComponent.getMessageIndex(messageId, messages);
    // if (idx === -1) return;

    // const msg = messages[idx];
    const msg = messageStore.getMessage(messageId);
    console.log("PaginationComponent.loadNextPage msg:", msg);
    if (msg.currentPage >= msg.pages) return;

    const chat = ChatComponent.create("conversation", "user");
    chat.loadPage(messageId, msg.currentPage + 1);
  },
};
