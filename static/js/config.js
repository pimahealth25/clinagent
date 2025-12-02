const Config = {
  API_BASE_URL: "http://127.0.0.1:5000/",
  THEME_STORAGE_KEY: "theme",
  PREFERENCES_STORAGE_KEY: "preferences",
  SESSION_STORAGE_KEY: "session",

  getApiUrl(endpoint) {
    return `${this.API_BASE_URL}${endpoint}`;
  },
};
