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

        handlePlaybackAnimation: function(playClicks, toggleClicks, nIntervals, miniStore, ggStore, miniFig, ggFig, speedFig, intervalDisabled, playbackStore) {
            if (!miniStore || !miniStore.d1 || !miniStore.d2) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update, window.dash_clientside.no_update, true, 0, 'Pause', 'Lap Time: 0.00s / 0.00s', {'t': 0, 'total': 0, 'lastUpdate': 0}];
            }
            
            const trigger = window.dash_clientside.callback_context.triggered[0].prop_id;
            const now = performance.now();
            const pObj = (window.Plotly || (typeof Plotly !== 'undefined' ? Plotly : null));
            if (!pObj) return window.dash_clientside.no_update;

            const binarySearch = function(arr, val) {
                let low = 0, high = arr.length - 1;
                while (low <= high) {
                    const mid = (low + high) >>> 1;
                    if (arr[mid] < val) low = mid + 1;
                    else if (arr[mid] > val) high = mid - 1;
                    else return mid;
                }
                return low;
            };

            const interpXY = function(series, tSec) {
                const t = series.t || [], x = series.x || [], y = series.y || [];
                if (!t.length || t.length !== x.length || t.length !== y.length) return null;
                if (tSec <= t[0]) return [x[0], y[0]];
                const lastI = t.length - 1;
                if (tSec >= t[lastI]) return [x[lastI], y[lastI]];
                
                const idx = binarySearch(t, tSec);
                const t0 = t[idx - 1], t1 = t[idx];
                const ratio = (tSec - t0) / Math.max(1e-6, (t1 - t0));
                return [x[idx - 1] + ratio * (x[idx] - x[idx - 1]), y[idx - 1] + ratio * (y[idx] - y[idx - 1])];
            };

            const d1Lap = miniStore.d1.lap_s || (miniStore.d1.t?.length ? miniStore.d1.t[miniStore.d1.t.length - 1] : 0);
            const d2Lap = miniStore.d2.lap_s || (miniStore.d2.t?.length ? miniStore.d2.t[miniStore.d2.t.length - 1] : 0);
            const maxLap = Math.max(d1Lap, d2Lap);

            let tSec = (playbackStore && playbackStore.t) || 0;
            let lastUpdate = (playbackStore && playbackStore.lastUpdate) || 0;
            let newIntervalDisabled = intervalDisabled;
            let btnText = 'Pause';

            if (trigger.includes('play-lap-btn')) {
                tSec = 0; lastUpdate = now; newIntervalDisabled = false; btnText = 'Pause';
            } else if (trigger.includes('pause-resume-lap-btn')) {
                if (intervalDisabled) { lastUpdate = now; newIntervalDisabled = false; btnText = 'Pause'; }
                else { newIntervalDisabled = true; btnText = 'Resume'; }
            } else if (trigger.includes('lap-playback-interval')) {
                if (intervalDisabled) return window.dash_clientside.no_update;
                tSec += (now - lastUpdate) / 1000.0;
                lastUpdate = now;
            }

            if (tSec >= maxLap) { tSec = maxLap; newIntervalDisabled = true; btnText = 'Pause'; }

            // 1. Update Mini Map
            const p1 = interpXY(miniStore.d1, tSec);
            const p2 = interpXY(miniStore.d2, tSec);
            let miniDiv = document.getElementById('mini-track-map');
            if (miniDiv && p1 && p2) {
                if (!miniDiv.data) miniDiv = miniDiv.querySelector('.js-plotly-plot') || miniDiv;
                if (miniDiv.data) {
                    pObj.restyle(miniDiv, {
                        'x': [[p1[0]], [p2[0]]], 'y': [[p1[1]], [p2[1]]],
                        'hovertemplate': [`<b>${miniStore.d1.name}</b><br>t=${tSec.toFixed(2)}s<extra></extra>`, `<b>${miniStore.d2.name}</b><br>t=${tSec.toFixed(2)}s<extra></extra>`]
                    }, [1, 2]);
                }
            }

            // 2. Update GG Diagram
            const getGGState = (key) => {
                const d = ggStore[key]; if (!d || !d.t) return null;
                const t = d.t, lat = d.lat, lng = d.long;
                if (tSec <= t[0]) return { curLat: lat[0], curLng: lng[0], trailLat: [lat[0]], trailLng: [lng[0]], name: d.driver };
                const idx = Math.min(t.length - 1, binarySearch(t, tSec));
                const trailWindow = 0.8; let start = idx;
                while (start > 0 && (tSec - t[start]) < trailWindow) start--;
                return { curLat: lat[idx], curLng: lng[idx], trailLat: lat.slice(start, idx + 1), trailLng: lng.slice(start, idx + 1), name: d.driver };
            };
            const s1 = getGGState('d1'), s2 = getGGState('d2');
            let ggDiv = document.getElementById('gg-diagram');
            if (ggDiv && (s1 || s2)) {
                if (!ggDiv.data) ggDiv = ggDiv.querySelector('.js-plotly-plot') || ggDiv;
                if (ggDiv.data) {
                    const ux = [], uy = [], uh = [], idxs = [5, 6, 7, 8, 9, 10];
                    idxs.forEach(i => {
                        const s = (i <= 7) ? s1 : s2;
                        if (!s) { ux.push([null]); uy.push([null]); uh.push(null); }
                        else {
                            const p = (i - 5) % 3;
                            if (p === 0) { ux.push([0, s.curLat]); uy.push([0, s.curLng]); uh.push(null); }
                            else if (p === 1) { ux.push(s.trailLat); uy.push(s.trailLng); uh.push(null); }
                            else { ux.push([s.curLat]); uy.push([s.curLng]); uh.push(`<b>${s.name}</b><br>${s.curLat.toFixed(2)}G, ${s.curLng.toFixed(2)}G<extra></extra>`); }
                        }
                    });
                    pObj.restyle(ggDiv, { 'x': ux, 'y': uy, 'hovertemplate': uh }, idxs);
                }
            }

            // 3. Update Speed Graph Cursor
            let speedDiv = document.getElementById('speed-graph');
            if (speedDiv) {
                if (!speedDiv.layout) speedDiv = speedDiv.querySelector('.js-plotly-plot') || speedDiv;
                if (speedDiv.layout) {
                    const d1 = miniStore.d1, distArr = d1.dist || [], tArr = d1.t || [];
                    let cDist = 0;
                    if (tSec <= tArr[0]) cDist = distArr[0];
                    else if (tSec >= tArr[tArr.length - 1]) cDist = distArr[distArr.length - 1];
                    else {
                        const i = binarySearch(tArr, tSec);
                        const ratio = (tSec - tArr[i - 1]) / Math.max(1e-6, (tArr[i] - tArr[i - 1]));
                        cDist = distArr[i - 1] + ratio * (distArr[i] - distArr[i - 1]);
                    }
                    const shapes = (speedDiv.layout.shapes || []).map(s => (s.name === 'playback-cursor' ? { ...s, x0: cDist, x1: cDist } : s));
                    if (!shapes.some(s => s.name === 'playback-cursor')) {
                        shapes.push({ type: 'line', name: 'playback-cursor', xref: 'x', yref: 'paper', x0: cDist, x1: cDist, y0: 0, y1: 1, line: { color: '#bbbbbb', width: 1.5, dash: 'dot' } });
                    }
                    pObj.relayout(speedDiv, { 'shapes': shapes });
                }
            }

            return [
                window.dash_clientside.no_update, window.dash_clientside.no_update, window.dash_clientside.no_update,
                newIntervalDisabled, trigger.includes('play-lap-btn') ? 0 : nIntervals,
                btnText, `Lap Time: ${tSec.toFixed(2)}s / ${maxLap.toFixed(2)}s`,
                {'t': tSec, 'total': maxLap, 'lastUpdate': lastUpdate}
            ];
        },

        updateGGHover: function(hoverData, ggStore, fig, playbackDisabled) {
            if (playbackDisabled === false) return window.dash_clientside.no_update;
            if (!hoverData || !ggStore || !fig || !hoverData.points) return window.dash_clientside.no_update;
            const hoverDist = hoverData.points[0].x;
            if (hoverDist === null || hoverDist === undefined) return window.dash_clientside.no_update;

            const getDriverState = (key) => {
                const d = ggStore[key];
                if (!d) return null;
                const dist = d.dist || [];
                const lat = d.lat || [];
                const lng = d.long || [];
                if (dist.length < 5) return null;
                const idx = window.dash_clientside.clientside.nearestIndex(dist, hoverDist);
                const start = Math.max(0, idx - 8);
                return {
                    curLat: lat[idx], curLng: lng[idx],
                    trailLat: lat.slice(start, idx + 1),
                    trailLng: lng.slice(start, idx + 1),
                    name: d.driver || key
                };
            };

            const s1 = getDriverState('d1');
            const s2 = getDriverState('d2');

            let graphDiv = document.getElementById('gg-diagram');
            const pObj = (window.Plotly || (typeof Plotly !== 'undefined' ? Plotly : null));
            if (graphDiv && pObj && (s1 || s2)) {
                if (!graphDiv.data) graphDiv = graphDiv.querySelector('.js-plotly-plot');
                if (graphDiv && graphDiv.data) {
                    const updateX = []; const updateY = []; const updateHover = [];
                    const indices = [5, 6, 7, 8, 9, 10];
                    indices.forEach((idx) => {
                        const s = (idx <= 7) ? s1 : s2;
                        if (!s) {
                            updateX.push([null]); updateY.push([null]); updateHover.push(null);
                        } else {
                            const part = (idx - 5) % 3;
                            if (part === 0) { // Beam
                                updateX.push([0, s.curLat]); updateY.push([0, s.curLng]); updateHover.push(null);
                            } else if (part === 1) { // Trail
                                updateX.push(s.trailLat); updateY.push(s.trailLng); updateHover.push(null);
                            } else { // Ball
                                updateX.push([s.curLat]); updateY.push([s.curLng]);
                                updateHover.push(`<b>${s.name}</b><br>Lat: ${s.curLat.toFixed(2)}G<br>Long: ${s.curLng.toFixed(2)}G<extra></extra>`);
                            }
                        }
                    });
                    pObj.restyle(graphDiv, { 'x': updateX, 'y': updateY, 'hovertemplate': updateHover }, indices);
                }
            }
            return window.dash_clientside.no_update;
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
