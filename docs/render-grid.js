// render-grid.js — shared render helpers for index.html live Gold sync
// Used by applyLocalEdits() to re-render Gold view from localStorage data

const RG_DAY_START = 8 * 60; // 08:00
const RG_DAY_END   = 20 * 60; // 20:00
const RG_SLOTS     = (RG_DAY_END - RG_DAY_START) / 15; // 48 slots

function teamColor(teamId) {
  let h = 0;
  for (let i = 0; i < teamId.length; i++) h = (h * 31 + teamId.charCodeAt(i)) & 0xfffffff;
  const hue = (h * 137 + 60) % 360;
  return `hsl(${hue} 92% 58%)`;
}

function _minToTime(m) {
  const h = Math.floor(m / 60), mm = m % 60;
  return `${String(h).padStart(2,'0')}:${String(mm).padStart(2,'0')}`;
}

function _timeToMin(t) {
  if (!t || t === 'NIET_GELUKT') return null;
  const [h, m] = t.split(':').map(Number);
  return h * 60 + m;
}

/**
 * Render a .grid table into containerEl (replaces existing content).
 * rows: array of row objects from gold_result.json / localStorage
 * date: string "DD-MM-YYYY" (used for data-detail if schema has no date info)
 * containerEl: the .grid-wrap element to populate
 */
function renderGoldGrid(rows, date, containerEl) {
  // Build slot occupancy map: slot -> court -> row
  const occupied = {}; // [slot][court] = row
  for (const r of rows) {
    if (!r.start || r.start === 'NIET_GELUKT' || !r.court) continue;
    const startMin = _timeToMin(r.start);
    const endMin   = _timeToMin(r.end);
    if (startMin === null || endMin === null) continue;
    const startSlot = (startMin - RG_DAY_START) / 15;
    const endSlot   = (endMin - RG_DAY_START) / 15;
    for (let s = startSlot; s < endSlot; s++) {
      if (!occupied[s]) occupied[s] = {};
      occupied[s][r.court] = { row: r, isFirst: s === startSlot };
    }
  }

  const courts = [1,2,3,4,5,6,7,8,9,10];

  let html = "<table class='grid'><thead><tr><th>Tijd</th>";
  for (const c of courts) html += `<th>Baan ${c}</th>`;
  html += "</tr></thead><tbody>";

  for (let s = 0; s < RG_SLOTS; s++) {
    const min = RG_DAY_START + s * 15;
    const isMajor = (min % 60 === 0);
    const timeStr = _minToTime(min);
    html += `<tr class='${isMajor ? "major-row" : ""}'><td class='time'>${timeStr}</td>`;
    for (const c of courts) {
      const cell = occupied[s] && occupied[s][c];
      if (cell) {
        const r = cell.row;
        const tid = r.team_id || r.team_short || r.schema || '';
        const col = teamColor(tid);
        const schema = r.schema || r.team_short || tid;
        const away = r.away_team || '';
        const detail = `${schema} | ${r.part || ''} | ${r.start}-${r.end} | Baan ${c} | vs ${away}`;
        const label = cell.isFirst
          ? `${r.team_short || tid} · ${r.part || ''}${away ? ' vs ' + away : ''}`
          : '·';
        html += `<td class='tap-cell' style='background:${col}' data-detail='${detail.replace(/'/g,"&#39;")}'><div class='cell'>${label}</div></td>`;
      } else {
        html += "<td class='empty'>—</td>";
      }
    }
    html += "</tr>";
  }

  html += "</tbody></table>";
  containerEl.innerHTML = html;
}

/**
 * Render a .summary div into containerEl (replaces existing content).
 * rows: array of row objects
 * containerEl: the .summary element to populate
 */
function renderGoldSummary(rows, containerEl) {
  // Group by team
  const teams = {};
  for (const r of rows) {
    const tid = r.team_id || r.team_short || r.schema || '';
    if (!teams[tid]) {
      teams[tid] = {
        short: r.team_short || tid,
        schema: r.schema || r.team_short || tid,
        away: r.away_team || '',
        home: r.home_team || '',
        rows: [],
        color: teamColor(tid)
      };
    }
    teams[tid].rows.push(r);
  }

  let html = "<h3>Teams vandaag</h3><ul>";
  for (const [tid, t] of Object.entries(teams)) {
    const scheduled = t.rows.filter(r => r.start && r.start !== 'NIET_GELUKT');
    const starts = scheduled.map(r => _timeToMin(r.start)).filter(x=>x!==null);
    const ends   = scheduled.map(r => _timeToMin(r.end)).filter(x=>x!==null);
    const firstStart = starts.length ? _minToTime(Math.min(...starts)) : '—';
    const lastEnd    = ends.length   ? _minToTime(Math.max(...ends))   : '—';
    const match = t.away ? `${t.home || 'MIERLO'} vs ${t.away}` : '—';
    html += `<li><span class='team-swatch' style='background:${t.color}'></span>` +
      `<strong>${t.short}</strong> <span class='small'>( ${t.schema} )</span>: ` +
      `${match} — wedstrijden <strong>${scheduled.length}/${t.rows.length}</strong> — ` +
      `eerste start <strong>${firstStart}</strong>, laatste eind <strong>${lastEnd}</strong></li>`;
  }
  html += "</ul>";
  containerEl.innerHTML = html;
}
