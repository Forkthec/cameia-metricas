// Renderers de gráficas, uno por "tipo" declarado en site/data/*.json.
// Para agregar una gráfica de un tipo YA soportado: agregar un objeto al JSON,
// nada de JS. Para un tipo nuevo: agregar una función aquí y una entrada en
// `RENDERERS` -- el resto del sitio (main.js) no cambia.
(function (global) {
  "use strict";

  function resolverColor(valor) {
    if (typeof valor === "string" && valor.startsWith("var(")) {
      const nombre = valor.slice(4, -1).trim();
      const resuelto = getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
      return resuelto || "#999";
    }
    return valor;
  }

  function estiloLinea(estilo) {
    if (estilo === "dashed") return [6, 4];
    if (estilo === "dotted") return [1, 3];
    return [];
  }

  const BASE_OPCIONES = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        position: "bottom",
        labels: { boxWidth: 12, boxHeight: 12, font: { size: 11.5, family: "IBM Plex Sans" }, color: resolverColor("var(--muted)") },
      },
      tooltip: { titleFont: { family: "IBM Plex Sans" }, bodyFont: { family: "IBM Plex Sans" } },
    },
  };

  function ejeComun(spec) {
    const colorEje = resolverColor("var(--muted)");
    const colorGrilla = resolverColor("var(--linea)");
    return {
      x: {
        title: { display: !!(spec.eje_x && spec.eje_x.titulo), text: spec.eje_x && spec.eje_x.titulo, color: colorEje, font: { size: 11.5 } },
        ticks: { color: colorEje, font: { size: 11 } },
        grid: { color: colorGrilla },
      },
      y: {
        title: { display: !!(spec.eje_y && spec.eje_y.titulo), text: spec.eje_y && spec.eje_y.titulo, color: colorEje, font: { size: 11.5 } },
        ticks: { color: colorEje, font: { size: 11 } },
        grid: { color: colorGrilla },
        beginAtZero: true,
      },
    };
  }

  function datasetsReferencias(spec, numCategorias) {
    return (spec.referencias || []).map((ref) => ({
      label: ref.nombre,
      data: Array(numCategorias).fill(ref.valor),
      borderColor: resolverColor(ref.color),
      borderWidth: 1.5,
      borderDash: estiloLinea(ref.estilo),
      pointRadius: 0,
      fill: false,
      order: -1,
    }));
  }

  function lineaConReferencia(ctx, spec) {
    const labels = spec.eje_x.categorias;
    const datasets = [
      ...spec.series.map((s) => ({
        label: s.nombre,
        data: s.valores,
        borderColor: resolverColor(s.color),
        backgroundColor: resolverColor(s.color),
        pointRadius: 2.5,
        borderWidth: 2,
        tension: 0.15,
      })),
      ...datasetsReferencias(spec, labels.length),
    ];
    return new Chart(ctx, { type: "line", data: { labels, datasets }, options: { ...BASE_OPCIONES, scales: ejeComun(spec) } });
  }

  function flujoAcumulado(ctx, spec) {
    const labels = spec.eje_x.categorias;
    // Se apila de abajo hacia arriba en el orden inverso al declarado (Finalizado
    // queda como banda base que crece, igual que el ejemplo del profesor).
    const series = [...spec.series].reverse();
    const datasets = series.map((s) => ({
      label: s.nombre,
      data: s.valores,
      borderColor: resolverColor(s.color),
      backgroundColor: resolverColor(s.color) + "CC",
      fill: true,
      pointRadius: 0,
      borderWidth: 1,
      tension: 0.1,
    }));
    return new Chart(ctx, {
      type: "line",
      data: { labels, datasets },
      options: { ...BASE_OPCIONES, scales: { ...ejeComun(spec), y: { ...ejeComun(spec).y, stacked: true } } },
    });
  }

  function edadPorEstado(ctx, spec) {
    const categorias = spec.eje_x.categorias;
    const puntos = spec.puntos.map((p) => ({ x: categorias.indexOf(p.estado) + 1, y: p.edad_dias, id: p.id }));
    const datasets = [
      {
        label: "Ítem abierto",
        data: puntos,
        backgroundColor: resolverColor("var(--serie-azul)"),
        borderColor: resolverColor("var(--serie-azul)"),
        pointRadius: 5,
        pointHoverRadius: 7,
        showLine: false,
      },
      ...datasetsReferencias(spec, 2).map((ds, i) => ({
        ...ds,
        data: [
          { x: 0.5, y: spec.referencias[i].valor },
          { x: categorias.length + 0.5, y: spec.referencias[i].valor },
        ],
        showLine: true,
      })),
    ];
    const colorEje = resolverColor("var(--muted)");
    return new Chart(ctx, {
      type: "scatter",
      data: { datasets },
      options: {
        ...BASE_OPCIONES,
        interaction: { mode: "nearest", intersect: true },
        plugins: {
          ...BASE_OPCIONES.plugins,
          tooltip: {
            ...BASE_OPCIONES.plugins.tooltip,
            callbacks: {
              label: (item) => (item.raw.id ? `${item.raw.id} · ${item.raw.y} días` : `${item.dataset.label}: ${item.raw.y}`),
            },
          },
        },
        scales: {
          x: {
            type: "linear",
            min: 0.5,
            max: categorias.length + 0.5,
            afterBuildTicks: (axis) => {
              axis.ticks = categorias.map((_, i) => ({ value: i + 1 }));
            },
            ticks: { color: colorEje, callback: (v) => categorias[Math.round(v) - 1] || "" },
            title: { display: !!(spec.eje_x && spec.eje_x.titulo), text: spec.eje_x.titulo, color: colorEje },
            grid: { color: resolverColor("var(--linea)") },
          },
          y: { ...ejeComun(spec).y },
        },
      },
    });
  }

  function categoriasApiladasConTotal(ctx, spec) {
    const labels = spec.eje_x.categorias;
    const datasets = spec.categorias.map((c) => ({
      type: "bar",
      label: c.nombre,
      data: c.valores,
      backgroundColor: resolverColor(c.color),
      stack: "desperdicio",
    }));
    if (spec.total) {
      datasets.push({
        type: "line",
        label: spec.total.nombre || "Total por día",
        data: spec.total.valores,
        borderColor: resolverColor("var(--ink)"),
        borderDash: [6, 4],
        borderWidth: 1.5,
        pointRadius: 3,
        fill: false,
      });
    }
    return new Chart(ctx, { type: "bar", data: { labels, datasets }, options: { ...BASE_OPCIONES, scales: ejeComun(spec) } });
  }

  const RENDERERS = {
    linea_con_referencia: lineaConReferencia,
    flujo_acumulado: flujoAcumulado,
    edad_por_estado: edadPorEstado,
    categorias_apiladas_con_total: categoriasApiladasConTotal,
  };

  global.CameiaCharts = {
    renderizar(tipo, ctx, spec) {
      const fn = RENDERERS[tipo];
      if (!fn) {
        console.warn(`Sin renderer para el tipo "${tipo}" -- agrega uno en site/js/charts.js`);
        return null;
      }
      return fn(ctx, spec);
    },
    tiposSoportados: Object.keys(RENDERERS),
  };
})(window);
