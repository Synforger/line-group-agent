// Stands in for LINE's LIFF SDK (https://static.line-scdn.net/liff/edge/2/sdk.js) when a page
// is opened outside LINE. Only what the bot's pages use is here; the member is the one the
// token was made for. `__ID_TOKEN__` and `__CLAIMS__` are filled in when the stub is served.
(function () {
  "use strict";

  var TOKEN = __ID_TOKEN__;
  var CLAIMS = __CLAIMS__;

  window.liff = {
    init: function () { return Promise.resolve(); },
    ready: Promise.resolve(),
    isLoggedIn: function () { return true; },
    login: function () {},
    logout: function () {},
    getIDToken: function () { return TOKEN; },
    getDecodedIDToken: function () { return CLAIMS; },
    isInClient: function () { return true; },
    closeWindow: function () { window.__liffClosed = true; },
    getOS: function () { return "ios"; },
    getLanguage: function () { return "ja"; },
    getVersion: function () { return "2.0.0-simulated"; }
  };
})();
