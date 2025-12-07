const AuthComponent = {
  create() {
    const container = document.createElement('div');
    container.className = 'auth-container';

    let isLogin = true;

    const render = () => {
      container.innerHTML = `
        <div class="auth-card">
          <div class="auth-header">
            <h1>Chat Application</h1>
            <p>${isLogin ? 'Sign in to continue' : 'Create your account'}</p>
          </div>
          <form class="auth-form" id="auth-form">
            <div class="form-group">
              <label for="email">Email</label>
              <input type="email" id="email" name="email" required autocomplete="email" />
            </div>
            <div class="form-group">
              <label for="password">Password</label>
              <input type="password" id="password" name="password" required autocomplete="current-password" minlength="6" />
            </div>
            <div class="error-message" id="error-message"></div>
            <button type="submit" class="btn-primary">
              ${isLogin ? 'Sign In' : 'Sign Up'}
            </button>
          </form>
          <div class="auth-toggle">
            ${isLogin ? "Don't have an account?" : 'Already have an account?'}
            <button class="link-btn" id="toggle-btn">
              ${isLogin ? 'Sign Up' : 'Sign In'}
            </button>
          </div>
        </div>
      `;

      const form = container.querySelector('#auth-form');
      const toggleBtn = container.querySelector('#toggle-btn');
      const errorMessage = container.querySelector('#error-message');

      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        errorMessage.textContent = '';

        const email = form.email.value;
        const password = form.password.value;

        try {
          if (isLogin) {
            await Auth.signIn(email, password);
          } else {
            await Auth.signUp(email, password);
          }
        } catch (error) {
          errorMessage.textContent = error.message;
        }
      });

      toggleBtn.addEventListener('click', () => {
        isLogin = !isLogin;
        render();
      });
    };

    render();
    return container;
  }
};
