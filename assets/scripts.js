window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        hexToRgba: function(hex, opacity) {
            let h = hex.replace('#', '');
            if (h.length === 3) h = h.split('').map(s => s + s).join('');
            const r = parseInt(h.slice(0, 2), 16);
            const g = parseInt(h.slice(2, 4), 16);
            const b = parseInt(h.slice(4, 6), 16);
            return `rgba(${r}, ${g}, ${b}, ${opacity})`;
        },

        nearestIndex: function(distArr, target) {
            let bestI = 0, bestD = Infinity;
            for (let i = 0; i < distArr.length; i++) {
                const d = Math.abs(distArr[i] - target);
                if (d < bestD) { bestD = d; bestI = i; }
            }
            return bestI;
        },

        updateMiniMap: function(hoverData, miniStore, fig, playbackDisabled) {
            if (playbackDisabled === false) return window.dash_clientside.no_update;
            if (!hoverData || !miniStore || !fig) return window.dash_clientside.no_update;
            if (!hoverData.points || hoverData.points.length === 0) return window.dash_clientside.no_update;
            const hoverDist = hoverData.points[0].x;
            if (hoverDist === null || hoverDist === undefined) return window.dash_clientside.no_update;

            const d1 = miniStore.d1 || {};
            const d2 = miniStore.d2 || {};
            const dist = d1.dist || miniStore.dist || [];
            const t1 = d1.t || [];
            if (dist.length < 2 || t1.length !== dist.length) return window.dash_clientside.no_update;

            const interpXY = function(series, tSec) {
                const t = series.t || [];
                const x = series.x || [];
                const y = series.y || [];
                if (!t.length || t.length !== x.length || t.length !== y.length) return null;
                if (tSec <= t[0]) return [x[0], y[0]];
                const lastI = t.length - 1;
                if (tSec >= t[lastI]) return [x[lastI], y[lastI]];
                let i = 1;
                while (i < t.length && t[i] < tSec) i++;
                const t0 = t[i - 1];
                const t1v = t[i];
                const ratio = (tSec - t0) / Math.max(1e-6, (t1v - t0));
                return [
                    x[i - 1] + ratio * (x[i] - x[i - 1]),
                    y[i - 1] + ratio * (y[i] - y[i - 1])
                ];
            };

            const bestI = window.dash_clientside.clientside.nearestIndex(dist, hoverDist);
            const tSec = t1[bestI];
            const p1 = interpXY(d1, tSec);
            const p2 = interpXY(d2, tSec);
            if (!p1 || !p2) return window.dash_clientside.no_update;

            const baseData = (fig.data || []).filter(
                tr => !(tr && (tr.meta === 'hover' || tr.meta === 'playback-marker' || tr.meta === 'driver-marker'))
            );

            baseData.push({
                type: 'scatter',
                mode: 'markers',
                x: [p1[0]],
                y: [p1[1]],
                marker: {
                    color: d1.color || '#ff0000',
                    size: 11,
                    symbol: 'circle',
                    line: {color: 'white', width: 1.5}
                },
                name: d1.name || 'Driver 1',
                showlegend: false,
                hovertemplate: `<b>${d1.name || 'Driver 1'}</b><br>t=${tSec.toFixed(2)}s<extra></extra>`,
                meta: 'driver-marker'
            });

            baseData.push({
                type: 'scatter',
                mode: 'markers',
                x: [p2[0]],
                y: [p2[1]],
                marker: {
                    color: d2.color || '#00ffff',
                    size: 11,
                    symbol: 'circle',
                    line: {color: 'white', width: 1.5}
                },
                name: d2.name || 'Driver 2',
                showlegend: false,
                hovertemplate: `<b>${d2.name || 'Driver 2'}</b><br>t=${tSec.toFixed(2)}s<extra></extra>`,
                meta: 'driver-marker'
            });

            // Preserve layout to prevent flicker from re-render
            const layout = fig.layout || {};
            return {data: baseData, layout: layout};
        },

        animateMiniMapPlayback: function(playClicks, toggleClicks, nIntervals, miniStore, fig, intervalDisabled, playbackStore) {
            if (!miniStore || !miniStore.d1 || !miniStore.d2 || !fig) {
                return [window.dash_clientside.no_update, true, 0, 'Pause', 'Lap Time: 0.00s / 0.00s', {'t': 0, 'total': 0, 'lastUpdate': 0}];
            }
            const trigger = window.dash_clientside.callback_context.triggered[0].prop_id;
            const now = performance.now();

            const interpXY = function(series, tSec) {
                const t = series.t || [];
                const x = series.x || [];
                const y = series.y || [];
                if (!t.length || t.length !== x.length || t.length !== y.length) return null;
                if (tSec <= t[0]) return [x[0], y[0]];
                const lastI = t.length - 1;
                if (tSec >= t[lastI]) return [x[lastI], y[lastI]];
                let i = 1;
                while (i < t.length && t[i] < tSec) i++;
                const t0 = t[i - 1];
                const t1 = t[i];
                const ratio = (tSec - t0) / Math.max(1e-6, (t1 - t0));
                return [
                    x[i - 1] + ratio * (x[i] - x[i - 1]),
                    y[i - 1] + ratio * (y[i] - y[i - 1])
                ];
            };

            const d1Lap = miniStore.d1.lap_s || (miniStore.d1.t && miniStore.d1.t.length ? miniStore.d1.t[miniStore.d1.t.length - 1] : 0);
            const d2Lap = miniStore.d2.lap_s || (miniStore.d2.t && miniStore.d2.t.length ? miniStore.d2.t[miniStore.d2.t.length - 1] : 0);
            const maxLap = Math.max(d1Lap, d2Lap);

            let tSec = (playbackStore && playbackStore.t) || 0;
            let lastUpdate = (playbackStore && playbackStore.lastUpdate) || 0;
            let newIntervalDisabled = intervalDisabled;
            let btnText = 'Pause';

            if (trigger.includes('play-lap-btn')) {
                tSec = 0;
                lastUpdate = now;
                newIntervalDisabled = false;
                btnText = 'Pause';
            } else if (trigger.includes('pause-resume-lap-btn')) {
                if (intervalDisabled) { // Resuming
                    lastUpdate = now;
                    newIntervalDisabled = false;
                    btnText = 'Pause';
                } else { // Pausing
                    newIntervalDisabled = true;
                    btnText = 'Resume';
                }
            } else if (trigger.includes('lap-playback-interval')) {
                if (intervalDisabled) return window.dash_clientside.no_update;
                const dt = (now - lastUpdate) / 1000.0;
                tSec += dt;
                lastUpdate = now;
            }

            const done = tSec >= maxLap;
            if (done) {
                tSec = maxLap;
                newIntervalDisabled = true;
                btnText = 'Pause';
            }

            const p1 = interpXY(miniStore.d1, tSec);
            const p2 = interpXY(miniStore.d2, tSec);
            if (!p1 || !p2) return [window.dash_clientside.no_update, true, 0, 'Pause', 'Lap Time: 0.00s / 0.00s', {'t': 0, 'total': 0, 'lastUpdate': 0}];

            const baseData = (fig.data || []).filter(
                tr => !(tr && (tr.meta === 'hover' || tr.meta === 'playback-marker' || tr.meta === 'driver-marker'))
            );

            baseData.push({
                type: 'scatter', mode: 'markers', x: [p1[0]], y: [p1[1]],
                marker: { color: miniStore.d1.color || '#ff0000', size: 11, symbol: 'circle', line: {color: 'white', width: 1.5} },
                name: miniStore.d1.name || 'Driver 1', showlegend: false,
                hovertemplate: `<b>${miniStore.d1.name || 'Driver 1'}</b><br>t=${tSec.toFixed(2)}s<extra></extra>`,
                meta: 'driver-marker'
            });

            baseData.push({
                type: 'scatter', mode: 'markers', x: [p2[0]], y: [p2[1]],
                marker: { color: miniStore.d2.color || '#00ffff', size: 11, symbol: 'circle', line: {color: 'white', width: 1.5} },
                name: miniStore.d2.name || 'Driver 2', showlegend: false,
                hovertemplate: `<b>${miniStore.d2.name || 'Driver 2'}</b><br>t=${tSec.toFixed(2)}s<extra></extra>`,
                meta: 'driver-marker'
            });

            const playLayout = fig.layout || {};
            const label = `Lap Time: ${tSec.toFixed(2)}s / ${maxLap.toFixed(2)}s`;
            
            return [
                {data: baseData, layout: playLayout},
                newIntervalDisabled,
                trigger.includes('play-lap-btn') ? 0 : nIntervals,
                btnText,
                label,
                {'t': tSec, 'total': maxLap, 'lastUpdate': lastUpdate}
            ];
        },

        updateGGHover: function(hoverData, ggStore, fig, playbackDisabled) {
            if (playbackDisabled === false) return window.dash_clientside.no_update;
            if (!hoverData || !ggStore || !fig || !hoverData.points) return window.dash_clientside.no_update;
            const hoverDist = hoverData.points[0].x;
            if (hoverDist === null || hoverDist === undefined) return window.dash_clientside.no_update;

            const baseData = (fig.data || []).filter(tr => !(tr && tr.meta === 'hover'));

            const addDriver = (key) => {
                const d = ggStore[key];
                if (!d) return;
                const dist = d.dist || [];
                const lat = d.lat || [];
                const lng = d.long || [];
                if (dist.length < 5) return;
                
                const idx = window.dash_clientside.clientside.nearestIndex(dist, hoverDist);
                const color = d.color || '#ffffff';
                const name = d.driver || key;

                // 1. G-Vector Beam
                baseData.push({
                    type: 'scatter',
                    mode: 'lines',
                    x: [0, lat[idx]],
                    y: [0, lng[idx]],
                    line: {color: color, width: 1.5, dash: 'dot'},
                    opacity: 0.5,
                    showlegend: false,
                    meta: 'hover',
                    hoverinfo: 'skip'
                });

                // 2. Motion Trail (shorter: 8 points for less clutter)
                const start = Math.max(0, idx - 8);
                baseData.push({
                    type: 'scatter',
                    mode: 'lines',
                    x: lat.slice(start, idx + 1),
                    y: lng.slice(start, idx + 1),
                    line: {color: color, width: 2.5, shape: 'spline', smoothing: 1.3},
                    opacity: 0.35,
                    showlegend: false,
                    meta: 'hover',
                    hoverinfo: 'skip'
                });

                // 3. Current "G-Ball" Marker
                baseData.push({
                    type: 'scatter',
                    mode: 'markers',
                    x: [lat[idx]],
                    y: [lng[idx]],
                    marker: {
                        color: color, 
                        size: 11, 
                        line: {color: 'white', width: 1.5},
                        symbol: 'diamond'
                    },
                    name: name,
                    showlegend: false,
                    meta: 'hover',
                    hovertemplate: `<b>${name}</b><br>Lat: %{x:.2f}G<br>Long: %{y:.2f}G<extra></extra>`
                });
            };

            addDriver('d1');
            addDriver('d2');
            return {...fig, data: baseData};
        },

        updateGGFromPlayback: function(playbackState, ggStore, fig) {
            if (!playbackState || !ggStore || !fig) return window.dash_clientside.no_update;
            const tSec = playbackState.t;
            if (tSec === null || tSec === undefined) return window.dash_clientside.no_update;

            const baseData = (fig.data || []).filter(tr => !(tr && tr.meta === 'hover'));

            const addDriver = (key) => {
                const d = ggStore[key];
                if (!d) return;
                const t = d.t || [];
                const lat = d.lat || [];
                const lng = d.long || [];
                if (!t.length || t.length !== lat.length || t.length !== lng.length) return;

                let idx = 0;
                let curLat = lat[0];
                let curLng = lng[0];
                if (tSec <= t[0]) {
                    idx = 0;
                } else if (tSec >= t[t.length - 1]) {
                    idx = t.length - 1;
                    curLat = lat[idx];
                    curLng = lng[idx];
                } else {
                    idx = 1;
                    while (idx < t.length && t[idx] < tSec) idx++;
                    const t0 = t[idx - 1];
                    const t1 = t[idx];
                    const ratio = (tSec - t0) / Math.max(1e-6, (t1 - t0));
                    curLat = lat[idx - 1] + ratio * (lat[idx] - lat[idx - 1]);
                    curLng = lng[idx - 1] + ratio * (lng[idx] - lng[idx - 1]);
                }
                const color = d.color || '#ffffff';
                const name = d.driver || key;

                baseData.push({
                    type: 'scatter',
                    mode: 'lines',
                    x: [0, curLat],
                    y: [0, curLng],
                    line: {color: color, width: 1.5, dash: 'dot'},
                    opacity: 0.5,
                    showlegend: false,
                    meta: 'hover',
                    hoverinfo: 'skip'
                });

                // Shorter time-window trail (0.8s) for less clutter.
                const trailWindowSec = 0.8;
                let start = idx;
                while (start > 0 && (tSec - t[start]) < trailWindowSec) start--;
                baseData.push({
                    type: 'scatter',
                    mode: 'lines',
                    x: lat.slice(start, idx + 1),
                    y: lng.slice(start, idx + 1),
                    line: {color: color, width: 2.5, shape: 'spline', smoothing: 1.3},
                    opacity: 0.35,
                    showlegend: false,
                    meta: 'hover',
                    hoverinfo: 'skip'
                });

                baseData.push({
                    type: 'scatter',
                    mode: 'markers',
                    x: [curLat],
                    y: [curLng],
                    marker: {color: color, size: 11, line: {color: 'white', width: 1.5}, symbol: 'diamond'},
                    name: name,
                    showlegend: false,
                    meta: 'hover',
                    hovertemplate: `<b>${name}</b><br>Lat: %{x:.2f}G<br>Long: %{y:.2f}G<extra></extra>`
                });
            };

            addDriver('d1');
            addDriver('d2');
            return {...fig, data: baseData};
        },

        updateTelemetryPlaybackCursor: function(playbackState, miniStore, fig) {
            if (!playbackState || !miniStore || !miniStore.d1 || !fig || !fig.layout) return window.dash_clientside.no_update;
            const tSec = playbackState.t;
            if (tSec === null || tSec === undefined) return window.dash_clientside.no_update;

            const t = miniStore.d1.t || [];
            const dist = miniStore.d1.dist || [];
            if (!t.length || t.length !== dist.length) return window.dash_clientside.no_update;

            let cursorDist = dist[0];
            if (tSec <= t[0]) {
                cursorDist = dist[0];
            } else if (tSec >= t[t.length - 1]) {
                cursorDist = dist[dist.length - 1];
            } else {
                let i = 1;
                while (i < t.length && t[i] < tSec) i++;
                const t0 = t[i - 1];
                const t1 = t[i];
                const ratio = (tSec - t0) / Math.max(1e-6, (t1 - t0));
                cursorDist = dist[i - 1] + ratio * (dist[i] - dist[i - 1]);
            }

            const layout = {...fig.layout};
            const shapes = (layout.shapes || []).filter(s => s.name !== 'playback-cursor');
            shapes.push({
                type: 'line',
                name: 'playback-cursor',
                xref: 'x',
                yref: 'paper',
                x0: cursorDist,
                x1: cursorDist,
                y0: 0,
                y1: 1,
                line: {color: '#bbbbbb', width: 1.5, dash: 'dot'}
            });
            layout.shapes = shapes;
            return {...fig, layout: layout};
        },

        toggleFeedbackModal: function(open_clicks, cancel_clicks, refresh_data, is_open) {
            const trigger = window.dash_clientside.callback_context.triggered[0].prop_id;
            if (trigger.includes('open-feedback-modal-btn')) return true;
            if (trigger.includes('cancel-feedback-btn') || trigger.includes('feedback-refresh-store')) return false;
            return is_open;
        },

        renderAIState: function(history, index) {
            if (!history || history.length === 0) {
                return ["", "Type a question and click 'Ask AI' or press Enter to get started.", 
                        {'display': 'none'}, true, true, "", {'display': 'none'}];
            }
            const i = Math.max(0, Math.min(index || 0, history.length - 1));
            const h = history[i];

            const prev_disabled = (i === 0);
            const next_disabled = (i >= history.length - 1);
            const position = (i + 1) + " / " + history.length;
            const nav_style = {'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center', 'marginTop': '0.75rem'};
            const q_container_style = {'marginBottom': '0.5rem', 'display': 'block'};

            // Simple HTML-like string for the question to avoid complex component tree via clientside
            const question_html = h.question;
            const answer_markdown = h.answer;

            return [question_html, answer_markdown, q_container_style, prev_disabled, next_disabled, position, nav_style];
        },
        
        updateAIHistoryIndex: function(n_prev, n_next, history, current_index) {
            if (!history || history.length === 0) return 0;
            const trigger = window.dash_clientside.callback_context.triggered[0].prop_id;
            if (trigger.includes('ai-prev-btn')) {
                return Math.max(0, current_index - 1);
            }
            if (trigger.includes('ai-next-btn')) {
                return Math.min(history.length - 1, current_index + 1);
            }
            return current_index;
        },
        
        toggleLapNumbers: function(d1_mode, d2_mode) {
            const base = {
                'width': '70px', 'display': 'inline-block', 'marginLeft': '6px',
                'backgroundColor': '#222', 'color': 'white', 'border': '1px solid #444',
                'fontSize': '0.8rem'
            };
            const d1_style = Object.assign({}, base, {display: (d1_mode === 'specific' ? 'inline-block' : 'none')});
            const d2_style = Object.assign({}, base, {display: (d2_mode === 'specific' ? 'inline-block' : 'none')});
            return [d1_style, d2_style];
        }
    }
});
