const SidebarComponent = {
  create(user, onConversationSelect) {
    const sidebar = document.createElement('div');
    sidebar.className = 'sidebar';
    sidebar.id = 'sidebar';

    let conversations = [];
    let searchQuery = '';

    const loadConversations = async () => {
      try {
        conversations = await API.getConversations();
        render();
      } catch (error) {
        console.error('Error loading conversations:', error);
      }
    };

    const handleNewConversation = async () => {
      try {
        const conversation = await API.createConversation();
        conversations.unshift(conversation);
        render();
        onConversationSelect(conversation);
      } catch (error) {
        console.error('Error creating conversation:', error);
      }
    };

    const handlePinConversation = async (id, currentPinned) => {
      try {
        await API.updateConversation(id, { is_pinned: !currentPinned });
        await loadConversations();
      } catch (error) {
        console.error('Error pinning conversation:', error);
      }
    };

    const handleDeleteConversation = async (id, event) => {
      event.stopPropagation();
      if (confirm('Delete this conversation?')) {
        try {
          await API.deleteConversation(id);
          conversations = conversations.filter(c => c.id !== id);
          render();
        } catch (error) {
          console.error('Error deleting conversation:', error);
        }
      }
    };

    const handleSearch = (query) => {
      searchQuery = query.toLowerCase();
      render();
    };

    const renderConversation = (c) => {
      const date = new Date(c.last_message_at);
      const formattedDate = this.formatDate(date);

      return `
        <div class="conversation-item" data-id="${c.id}">
          <div class="conversation-content">
            <div class="conversation-title">${this.escapeHtml(c.title)}</div>
            <div class="conversation-meta">
              <span class="conversation-date">${formattedDate}</span>
              ${c.domain && c.domain !== 'general' ? `<span class="conversation-domain">${c.domain}</span>` : ''}
            </div>
          </div>
          <div class="conversation-actions">
            <button class="pin-btn" title="${c.is_pinned ? 'Unpin' : 'Pin'}">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="${c.is_pinned ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
                <path d="M12 17v5m-4-9l4-4 4 4m-8-4h8a2 2 0 0 1 0 4H8a2 2 0 0 1 0-4z"/>
              </svg>
            </button>
            <button class="delete-btn" title="Delete">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>
      `;
    };

    const render = () => {
      const filteredConversations = conversations.filter(c =>
        c.title.toLowerCase().includes(searchQuery)
      );

      const pinnedConvos = filteredConversations.filter(c => c.is_pinned);
      const regularConvos = filteredConversations.filter(c => !c.is_pinned);

      sidebar.innerHTML = `
        <div class="sidebar-header">
          <button class="new-chat-btn" id="new-chat-btn">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            New Chat
          </button>
        </div>

        <div class="search-container">
          <input
            type="text"
            class="search-input"
            placeholder="Search conversations..."
            id="search-input"
            value="${searchQuery}"
          />
        </div>

        <div class="conversations-list">
          ${pinnedConvos.length > 0 ? `
            <div class="conversation-section">
              <div class="section-title">Pinned</div>
              ${pinnedConvos.map(c => renderConversation(c)).join('')}
            </div>
          ` : ''}

          ${regularConvos.length > 0 ? `
            <div class="conversation-section">
              ${pinnedConvos.length > 0 ? '<div class="section-title">All Conversations</div>' : ''}
              ${regularConvos.map(c => renderConversation(c)).join('')}
            </div>
          ` : ''}

          ${filteredConversations.length === 0 ? `
            <div class="empty-state">
              <p>No conversations found</p>
            </div>
          ` : ''}
        </div>

        <div class="sidebar-footer">
          <button class="settings-btn" id="settings-btn">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 1v6m0 6v6m0-6h6m-6 0H6"/>
            </svg>
            Settings
          </button>
          <button class="logout-btn" id="logout-btn">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            Sign Out
          </button>
        </div>
      `;

      sidebar.querySelector('#new-chat-btn').addEventListener('click', handleNewConversation);
      sidebar.querySelector('#search-input').addEventListener('input', (e) => handleSearch(e.target.value));

      const settingsBtn = sidebar.querySelector('#settings-btn');
      if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
          window.dispatchEvent(new CustomEvent('openSettings'));
        });
      }

      sidebar.querySelector('#logout-btn').addEventListener('click', async () => {
        try {
          await Auth.signOut();
        } catch (error) {
          console.error('Error signing out:', error);
        }
      });

      filteredConversations.forEach(c => {
        const item = sidebar.querySelector(`[data-id="${c.id}"]`);
        if (item) {
          item.addEventListener('click', () => onConversationSelect(c));

          const pinBtn = item.querySelector('.pin-btn');
          if (pinBtn) {
            pinBtn.addEventListener('click', (e) => {
              e.stopPropagation();
              handlePinConversation(c.id, c.is_pinned);
            });
          }

          const deleteBtn = item.querySelector('.delete-btn');
          if (deleteBtn) {
            deleteBtn.addEventListener('click', (e) => handleDeleteConversation(c.id, e));
          }
        }
      });
    };

    loadConversations();

    return sidebar;
  },

  formatDate(date) {
    const now = new Date();
    const diff = now - date;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days} days ago`;
    return date.toLocaleDateString();
  },

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
};
