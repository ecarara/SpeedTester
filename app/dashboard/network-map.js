/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 Edson Angelo Carara */

/* Offline-first network atlas: no map tiles, public-IP data or third-party requests. */
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const COLORS = ['#d8ff66', '#6de4d0', '#ffad68', '#83b8ff', '#ff796d', '#c7a6ff'];
  const REGIONS = [
    ['AMÉRICA DO NORTE', 235, 168], ['AMÉRICA DO SUL', 350, 357],
    ['EUROPA', 533, 127], ['ÁFRICA', 552, 252],
    ['ÁSIA', 731, 157], ['OCEANIA', 828, 374],
  ];

  function svg(tag, attrs = {}, text = '') {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text) node.textContent = text;
    return node;
  }

  function project(latitude, longitude) {
    return { x: 50 + ((Number(longitude) + 180) / 360) * 900, y: 28 + ((90 - Number(latitude)) / 180) * 444 };
  }

  function format(value, suffix = '') {
    return value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(2) + suffix;
  }

  function selectPoint(point, position, color, detailTitle, detailCopy, detailStats, map) {
    detailTitle.textContent = point.operator;
    let coordinateLabel = 'posição indisponível';
    if (point.coordinate_source === 'city-centroid') coordinateLabel = 'posição aproximada da cidade';
    else if (point.coordinate_source === 'country-centroid') coordinateLabel = 'posição aproximada do país';
    detailCopy.textContent = `${point.city} · ${point.country} · ${coordinateLabel}`;
    detailStats.replaceChildren();
    for (const [label, value] of [['Amostras', point.samples], ['Download médio', format(point.avg_download_mbps, ' Mbps')], ['Upload médio', format(point.avg_upload_mbps, ' Mbps')], ['Falhas', point.failure_count]]) {
      const stat = document.createElement('div');
      const caption = document.createElement('span');
      caption.textContent = label;
      const valueNode = document.createElement('strong');
      valueNode.textContent = String(value);
      stat.append(caption, valueNode);
      detailStats.append(stat);
    }
    if (position) {
      for (const node of map.querySelectorAll('.map-tooltip')) node.remove();
      const tooltip = svg('g', { class: 'map-tooltip' });
      const text = `${point.operator} · ${point.city}`;
      const width = Math.min(310, Math.max(120, text.length * 6.3));
      const x = Math.max(18, Math.min(982 - width, position.x + 14));
      const y = Math.max(68, position.y - 14);
      tooltip.append(svg('rect', { x, y: y - 22, width, height: 26, rx: 7, fill: '#102223', stroke: color }));
      tooltip.append(svg('text', { x: x + 10, y: y - 5, class: 'map-tooltip-text' }, text));
      map.append(tooltip);
    }
  }

  function render(target, payload, filters = {}) {
    target.replaceChildren();
    const points = Array.isArray(payload?.points) ? payload.points : [];
    const filtered = points.filter((point) =>
      (!filters.operator || point.operator === filters.operator) &&
      (!filters.country || point.country === filters.country) &&
      (!filters.city || point.city === filters.city)
    );
    const layout = document.createElement('div');
    layout.className = 'network-map-layout';
    const mapWrap = document.createElement('div');
    mapWrap.className = 'network-map-canvas';
    const map = svg('svg', { viewBox: '0 0 1000 500', role: 'img', 'aria-label': 'Mapa interativo de operadoras, cidades e países' });
    const heading = document.createElement('div');
    heading.className = 'network-map-heading';
    const headingTitle = document.createElement('span');
    headingTitle.textContent = 'Visão global';
    const headingCount = document.createElement('span');
    headingCount.className = 'network-map-count';
    const located = filtered.filter((point) => point.latitude != null && point.longitude != null).length;
    headingCount.textContent = located + (located === 1 ? ' grupo localizado' : ' grupos localizados');
    heading.append(headingTitle, headingCount);
    mapWrap.append(heading, map);

    for (let longitude = -180; longitude <= 180; longitude += 30) {
      const start = project(-90, longitude), end = project(90, longitude);
      map.append(svg('line', { x1: start.x, y1: start.y, x2: end.x, y2: end.y, class: 'map-grid-line' }));
    }
    for (let latitude = -60; latitude <= 60; latitude += 30) {
      const start = project(latitude, -180), end = project(latitude, 180);
      map.append(svg('line', { x1: start.x, y1: start.y, x2: end.x, y2: end.y, class: latitude === 0 ? 'map-grid-line map-equator' : 'map-grid-line' }));
    }
    map.append(svg('image', { href: '/dashboard/world-map.svg', x: 0, y: 0, width: 1000, height: 500, class: 'map-geography', 'aria-hidden': 'true' }));
    for (const [name, x, y] of REGIONS) map.append(svg('text', { x, y, 'text-anchor': 'middle', class: 'map-region-label', 'aria-hidden': 'true' }, name));
    const footer = document.createElement('div');
    footer.className = 'network-map-footer';
    const key = document.createElement('span');
    key.className = 'network-map-key';
    key.textContent = 'Medições agrupadas';
    const precision = document.createElement('span');
    precision.textContent = 'Posições aproximadas';
    footer.append(key, precision);
    mapWrap.append(footer);

    const visiblePoints = filtered.filter((point) => point.latitude != null && point.longitude != null);
    const coordinateGroups = new Map();
    for (const point of visiblePoints) {
      const key = `${point.latitude}:${point.longitude}`;
      const index = coordinateGroups.get(key) || 0;
      coordinateGroups.set(key, index + 1);
      const angle = index * 1.7;
      const radius = index ? 10 + index * 3 : 0;
      const base = project(point.latitude, point.longitude);
      const position = { x: base.x + Math.cos(angle) * radius, y: base.y + Math.sin(angle) * radius };
      const color = COLORS[points.indexOf(point) % COLORS.length];
      const group = document.createElementNS(NS, 'g');
      group.classList.add('map-marker');
      group.setAttribute('tabindex', '0');
      group.setAttribute('role', 'button');
      group.setAttribute('aria-label', `${point.operator}, ${point.city}, ${point.country}`);
      group.addEventListener('click', () => selectPoint(point, position, color, detailTitle, detailCopy, detailStats, map));
      group.addEventListener('focus', () => selectPoint(point, position, color, detailTitle, detailCopy, detailStats, map));
      group.addEventListener('mouseenter', () => selectPoint(point, position, color, detailTitle, detailCopy, detailStats, map));
      group.append(svg('circle', { cx: position.x, cy: position.y, r: Math.min(18, 6 + Math.sqrt(point.samples) * 1.8), fill: color, class: 'map-marker-halo' }));
      group.append(svg('circle', { cx: position.x, cy: position.y, r: 4, fill: '#071114', stroke: color, 'stroke-width': 2 }));
      map.append(group);
    }
    const detail = document.createElement('aside');
    detail.className = 'network-map-detail';
    const detailEyebrow = document.createElement('div');
    detailEyebrow.className = 'eyebrow';
    detailEyebrow.textContent = 'Ponto selecionado';
    const detailTitle = document.createElement('h4');
    detailTitle.textContent = 'Passe o cursor sobre um ponto';
    const detailCopy = document.createElement('p');
    detailCopy.className = 'network-map-detail-copy';
    detailCopy.textContent = 'Cada ponto reúne medições da mesma operadora, cidade e país.';
    const detailStats = document.createElement('div');
    detailStats.className = 'network-map-stats';
    detail.append(detailEyebrow, detailTitle, detailCopy, detailStats);

    const listTitle = document.createElement('div');
    listTitle.className = 'network-map-list-title';
    listTitle.textContent = `${filtered.length} agrupamento(s)`;
    detail.append(listTitle);
    const list = document.createElement('div');
    list.className = 'network-map-list';
    for (const [index, point] of filtered.slice(0, 12).entries()) {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'network-map-list-item';
      item.addEventListener('click', () => {
        const base = point.latitude == null ? null : project(point.latitude, point.longitude);
        selectPoint(point, base, COLORS[points.indexOf(point) % COLORS.length], detailTitle, detailCopy, detailStats, map);
      });
      const swatch = document.createElement('span');
      swatch.className = 'network-map-swatch';
      swatch.style.background = COLORS[index % COLORS.length];
      const copy = document.createElement('span');
      const name = document.createElement('strong');
      name.textContent = point.operator;
      const location = document.createElement('small');
      location.textContent = `${point.city} · ${point.country}`;
      copy.append(name, location);
      const count = document.createElement('b');
      count.textContent = String(point.samples);
      item.append(swatch, copy, count);
      list.append(item);
    }
    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = 'Nenhum grupo encontrado para os filtros atuais.';
      list.append(empty);
    }
    detail.append(list);
    layout.append(mapWrap, detail);
    target.append(layout);
  }

  window.SpeedTesterNetworkMap = { render };
})();
