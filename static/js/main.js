/*

This file is part of ClinAgent (https://clinagent.ai/)
the chatbot for clinical trial search and analysis.
The following are the command it accepts:
- "send" free text queries (e.g., "phase 3 diabetes")
- "show" to show results for the current query
- "show <query>" to show results for a new query
- "clear" to reset the conversation and state
- "help" to get help information
*/

const chat = document.getElementById("chat");
const chatInput = document.getElementById("input");
const btnSend = document.getElementById("send");
const btnShow = document.getElementById("show");
const btnClear = document.getElementById("clear");
const chkAgent = document.getElementById("agent");
const statusDiv = document.getElementById("status");

let state = { query: "", page_size: 5, filters: {}, agent: false };

/**
 * append a message to the chat window depending on the role
 * @param {string} role
 * @param {string} text
 */
function append(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + (role === "user" ? "user" : "bot");

  const label = document.createElement("span");
  label.className = "label";
  label.textContent = role === "user" ? "You" : "Agent";

  const content = document.createElement("span");
  content.className = "content";
  content.textContent = " " + text;

  div.appendChild(label);
  div.appendChild(content);
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

/**
 * add the current state in the chat status div
 * @param {string} s state
 */
function setStatus(s) {
  const filters = s?.filters || {};
  const pieces = [];

  if (s?.query) pieces.push(`query: "${s.query}"`);
  const phase = filters.phase ? `phase=${filters.phase}` : "";
  const st = filters.status ? `status=${filters.status}` : "";
  const cond = filters.condition ? `condition=${filters.condition}` : "";
  const sort = filters.sort ? `sort=${filters.sort}` : "";
  const limit = filters.limit ? `limit=${filters.limit}` : "";

  const fs = [phase, st, cond, sort, limit].filter(Boolean).join(" · ");
  if (fs) pieces.push(fs);
  if (s?.page_size) pieces.push(`pageSize=${s.page_size}`);
  if (s?.refiner) pieces.push("refiner=on");
  if (s?.agent) pieces.push("agent=on");
  statusDiv.textContent = pieces.length ? `State: ${pieces.join(" | ")}` : "";
}

function updateShowLabel() {
  const hasText = !!chatInput.value.trim();
  const hasQuery = !!(state?.query && state.query.trim());
  btnShow.textContent = hasText || !hasQuery ? "Show" : "More";
}

chkAgent.checked = !!state.agent;
chkAgent.addEventListener("change", () => {
  state.agent = chkAgent.checked;
  setStatus(state);
});

async function sendMessage(message) {
  append("user", message);
  chatInput.value = "";

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, state }),
    });

    const data = await res.json();
    state = data.state || state;

    setStatus(state);
    updateShowLabel();
    append("bot", data.reply || "");
  } catch (e) {
    append("bot", "Error contacting server.");
  }
}

async function sendCommand(message) {
  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, state }),
    });
    const data = await res.json();
    state = data.state || state;

    setStatus(state);
    updateShowLabel();
    append("bot", data.reply || "");
  } catch (e) {
    append("bot", "Error contacting server.");
  }
}

async function sendShowForQuery(q) {
  append("user", q);
  chatInput.value = "";
  state.filters = { ...(state.filters || {}), limit: "10" };
  await sendCommand("show " + q);
}

btnSend.addEventListener("click", () => {
  const text = chatInput.value.trim();
  if (text) sendMessage(text);
});

chatInput.addEventListener("input", updateShowLabel);

btnShow.addEventListener("click", () => {
  /*
   It takes the current input value. If there is text, it sends a "show" command for that query.
   If there is no text, it increases the limit in the state filters and sends a "show" command
   to get more results for the current query.
   */
  const text = chatInput.value.trim();

  if (text) {
    sendShowForQuery(text);
    updateShowLabel();
  } else {
    const f = state.filters || {};
    const current = parseInt(f.limit || "10", 10);
    const next = Math.min(isNaN(current) ? 10 : current + 10, 100);
    state.filters = { ...f, limit: String(next) };
    const ps = parseInt(String(state.page_size || "5"), 10);
    state.page_size = Math.min(Math.max(isNaN(ps) ? 5 : ps, next), 100);
    sendCommand("show");
  }
});

btnClear.addEventListener("click", () => sendMessage("clear"));

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (text) sendMessage(text);
  }
});

append(
  "bot",
  "Hi! Try 'phase 3 diabetes', '5 most recent lung cancer', or type 'help'."
);
updateShowLabel();
