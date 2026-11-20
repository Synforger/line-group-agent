// Stands in for LINE's LIFF SDK (https://static.line-scdn.net/liff/edge/2/sdk.js) when a page
// is opened outside LINE. Only what the bot's pages use is here; the member is the one the
// token was made for. `__ID_TOKEN__` and `__CLAIMS__` are filled in when the stub is served.
//
// `window.__liffStubConfig`, when a harness sets it before the page loads, changes where the
// page seems to be open: `inClient` (false: an external browser), `context` (the type of the
// screen it was opened from), `chatMessageWrite` (the consent state of that scope) and
// `shareTargetPicker` (false: the picker is not available), `sendMessagesFails` (true: the page
// seems able to send but LINE refuses, as when it was reloaded from the recently used services)
// and `storage` (values the device already holds in its local storage, as an object).
//
// Every sendMessages and shareTargetPicker call is checked against the limits LINE states for
// it and written to `window.__liffCalls`, which the harness reads.
(function () {
  "use strict";

  var TOKEN = __ID_TOKEN__;
  var CLAIMS = __CLAIMS__;
  var CONFIG = Object.assign(
    {
      inClient: true,
      context: "group",
      chatMessageWrite: "granted",
      shareTargetPicker: true,
      sendMessagesFails: false
    },
    window.__liffStubConfig || {}
  );
  var MAX_MESSAGES = 5;
  var MAX_TEXT = 5000;
  var MAX_ALT_TEXT = 400;
  var MAX_LABEL = 20;
  var SEND_TYPES = ["text", "sticker", "image", "video", "audio", "location", "template", "flex"];
  var SHARE_TYPES = ["text", "image", "video", "audio", "location", "template", "flex"];

  window.__liffCalls = { sent: [], shared: [] };
  Object.keys(CONFIG.storage || {}).forEach(function (key) {
    try {
      window.localStorage.setItem(key, CONFIG.storage[key]);
    } catch (error) {
      // A page without local storage is a case of its own; nothing to hold here.
    }
  });

  function failure(code, message) {
    var error = new Error(message);
    error.code = code;
    return error;
  }

  function actionsIn(node, found) {
    if (Array.isArray(node)) {
      node.forEach(function (item) { actionsIn(item, found); });
    } else if (node && typeof node === "object") {
      if (node.action) found.push(node.action);
      Object.keys(node).forEach(function (key) {
        if (key !== "action") actionsIn(node[key], found);
      });
    }
    return found;
  }

  function checkMessage(message, types) {
    if (!message || types.indexOf(message.type) < 0) {
      throw failure("INVALID_ARGUMENT", "message type not allowed: " + (message && message.type));
    }
    if (message.type === "text") {
      if (typeof message.text !== "string" || !message.text || message.text.length > MAX_TEXT) {
        throw failure("INVALID_ARGUMENT", "text must be 1 to " + MAX_TEXT + " characters");
      }
      if ("emojis" in message || "quoteToken" in message) {
        throw failure("INVALID_ARGUMENT", "text may not carry emojis or quoteToken");
      }
    }
    if (message.type === "template" || message.type === "flex") {
      if (typeof message.altText !== "string" || !message.altText || message.altText.length > MAX_ALT_TEXT) {
        throw failure("INVALID_ARGUMENT", "altText must be 1 to " + MAX_ALT_TEXT + " characters");
      }
      actionsIn(message.contents || message.template, []).forEach(function (action) {
        if (action.type !== "uri") {
          throw failure("INVALID_ARGUMENT", "only a uri action can be set, not " + action.type);
        }
        if (typeof action.label === "string" && action.label.length > MAX_LABEL) {
          throw failure("INVALID_ARGUMENT", "an action label is at most " + MAX_LABEL + " characters");
        }
      });
    }
  }

  function checkMessages(messages, types) {
    if (!Array.isArray(messages) || messages.length < 1 || messages.length > MAX_MESSAGES) {
      throw failure("INVALID_ARGUMENT", "messages must hold 1 to " + MAX_MESSAGES + " messages");
    }
    messages.forEach(function (message) { checkMessage(message, types); });
  }

  function copyOf(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function canSendMessages() {
    return CONFIG.inClient && CONFIG.context !== "external" && CONFIG.context !== "none" &&
      CONFIG.chatMessageWrite === "granted" && !CONFIG.sendMessagesFails;
  }

  window.liff = {
    init: function () { return Promise.resolve(); },
    ready: Promise.resolve(),
    isLoggedIn: function () { return true; },
    login: function () {},
    logout: function () {},
    getIDToken: function () { return TOKEN; },
    getDecodedIDToken: function () { return CLAIMS; },
    isInClient: function () { return CONFIG.inClient; },
    getContext: function () {
      return { type: CONFIG.inClient ? CONFIG.context : "external", scope: ["openid", "chat_message.write"] };
    },
    permission: {
      query: function (name) {
        if (name !== "chat_message.write") return Promise.resolve({ state: "unavailable" });
        return Promise.resolve({ state: CONFIG.chatMessageWrite });
      }
    },
    isApiAvailable: function (name) {
      return name === "shareTargetPicker" && CONFIG.shareTargetPicker;
    },
    sendMessages: function (messages) {
      try {
        if (!canSendMessages()) {
          throw failure("403", "user doesn't grant required permissions yet");
        }
        checkMessages(messages, SEND_TYPES);
      } catch (error) {
        return Promise.reject(error);
      }
      window.__liffCalls.sent.push.apply(window.__liffCalls.sent, copyOf(messages));
      return Promise.resolve();
    },
    shareTargetPicker: function (messages, options) {
      try {
        if (!CONFIG.shareTargetPicker) {
          throw failure("FORBIDDEN", "the share target picker is not available");
        }
        checkMessages(messages, SHARE_TYPES);
      } catch (error) {
        return Promise.reject(error);
      }
      window.__liffCalls.shared.push({ messages: copyOf(messages), options: copyOf(options || {}) });
      return Promise.resolve({ status: "success" });
    },
    closeWindow: function () { window.__liffClosed = true; },
    getOS: function () { return "ios"; },
    getLanguage: function () { return "ja"; },
    getVersion: function () { return "2.0.0-simulated"; }
  };
})();
