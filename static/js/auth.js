const Auth = {
  currentUser: null,
  listeners: [],

  setUser(user) {
    this.currentUser = user;
    this.notifyListeners();
  },

  getUser() {
    return this.currentUser;
  },

  isAuthenticated() {
    return this.currentUser !== null;
  },

  onAuthChange(callback) {
    this.listeners.push(callback);
  },

  notifyListeners() {
    this.listeners.forEach(cb => cb(this.currentUser));
  },

  async checkAuth() {
    try {
      const response = await fetch(Config.getApiUrl('/auth/user'));
      if (response.ok) {
        const data = await response.json();
        this.setUser(data.user);
        return data.user;
      } else {
        this.setUser(null);
        return null;
      }
    } catch (error) {
      console.error('Auth check error:', error);
      this.setUser(null);
      return null;
    }
  },

  async signUp(email, password) {
    try {
      const response = await fetch(Config.getApiUrl('/auth/register'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Registration failed');
      }

      const data = await response.json();
      this.setUser(data.user);
      return data;
    } catch (error) {
      throw error;
    }
  },

  async signIn(email, password) {
    try {
      const response = await fetch(Config.getApiUrl('/auth/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Login failed');
      }

      const data = await response.json();
      this.setUser(data.user);
      return data;
    } catch (error) {
      throw error;
    }
  },

  async signOut() {
    try {
      await fetch(Config.getApiUrl('/auth/logout'), {
        method: 'POST'
      });
      this.setUser(null);
    } catch (error) {
      console.error('Logout error:', error);
      this.setUser(null);
    }
  }
};
