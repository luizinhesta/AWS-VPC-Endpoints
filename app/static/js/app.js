// Pre-visualizacao da foto selecionada antes do envio do formulario.
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var input = document.getElementById("photo");
        var preview = document.getElementById("photo-preview");

        if (!input || !preview) {
            return;
        }

        input.addEventListener("change", function () {
            var file = input.files && input.files[0];

            if (!file) {
                preview.hidden = true;
                preview.removeAttribute("src");
                return;
            }

            // Mostra a previa apenas para tipos de imagem aceitos.
            if (file.type !== "image/jpeg" && file.type !== "image/png") {
                preview.hidden = true;
                preview.removeAttribute("src");
                return;
            }

            var reader = new FileReader();
            reader.onload = function (event) {
                preview.src = event.target.result;
                preview.hidden = false;
            };
            reader.readAsDataURL(file);
        });
    });
})();
