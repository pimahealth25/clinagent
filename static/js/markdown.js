const MarkdownParser = {
  parse(text) {
    if (!text) return "";

    // Normalize line endings
    text = text.replace(/\r\n/g, "\n");

    // Escape HTML early (critical for safety)
    text = this.escapeHTML(text);

    // ─────────────────────────────────
    // 1. CODE BLOCKS (extract first)
    // ─────────────────────────────────
    const codeBlocks = [];
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) => {
      const language = lang || "plaintext";
      const index = codeBlocks.length;
      codeBlocks.push({ language, code: code.trim() });
      return `@@CODEBLOCK_${index}@@`;
    });

    // ─────────────────────────────────
    // 2. HEADINGS
    // ─────────────────────────────────
    text = text
      .replace(/^### (.+)$/gm, "<h3>$1</h3>")
      .replace(/^## (.+)$/gm, "<h2>$1</h2>")
      .replace(/^# (.+)$/gm, "<h1>$1</h1>");

    // ─────────────────────────────────
    // 3. BLOCKQUOTES
    // ─────────────────────────────────
    text = text.replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>");

    // ─────────────────────────────────
    // 4. LISTS (group properly)
    // ─────────────────────────────────
    text = text.replace(
      /(?:^|\n)(\* .+(?:\n\* .+)*)/g,
      (block) =>
        `<ul>${block.trim().replace(/^\* (.+)$/gm, "<li>$1</li>")}</ul>`
    );

    text = text.replace(
      /(?:^|\n)(\d+\. .+(?:\n\d+\. .+)*)/g,
      (block) =>
        `<ol>${block.trim().replace(/^\d+\. (.+)$/gm, "<li>$1</li>")}</ol>`
    );

    // ─────────────────────────────────
    // 5. PARAGRAPHS
    // ─────────────────────────────────
    text = text
      .split(/\n{2,}/)
      .map((block) =>
        block.match(/^<(h\d|ul|ol|blockquote|pre|img)/)
          ? block
          : `<p>${block}</p>`
      )
      .join("");

    // ─────────────────────────────────
    // 6. INLINE FORMATTING
    // ─────────────────────────────────
    text = text
      .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
      .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/~~(.+?)~~/g, "<del>$1</del>")
      .replace(/==(.+?)==/g, "<mark>$1</mark>");

    // ─────────────────────────────────
    // 7. LINKS & IMAGES
    // ─────────────────────────────────
    text = text
      .replace(
        /!\[([^\]]*)\]\(([^)]+)\)/g,
        `<img src="$2" alt="$1"
          onerror="this.src='https://via.placeholder.com/400x300?text=Image+Not+Found'" />`
      )
      .replace(
        /\[([^\]]+)\]\(([^)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
      );

    // ─────────────────────────────────
    // 8. RESTORE CODE BLOCKS
    // ─────────────────────────────────
    text = text.replace(/@@CODEBLOCK_(\d+)@@/g, (_, i) => {
      const { language, code } = codeBlocks[i];
      const highlighted = this.highlightCode(code, language);
      return `
        <div class="code-block-wrapper">
          <div class="code-block-header">
            <span class="code-lang">${language}</span>
            <button class="copy-btn" onclick="MarkdownParser.copyCode(this)">Copy</button>
          </div>
          <pre><code class="language-${language}">${highlighted}</code></pre>
        </div>
      `;
    });

    return text;
  },

  highlightCode(code, language) {
    const keywords = {
      python: [
        "def",
        "class",
        "import",
        "from",
        "return",
        "if",
        "else",
        "elif",
        "for",
        "while",
        "try",
        "except",
        "with",
        "as",
        "lambda",
        "yield",
        "async",
        "await",
      ],
      javascript: [
        "const",
        "let",
        "var",
        "function",
        "return",
        "if",
        "else",
        "for",
        "while",
        "try",
        "catch",
        "async",
        "await",
        "class",
        "import",
        "export",
        "from",
      ],
      typescript: [
        "const",
        "let",
        "var",
        "function",
        "return",
        "if",
        "else",
        "for",
        "while",
        "try",
        "catch",
        "async",
        "await",
        "class",
        "import",
        "export",
        "from",
        "interface",
        "type",
      ],
      java: [
        "public",
        "private",
        "protected",
        "class",
        "interface",
        "extends",
        "implements",
        "return",
        "if",
        "else",
        "for",
        "while",
        "try",
        "catch",
        "new",
      ],
    };

    const langKeywords = keywords[language] || [];
    let highlighted = code;

    highlighted = highlighted
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    highlighted = highlighted.replace(
      /('([^'\\]|\\.)*'|"([^"\\]|\\.)*")/g,
      '<span class="string">$1</span>'
    );

    highlighted = highlighted.replace(
      /(\/\/.*$)/gm,
      '<span class="comment">$1</span>'
    );
    highlighted = highlighted.replace(
      /(\/\*[\s\S]*?\*\/)/g,
      '<span class="comment">$1</span>'
    );
    highlighted = highlighted.replace(
      /(#.*$)/gm,
      '<span class="comment">$1</span>'
    );

    langKeywords.forEach((keyword) => {
      const regex = new RegExp(`\\b(${keyword})\\b`, "g");
      highlighted = highlighted.replace(
        regex,
        '<span class="keyword">$1</span>'
      );
    });

    highlighted = highlighted.replace(
      /\b(\d+)\b/g,
      '<span class="number">$1</span>'
    );

    return highlighted;
  },

  copyCode(button) {
    const codeBlock = button
      .closest(".code-block-wrapper")
      .querySelector("code");
    const text = codeBlock.innerText;
    navigator.clipboard.writeText(text).then(() => {
      button.textContent = "Copied!";
      setTimeout(() => {
        button.textContent = "Copy";
      }, 2000);
    });
  },

  escapeHTML(str) {
    return str.replace(
      /[&<>"']/g,
      (m) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        }[m])
    );
  },
};
