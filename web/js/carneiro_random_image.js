import { app } from "../../../scripts/app.js";

app.registerExtension({
  name: "Carneiro.RandomImage.Controls",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "CarneiroRandomImageLoader") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onNodeCreated?.apply(this, arguments);

      const node = this;
      const imagePicker = document.createElement("input");
      imagePicker.type = "file";
      imagePicker.accept = "image/*,.exr";
      imagePicker.hidden = true;
      document.body.appendChild(imagePicker);

      const btnLoadImage = node.addWidget(
        "button",
        "🖼️ Carregar imagem do PC",
        null,
        () => imagePicker.click()
      );
      btnLoadImage.serialize = false;

      imagePicker.addEventListener("change", async () => {
        const file = imagePicker.files?.[0];
        imagePicker.value = "";
        if (!file) return;

        btnLoadImage.name = "⏳ Enviando imagem...";
        node.setDirtyCanvas(true, true);

        try {
          const formData = new FormData();
          formData.append("image", file);
          formData.append("type", "input");
          const response = await fetch("/upload/image", {
            method: "POST",
            body: formData,
          });
          if (!response.ok) throw new Error(await response.text());

          const uploaded = await response.json();
          const imagePath = uploaded.subfolder
            ? `${uploaded.subfolder}/${uploaded.name}`
            : uploaded.name;
          const imageWidget = node.widgets?.find((widget) => widget.name === "image");
          const manualWidget = node.widgets?.find((widget) => widget.name === "manual_image");

          if (Array.isArray(imageWidget?.options?.values) && !imageWidget.options.values.includes(imagePath)) {
            imageWidget.options.values.push(imagePath);
          }
          if (imageWidget) {
            imageWidget.value = imagePath;
            imageWidget.callback?.(imagePath);
          }
          if (manualWidget) {
            manualWidget.value = true;
            manualWidget.callback?.(true);
          }
          node.setDirtyCanvas(true, true);
        } catch (error) {
          alert("Falha ao carregar a imagem: " + error.message);
        } finally {
          btnLoadImage.name = "🖼️ Carregar imagem do PC";
          node.setDirtyCanvas(true, true);
        }
      });

      let isRenaming = false;
      let isResetting = false;

      // 1. Botão de Renomear e Redimensionar
      const btnRename = node.addWidget(
        "button",
        "📁 Rename & Resize Images",
        null,
        async () => {
          if (isRenaming) return;

          const folderWidget = node.widgets?.find(
            (w) => w.name === "folder_path"
          );
          const folder = folderWidget?.value?.trim();
          if (!folder) {
            alert("Preencha o campo 'folder_path' antes de executar.");
            return;
          }

          isRenaming = true;
          btnRename.name = "⏳ Processando...";
          node.setDirtyCanvas(true, true);

          try {
            const resp = await fetch("/carneiro/rename_images", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ folder: folder }),
            });
            const data = await resp.json();
            if (resp.ok) {
              btnRename.name = "✅ Concluído!";
              alert(
                `Sucesso!\n` +
                  `• ${data.renamed} imagens renomeadas\n` +
                  `• ${data.resized} redimensionadas (max ${data.max_dim}px)`
              );
            } else {
              btnRename.name = "❌ Erro";
              alert("Erro: " + (data.error || "desconhecido"));
            }
          } catch (e) {
            btnRename.name = "❌ Erro";
            alert("Falha na requisição: " + e.message);
          } finally {
            setTimeout(() => {
              btnRename.name = "📁 Rename & Resize Images";
              isRenaming = false;
              node.setDirtyCanvas(true, true);
            }, 3000);
          }
        }
      );
      btnRename.serialize = false;

      // 2. Botão de Resetar Ciclo/Rastreador (Item 11)
      const btnReset = node.addWidget(
        "button",
        "🔄 Reset Tracker Cycle",
        null,
        async () => {
          if (isResetting) return;

          const folderWidget = node.widgets?.find(
            (w) => w.name === "folder_path"
          );
          const folder = folderWidget?.value?.trim();
          if (!folder) {
            alert("Preencha o campo 'folder_path' antes de resetar.");
            return;
          }

          isResetting = true;
          btnReset.name = "⏳ Resetando...";
          node.setDirtyCanvas(true, true);

          try {
            const resp = await fetch("/carneiro/reset_tracker", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ folder: folder }),
            });
            const data = await resp.json();
            if (resp.ok) {
              btnReset.name = "✅ Resetado!";
              alert(data.message || "Ciclo de imagens resetado com sucesso!");
            } else {
              btnReset.name = "❌ Erro";
              alert("Erro: " + (data.error || "desconhecido"));
            }
          } catch (e) {
            btnReset.name = "❌ Erro";
            alert("Falha na requisição: " + e.message);
          } finally {
            setTimeout(() => {
              btnReset.name = "🔄 Reset Tracker Cycle";
              isResetting = false;
              node.setDirtyCanvas(true, true);
            }, 2500);
          }
        }
      );
      btnReset.serialize = false;
    };
  },
});
