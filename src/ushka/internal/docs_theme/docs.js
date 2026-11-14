// Ushka Docs: copy buttons on code blocks, and a collapsed menu on small screens.
(function () {
  document.querySelectorAll(".d-article pre").forEach(function (pre) {
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
  var menu = document.querySelector(".d-nav__menu");
  if (menu && window.matchMedia("(max-width: 52rem)").matches) { menu.removeAttribute("open"); }
})();
