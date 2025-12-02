const MarkdownParser = {
  parse(text) {
    if (!text) return '';

    let html = text;

    html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
      const language = lang || 'plaintext';
      const highlighted = this.highlightCode(code.trim(), language);
      return `<div class="code-block-wrapper"><div class="code-block-header"><span class="code-lang">${language}</span><button class="copy-btn" onclick="MarkdownParser.copyCode(this)">Copy</button></div><pre><code class="language-${language}">${highlighted}</code></pre></div>`;
    });

    html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    html = html.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    html = html.replace(/~~(.*?)~~/g, '<del>$1</del>');
    html = html.replace(/==(.*?)==/g, '<mark>$1</mark>');

    html = html.replace(/^\> (.*$)/gim, '<blockquote>$1</blockquote>');

    html = html.replace(/^\* (.*$)/gim, '<li>$1</li>');
    html = html.replace(/^\d+\. (.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" onerror="this.src=\'https://via.placeholder.com/400x300?text=Image+Not+Found\'" />');

    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';

    return html;
  },

  highlightCode(code, language) {
    const keywords = {
      python: ['def', 'class', 'import', 'from', 'return', 'if', 'else', 'elif', 'for', 'while', 'try', 'except', 'with', 'as', 'lambda', 'yield', 'async', 'await'],
      javascript: ['const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while', 'try', 'catch', 'async', 'await', 'class', 'import', 'export', 'from'],
      typescript: ['const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while', 'try', 'catch', 'async', 'await', 'class', 'import', 'export', 'from', 'interface', 'type'],
      java: ['public', 'private', 'protected', 'class', 'interface', 'extends', 'implements', 'return', 'if', 'else', 'for', 'while', 'try', 'catch', 'new'],
    };

    const langKeywords = keywords[language] || [];
    let highlighted = code;

    highlighted = highlighted.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    highlighted = highlighted.replace(/('([^'\\]|\\.)*'|"([^"\\]|\\.)*")/g, '<span class="string">$1</span>');

    highlighted = highlighted.replace(/(\/\/.*$)/gm, '<span class="comment">$1</span>');
    highlighted = highlighted.replace(/(\/\*[\s\S]*?\*\/)/g, '<span class="comment">$1</span>');
    highlighted = highlighted.replace(/(#.*$)/gm, '<span class="comment">$1</span>');

    langKeywords.forEach(keyword => {
      const regex = new RegExp(`\\b(${keyword})\\b`, 'g');
      highlighted = highlighted.replace(regex, '<span class="keyword">$1</span>');
    });

    highlighted = highlighted.replace(/\b(\d+)\b/g, '<span class="number">$1</span>');

    return highlighted;
  },

  copyCode(button) {
    const codeBlock = button.closest('.code-block-wrapper').querySelector('code');
    const text = codeBlock.innerText;
    navigator.clipboard.writeText(text).then(() => {
      button.textContent = 'Copied!';
      setTimeout(() => {
        button.textContent = 'Copy';
      }, 2000);
    });
  }
};
