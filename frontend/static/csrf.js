// Manda o token CSRF (meta csrf-token) em todo fetch de escrita para o mesmo site.
(function () {
  var meta = document.querySelector('meta[name="csrf-token"]');
  if (!meta || !window.fetch) return;
  var token = meta.content;
  var original = window.fetch;
  var escrita = /^(POST|PUT|PATCH|DELETE)$/i;
  window.fetch = function (input, init) {
    init = init || {};
    var metodo = init.method || (input && input.method) || "GET";
    var url = typeof input === "string" ? input : (input && input.url) || "";
    var mesmoSite = (url.charAt(0) === "/" && url.charAt(1) !== "/") || url.indexOf(location.origin) === 0;
    if (escrita.test(metodo) && mesmoSite) {
      var headers = new Headers(init.headers || (input && input.headers) || {});
      headers.set("X-CSRF-Token", token);
      init.headers = headers;
    }
    return original.call(this, input, init);
  };
})();
