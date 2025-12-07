const SettingsComponent = {
  create(user) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';

    let preferences = null;

    const loadPreferences = async () => {
      try {
        preferences = await API.getUserPreferences();
        render();
      } catch (error) {
        console.error('Error loading preferences:', error);
        preferences = {
          theme: 'light',
          text_size: 'medium',
          font_family: 'system',
          animations_enabled: true,
          context_memory_enabled: true
        };
        render();
      }
    };

    const savePreferences = async (updates) => {
      try {
        preferences = await API.updateUserPreferences({ ...preferences, ...updates });
        this.applyTheme(preferences.theme);
        this.applyTextSize(preferences.text_size);
        this.applyFontFamily(preferences.font_family);
        this.applyAnimations(preferences.animations_enabled);
      } catch (error) {
        console.error('Error saving preferences:', error);
      }
    };

    const render = () => {
      if (!preferences) {
        modal.innerHTML = '<div class="loading">Loading preferences...</div>';
        return;
      }

      modal.innerHTML = `
        <div class="modal-content settings-modal">
          <div class="modal-header">
            <h2>Settings</h2>
            <button class="close-btn" id="close-btn">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <div class="settings-section">
              <h3>Appearance</h3>

              <div class="setting-item">
                <label>Theme</label>
                <div class="theme-selector">
                  <button class="theme-option ${preferences.theme === 'light' ? 'active' : ''}" data-theme="light">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="5"/>
                      <line x1="12" y1="1" x2="12" y2="3"/>
                      <line x1="12" y1="21" x2="12" y2="23"/>
                      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                      <line x1="1" y1="12" x2="3" y2="12"/>
                      <line x1="21" y1="12" x2="23" y2="12"/>
                      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                    </svg>
                    Light
                  </button>
                  <button class="theme-option ${preferences.theme === 'dark' ? 'active' : ''}" data-theme="dark">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                    </svg>
                    Dark
                  </button>
                  <button class="theme-option ${preferences.theme === 'black' ? 'active' : ''}" data-theme="black">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                      <circle cx="12" cy="12" r="10"/>
                    </svg>
                    Black
                  </button>
                </div>
              </div>

              <div class="setting-item">
                <label for="text-size">Text Size</label>
                <select id="text-size" class="setting-select">
                  <option value="small" ${preferences.text_size === 'small' ? 'selected' : ''}>Small</option>
                  <option value="medium" ${preferences.text_size === 'medium' ? 'selected' : ''}>Medium</option>
                  <option value="large" ${preferences.text_size === 'large' ? 'selected' : ''}>Large</option>
                </select>
              </div>

              <div class="setting-item">
                <label for="font-family">Font Family</label>
                <select id="font-family" class="setting-select">
                  <option value="system" ${preferences.font_family === 'system' ? 'selected' : ''}>System Default</option>
                  <option value="serif" ${preferences.font_family === 'serif' ? 'selected' : ''}>Serif</option>
                  <option value="mono" ${preferences.font_family === 'mono' ? 'selected' : ''}>Monospace</option>
                </select>
              </div>

              <div class="setting-item">
                <label class="checkbox-label">
                  <input type="checkbox" id="animations" ${preferences.animations_enabled ? 'checked' : ''} />
                  Enable animations
                </label>
              </div>
            </div>

            <div class="settings-section">
              <h3>Context & Memory</h3>

              <div class="setting-item">
                <label class="checkbox-label">
                  <input type="checkbox" id="context-memory" ${preferences.context_memory_enabled ? 'checked' : ''} />
                  Enable contextual memory
                </label>
                <p class="setting-description">
                  Remember conversation context across sessions
                </p>
              </div>

              <div class="setting-item">
                <button class="btn-secondary" id="clear-session">
                  Clear Session Data
                </button>
                <p class="setting-description">
                  Remove all cached conversation data
                </p>
              </div>
            </div>

            <div class="settings-section">
              <h3>About</h3>
              <p class="setting-description">
                Modern Chat Application v1.0.0<br/>
                Built with Flask and Vanilla JavaScript
              </p>
            </div>
          </div>
        </div>
      `;

      const closeBtn = modal.querySelector('#close-btn');
      closeBtn.addEventListener('click', () => {
        modal.remove();
      });

      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          modal.remove();
        }
      });

      const themeButtons = modal.querySelectorAll('.theme-option');
      themeButtons.forEach(btn => {
        btn.addEventListener('click', () => {
          const theme = btn.dataset.theme;
          savePreferences({ theme });
          themeButtons.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
        });
      });

      modal.querySelector('#text-size').addEventListener('change', (e) => {
        savePreferences({ text_size: e.target.value });
      });

      modal.querySelector('#font-family').addEventListener('change', (e) => {
        savePreferences({ font_family: e.target.value });
      });

      modal.querySelector('#animations').addEventListener('change', (e) => {
        savePreferences({ animations_enabled: e.target.checked });
      });

      modal.querySelector('#context-memory').addEventListener('change', (e) => {
        savePreferences({ context_memory_enabled: e.target.checked });
      });

      modal.querySelector('#clear-session').addEventListener('click', () => {
        if (confirm('Are you sure you want to clear all session data?')) {
          localStorage.clear();
          alert('Session data cleared');
        }
      });
    };

    loadPreferences();

    return modal;
  },

  applyTheme(theme) {
    document.body.className = `theme-${theme}`;
    localStorage.setItem('theme', theme);
  },

  applyTextSize(size) {
    document.documentElement.style.setProperty('--text-size-multiplier',
      size === 'small' ? '0.875' : size === 'large' ? '1.125' : '1'
    );
  },

  applyFontFamily(font) {
    document.documentElement.style.setProperty('--font-family',
      font === 'mono' ? 'monospace' :
      font === 'serif' ? 'Georgia, serif' :
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
    );
  },

  applyAnimations(enabled) {
    document.documentElement.style.setProperty('--animation-duration', enabled ? '0.3s' : '0s');
  }
};
