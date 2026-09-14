// Carga site/data/*.json y arma la página. No conoce el contenido de ninguna
// gráfica en particular -- todo lo que dibuja sale del JSON + charts.js.
(function () {
  "use strict";

  const ORIGEN_DATOS = {
    graficas: "data/graficas.json",
    // Bloques siguientes (calidad/gqm) agregan su entrada aquí cuando existan
    // sus propios *.json y su sección deje de ser "próximamente" en el HTML.
  };

  function el(tag, attrs, hijos) {
    const nodo = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "texto") nodo.textContent = v;
      else if (k === "clase") nodo.className = v;
      else nodo.setAttribute(k, v);
    });
    (hijos || []).forEach((h) => h && nodo.appendChild(h));
    return nodo;
  }

  function tarjetaStat(numero, etiqueta) {
    return el("div", { clase: "stat" }, [el("div", { clase: "n", texto: String(numero) }), el("div", { clase: "l", texto: etiqueta })]);
  }

  function pintarResumen(corte) {
    const cont = document.getElementById("resumen-corte");
    if (!corte) return;
    cont.replaceChildren(
      tarjetaStat(corte.poblacion_total ?? "—", "issues en la población"),
      tarjetaStat(corte.ciclos_terminados_n ?? "—", "ciclos terminados (n)"),
      tarjetaStat(corte.story_points_comprometidos ?? "—", "story points comprometidos"),
      ...Object.entries(corte.por_estado || {}).map(([nombre, valor]) => tarjetaStat(valor, nombre))
    );
    const nota = document.getElementById("nota-corte");
    nota.textContent = `Corte: ${corte.identificador_del_corte || "—"} · fuente: ${corte.fuente || "Jira"}`;
  }

  function tarjetaGrafica(spec) {
    const esReal = spec.estado === "real";
    const pill = el("span", { clase: `pill ${esReal ? "ok" : "pendiente"}`, texto: esReal ? "Dato real" : "Pendiente" });
    const header = el("header", {}, [
      el("div", {}, [
        el("h3", { texto: spec.titulo }),
        spec.pregunta ? el("p", { clase: "pregunta", texto: spec.pregunta }) : null,
      ]),
      pill,
    ]);

    const cuerpo = [];
    const lienzo = el("div", { clase: "lienzo-grafica" });
    if (esReal) {
      const canvas = el("canvas");
      lienzo.appendChild(canvas);
      cuerpo.push(lienzo);
      requestAnimationFrame(() => window.CameiaCharts.renderizar(spec.tipo, canvas.getContext("2d"), spec));
    } else {
      lienzo.appendChild(el("div", { clase: "vacio-grafica", texto: "Sin dato real todavía — ver nota abajo." }));
      cuerpo.push(lienzo);
    }

    if (spec.nota_estado) cuerpo.push(el("p", { clase: "nota-estado", texto: spec.nota_estado }));
    if (spec.lectura && spec.lectura.resumen) cuerpo.push(el("p", { clase: "lectura", texto: spec.lectura.resumen }));
    if (spec.fuente) cuerpo.push(el("p", { clase: "fuente-dato", texto: `Fuente: ${spec.fuente}` }));

    return el("article", { clase: "tarjeta-grafica" }, [header, ...cuerpo]);
  }

  function cargarSeccionGraficas() {
    fetch(ORIGEN_DATOS.graficas, { cache: "no-store" })
      .then((r) => r.json())
      .then((datos) => {
        pintarResumen(datos.corte);
        const lista = document.getElementById("lista-graficas");
        lista.replaceChildren(...datos.graficas.map(tarjetaGrafica));
        const gen = document.getElementById("generado-en");
        if (gen && datos.generado_en) gen.textContent = `Generado: ${new Date(datos.generado_en).toLocaleString("es-CO")}`;
      })
      .catch((err) => {
        document.getElementById("lista-graficas").replaceChildren(
          el("p", { clase: "nota-estado", texto: "No se pudo cargar data/graficas.json — " + err.message })
        );
      });
  }

  function activarPestañas() {
    const botones = Array.from(document.querySelectorAll(".pestañas button"));
    botones.forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        botones.forEach((b) => b.setAttribute("aria-selected", "false"));
        btn.setAttribute("aria-selected", "true");
        document.querySelectorAll(".panel-seccion").forEach((s) => (s.hidden = s.id !== btn.getAttribute("aria-controls")));
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    activarPestañas();
    cargarSeccionGraficas();
  });
})();
