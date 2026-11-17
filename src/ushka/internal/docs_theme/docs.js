// Ushka Docs: copy buttons on code blocks, and a collapsed menu on small screens.
(function () {
  document.querySelectorAll(".d-article pre:not(.api-sig)").forEach(function (pre) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "copy-btn";
    button.textContent = "Copy";
    button.addEventListener("click", function () {
      var code = pre.querySelector("code") || pre;
      navigator.clipboard.writeText(code.innerText.replace(/\n$/, "")).then(function () {
        button.textContent = "Copied";
        setTimeout(function () { button.textContent = "Copy"; }, 1500);
      });
    });
    pre.appendChild(button);
  });
  // Keep the current page visible in a long sidebar.
  var here = document.querySelector('.d-nav a[aria-current="page"]');
  var side = document.querySelector(".d-nav");
  if (here && side && side.scrollHeight > side.clientHeight) { side.scrollTop = here.offsetTop - side.clientHeight / 2; }
  // "On this page": mark the section being read.
  var links = Array.prototype.slice.call(document.querySelectorAll(".d-toc li a"));
  if (links.length && "IntersectionObserver" in window) {
    var byId = {};
    links.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
    var current = null;
    var seen = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) { return; }
        var link = byId[e.target.id];
        if (!link || link === current) { return; }
        if (current) { current.removeAttribute("aria-current"); }
        link.setAttribute("aria-current", "true");
        current = link;
      });
    }, { rootMargin: "-10% 0px -80% 0px" });
    Object.keys(byId).forEach(function (id) { var el = document.getElementById(id); if (el) { seen.observe(el); } });
  }
  var menu = document.querySelector(".d-nav__menu");
  if (menu && window.matchMedia("(max-width: 52rem)").matches) { menu.removeAttribute("open"); }
})();
