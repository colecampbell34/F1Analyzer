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

        showPhoneDisclaimer: function(_pathname, dismissClicks, storeData) {
            const ctx = window.dash_clientside.callback_context || {};
            const trigger = ctx.triggered && ctx.triggered[0] ? ctx.triggered[0].prop_id : '';
            const current = storeData || {};
            if (trigger === 'phone-disclaimer-dismiss-btn.n_clicks' && dismissClicks) {
                return [false, Object.assign({}, current, {dismissed: true})];
            }
            const isPhoneSize = window.matchMedia && window.matchMedia('(max-width: 768px)').matches;
            return [Boolean(isPhoneSize && !current.dismissed), current];
        },

        updateMiniMap: function(hoverData, miniStore, fig, playbackDisabled) {
            const dash = document.getElementById('live-telemetry-dashboard');
            if (playbackDisabled === false) return window.dash_clientside.no_update;
            if (!hoverData || !miniStore || !fig || !hoverData.points || hoverData.points.length === 0) {
                if (dash) dash.style.display = 'none';
                return window.dash_clientside.no_update;
            }
            const hoverDist = hoverData.points[0].x;
            if (hoverDist === null || hoverDist === undefined) {
                if (dash) dash.style.display = 'none';
                return window.dash_clientside.no_update;
            }

            const d1 = miniStore.d1 || {};
            const d2 = miniStore.d2 || {};

            const getTimeAtDistance = function(series, distanceMeters) {
                const dist = series.dist || [], times = series.t || [];
                if (dist.length < 2 || dist.length !== times.length) return 0;
                const target = distanceMeters / Math.max(1e-6, (series.dist_max || 1));
                if (target <= dist[0]) return times[0];
                if (target >= dist[dist.length - 1]) return times[times.length - 1];
                let low = 0, high = dist.length - 1;
                while (low <= high) {
                    const mid = (low + high) >>> 1;
                    if (dist[mid] < target) low = mid + 1;
                    else if (dist[mid] > target) high = mid - 1;
                    else return times[mid];
                }
                const ratio = (target - dist[low - 1]) / Math.max(1e-6, (dist[low] - dist[low - 1]));
                return times[low - 1] + ratio * (times[low] - times[low - 1]);
            };

            const refSeries = (miniStore.delta && miniStore.delta.reference === 'd1') ? d1 : d2;
            const tSec = getTimeAtDistance(refSeries, hoverDist);

            const interpXY = function(series, t) {
                const ts = series.t || [], xs = series.x || [], ys = series.y || [];
                if (!ts.length) return null;
                if (t <= ts[0]) return [xs[0], ys[0]];
                if (t >= ts[ts.length - 1]) return [xs[ts.length - 1], ys[ts.length - 1]];
                let low = 0, high = ts.length - 1;
                while (low <= high) {
                    const mid = (low + high) >>> 1;
                    if (ts[mid] < t) low = mid + 1;
                    else if (ts[mid] > t) high = mid - 1;
                    else return [xs[mid], ys[mid]];
                }
                const ratio = (t - ts[low - 1]) / Math.max(1e-6, (ts[low] - ts[low - 1]));
                return [
                    xs[low - 1] + ratio * (xs[low] - xs[low - 1]),
                    ys[low - 1] + ratio * (ys[low] - ys[low - 1])
                ];
            };
            
            // Update Live Dashboard during hover (always responsive)
            window.dash_clientside.clientside.updateLiveDashboard(tSec, miniStore, true, hoverDist);

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

            const interpMetric = function(series, t, metric) {
                const ts = series.t || [], values = series[metric] || [];
                if (!ts.length || ts.length !== values.length) return 0;
                if (t <= ts[0]) return values[0];
                if (t >= ts[ts.length - 1]) return values[values.length - 1];
                const idx = binarySearch(ts, t);
                const t0 = ts[idx - 1], t1 = ts[idx];
                const ratio = (t - t0) / Math.max(1e-6, (t1 - t0));
                return values[idx - 1] + ratio * (values[idx] - values[idx - 1]);
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
                const dash = document.getElementById('live-telemetry-dashboard');
                if (dash) delete dash.dataset.lastHalfSecond;
            } else if (trigger.includes('pause-resume-lap-btn')) {
                if (intervalDisabled) { lastUpdate = now; newIntervalDisabled = false; btnText = 'Pause'; }
                else { newIntervalDisabled = true; btnText = 'Resume'; }
            } else if (trigger.includes('lap-playback-interval')) {
                if (intervalDisabled) return window.dash_clientside.no_update;
                tSec += (now - lastUpdate) / 1000.0;
                lastUpdate = now;
            }

            if (tSec >= maxLap) { tSec = maxLap; newIntervalDisabled = true; btnText = 'Pause'; }

            // Update Live Dashboard (throttled during playback)
            const deltaRef = (miniStore.delta && miniStore.delta.reference === 'd1') ? miniStore.d1 : miniStore.d2;
            const playbackDistM = interpMetric(
                deltaRef,
                Math.min(tSec, deltaRef.lap_s || tSec),
                'dist'
            ) * (deltaRef.dist_max || 1);
            window.dash_clientside.clientside.updateLiveDashboard(tSec, miniStore, false, playbackDistM);

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
                const curLat = interpMetric(d, tSec, 'lat');
                const curLng = interpMetric(d, tSec, 'long');
                const trailWindow = 0.8; let start = idx;
                while (start > 0 && (tSec - t[start]) < trailWindow) start--;
                return {
                    curLat: curLat,
                    curLng: curLng,
                    trailLat: lat.slice(start, idx + 1).concat([curLat]),
                    trailLng: lng.slice(start, idx + 1).concat([curLng]),
                    name: d.driver
                };
            };
            const s1 = ggStore ? getGGState('d1') : null;
            const s2 = ggStore ? getGGState('d2') : null;
            let ggDiv = document.getElementById('gg-diagram');
            if (ggDiv && (s1 || s2)) {
                if (!ggDiv.data) ggDiv = ggDiv.querySelector('.js-plotly-plot') || ggDiv;
                if (ggDiv.data) {
                    const ux = [], uy = [], uh = [], idxs = [7, 8, 9, 10, 11, 12];
                    idxs.forEach(i => {
                        const s = (i <= 9) ? s1 : s2;
                        if (!s) { ux.push([null]); uy.push([null]); uh.push(null); }
                        else {
                            const p = (i - 7) % 3;
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
                    const ref = deltaRef, distArr = ref.dist || [], tArr = ref.t || [];
                    let cDist = 0;
                    if (tSec <= tArr[0]) cDist = distArr[0];
                    else if (tSec >= tArr[tArr.length - 1]) cDist = distArr[distArr.length - 1];
                    else {
                        const i = binarySearch(tArr, tSec);
                        const ratio = (tSec - tArr[i - 1]) / Math.max(1e-6, (tArr[i] - tArr[i - 1]));
                        cDist = distArr[i - 1] + ratio * (distArr[i] - distArr[i - 1]);
                    }
                    // Scale back to meters for the chart cursor
                    const cDistM = cDist * (ref.dist_max || 1);
                    const shapes = (speedDiv.layout.shapes || []).map(s => (s.name === 'playback-cursor' ? { ...s, x0: cDistM, x1: cDistM } : s));
                    if (!shapes.some(s => s.name === 'playback-cursor')) {
                        shapes.push({ type: 'line', name: 'playback-cursor', xref: 'x', yref: 'paper', x0: cDistM, x1: cDistM, y0: 0, y1: 1, line: { color: '#bbbbbb', width: 1.5, dash: 'dot' } });
                    }
                    pObj.relayout(speedDiv, { 'shapes': shapes });
                }
            }

            if (newIntervalDisabled && !trigger.includes('pause-resume-lap-btn') && tSec >= maxLap) {
                 const dash = document.getElementById('live-telemetry-dashboard');
                 if (dash) dash.style.display = 'none';
            }

            return [
                window.dash_clientside.no_update, window.dash_clientside.no_update, window.dash_clientside.no_update,
                newIntervalDisabled, trigger.includes('play-lap-btn') ? 0 : nIntervals,
                btnText, `Lap Time: ${tSec.toFixed(2)}s / ${maxLap.toFixed(2)}s`,
                {'t': tSec, 'total': maxLap, 'lastUpdate': lastUpdate}
            ];
        },

        updateLiveDashboard: function(tSec, miniStore, hoverMode, deltaDistanceMeters) {
            const dash = document.getElementById('live-telemetry-dashboard');
            if (!dash) return;
            if (!miniStore || !miniStore.d1 || !miniStore.d2) {
                dash.style.display = 'none';
                delete dash.dataset.lastHalfSecond;
                return;
            }
            if (dash.style.display === 'none') delete dash.dataset.lastHalfSecond;
            dash.style.display = 'block';

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

            const interpMetric = function(series, t, metric) {
                const ts = series.t || [], m = series[metric] || [];
                if (!ts.length || ts.length !== m.length) return 0;
                if (t <= ts[0]) return m[0];
                if (t >= ts[ts.length - 1]) return m[m.length - 1];
                const idx = binarySearch(ts, t);
                const t0 = ts[idx - 1], t1 = ts[idx];
                const ratio = (t - t0) / Math.max(1e-6, (t1 - t0));
                return m[idx - 1] + ratio * (m[idx] - m[idx - 1]);
            };

            const updateDriver = (id, data, t) => {
                const nameEl = document.getElementById(`live-${id}-name`);
                const speedEl = document.getElementById(`live-${id}-speed`);
                const gearEl = document.getElementById(`live-${id}-gear`);
                const rpmEl = document.getElementById(`live-${id}-rpm`);
                if (nameEl) { nameEl.innerText = data.name; nameEl.style.color = data.color; }
                if (speedEl) speedEl.innerText = Math.round(interpMetric(data, t, 'speed'));
                if (gearEl) gearEl.innerText = Math.round(interpMetric(data, t, 'gear'));
                if (rpmEl) rpmEl.innerText = Math.round(interpMetric(data, t, 'rpm'));
            };

            updateDriver('d1', miniStore.d1, tSec);
            updateDriver('d2', miniStore.d2, tSec);

            // Delta at distance - Throttle to update only twice per second during playback,
            // but update every frame during hover for responsiveness.
            const currentHalfSecond = Math.floor(tSec * 2);
            if (dash.dataset.lastHalfSecond !== String(currentHalfSecond) || hoverMode) {
                dash.dataset.lastHalfSecond = currentHalfSecond;
                const getDeltaAtDistance = (targetD) => {
                    const delta = miniStore.delta || {};
                    const d = delta.dist || [], values = delta.value || [];
                    if (d.length < 2 || d.length !== values.length) return null;
                    if (targetD <= d[0]) return values[0];
                    if (targetD >= d[d.length - 1]) return values[values.length - 1];
                    let low = 0, high = d.length - 1;
                    while (low <= high) {
                        const mid = (low + high) >>> 1;
                        if (d[mid] < targetD) low = mid + 1;
                        else if (d[mid] > targetD) high = mid - 1;
                        else return values[mid];
                    }
                    const ratio = (targetD - d[low - 1]) / Math.max(1e-6, (d[low] - d[low - 1]));
                    return values[low - 1] + ratio * (values[low] - values[low - 1]);
                };

                const d1 = miniStore.d1, d2 = miniStore.d2;
                const primaryName = (miniStore.delta && miniStore.delta.primary) || d1.name;
                const secondaryName = (miniStore.delta && miniStore.delta.secondary) || d2.name;
                let targetDistance = deltaDistanceMeters;
                if (targetDistance === null || targetDistance === undefined) {
                    const refSeries = (miniStore.delta && miniStore.delta.reference === 'd1') ? d1 : d2;
                    targetDistance = interpMetric(
                        refSeries,
                        Math.min(tSec, refSeries.lap_s || tSec),
                        'dist'
                    ) * (refSeries.dist_max || 1);
                }
                const delta = getDeltaAtDistance(targetDistance);
                const deltaEl = document.getElementById('live-delta-value');
                const deltaLabelEl = document.querySelector('.delta-label');

                if (deltaEl && deltaLabelEl && delta !== null) {
                    deltaLabelEl.innerText = `${primaryName || 'D1'} GAP TO ${secondaryName || 'D2'}`;
                    deltaEl.innerText = (delta >= 0 ? '-' : '+') + Math.abs(delta).toFixed(3) + 's';
                    deltaEl.style.color = delta >= 0 ? '#00ff00' : '#ff4444';
                }
            }
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

                const interpolateByDistance = function(series, targetD, metric) {
                    const dArr = series.dist || [], values = series[metric] || [];
                    if (!dArr.length || dArr.length !== values.length) return 0;
                    if (targetD <= dArr[0]) return values[0];
                    if (targetD >= dArr[dArr.length - 1]) return values[values.length - 1];
                    let low = 0, high = dArr.length - 1;
                    while (low <= high) {
                        const mid = (low + high) >>> 1;
                        if (dArr[mid] < targetD) low = mid + 1;
                        else if (dArr[mid] > targetD) high = mid - 1;
                        else return values[mid];
                    }
                    const ratio = (targetD - dArr[low - 1]) / Math.max(1e-6, (dArr[low] - dArr[low - 1]));
                    return values[low - 1] + ratio * (values[low] - values[low - 1]);
                };

                const curLat = interpolateByDistance(d, hoverDist, 'lat');
                const curLng = interpolateByDistance(d, hoverDist, 'long');
                const start = Math.max(0, idx - 12);
                return {
                    curLat: curLat, curLng: curLng,
                    trailLat: lat.slice(start, idx + 1).concat([curLat]),
                    trailLng: lng.slice(start, idx + 1).concat([curLng]),
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
                    const indices = [7, 8, 9, 10, 11, 12];
                    indices.forEach((idx) => {
                        const s = (idx <= 9) ? s1 : s2;
                        if (!s) {
                            updateX.push([null]); updateY.push([null]); updateHover.push(null);
                        } else {
                            const part = (idx - 7) % 3;
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



        toggleFeedbackModal: function(open_clicks, mobile_open_clicks, cancel_clicks, refresh_data, is_open) {
            const trigger = window.dash_clientside.callback_context.triggered[0].prop_id;
            if (trigger === 'open-feedback-modal-btn.n_clicks' || trigger === 'mobile-open-feedback-modal-btn.n_clicks') return true;
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
        },
        
        copyToClipboard: function(n_clicks, mobile_clicks) {
            const ctx = window.dash_clientside.callback_context || {};
            const trigger = (ctx.triggered && ctx.triggered[0] && ctx.triggered[0].prop_id) || '';
            if (!trigger || ((n_clicks || 0) + (mobile_clicks || 0)) === 0) return false;
            const url = window.location.href;
            const el = document.createElement('textarea');
            el.value = url;
            document.body.appendChild(el);
            el.select();
            document.execCommand('copy');
            document.body.removeChild(el);
            return true;
        },

        graphIdForTab: function(activeTab) {
            const ids = {
                'tab-telemetry': 'speed-graph',
                'tab-trackmap': '2d-dominance-graph',
                'tab-strategy': 'strategy-graph',
                'tab-race': 'race-gaps-graph',
                'tab-gridpace': 'grid-pace-graph'
            };
            return ids[activeTab] || null;
        },

        resizeVisiblePlots: function(activeTab, speedFigure) {
            if (window.f1AnalyzerSchedulePlotResize) {
                window.f1AnalyzerSchedulePlotResize();
            }
            return activeTab || '';
        },

        safeFilename: function(text) {
            return String(text || 'f1-analysis')
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, '-')
                .replace(/^-+|-+$/g, '')
                .slice(0, 80) || 'f1-analysis';
        },

        downloadActiveChart: function(n_clicks, activeTab, title) {
            if (!n_clicks) return window.dash_clientside.no_update;
            const graphId = window.dash_clientside.clientside.graphIdForTab(activeTab);
            if (!graphId) return 'No downloadable chart is active on this tab.';
            const container = document.getElementById(graphId);
            const plot = container ? (container.querySelector('.js-plotly-plot') || container) : null;
            const pObj = (window.Plotly || (typeof Plotly !== 'undefined' ? Plotly : null));
            if (!plot || !pObj || !plot.data) return 'Chart is not ready to download yet.';
            const filename = window.dash_clientside.clientside.safeFilename(title || graphId);
            try {
                pObj.downloadImage(plot, {
                    format: 'png',
                    width: 1600,
                    height: 900,
                    filename: filename
                });
                return 'Chart download started.';
            } catch (err) {
                return 'Chart download failed. Try again after the chart finishes loading.';
            }
        }
    }
});

if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/service-worker.js').catch(function() {});
    });
}

(function() {
    const plotIds = [
        'speed-graph',
        'mini-track-map',
        'gg-diagram',
        '2d-dominance-graph',
        'strategy-graph',
        'deg-graph',
        'race-gaps-graph',
        'pit-stops-graph',
        'grid-pace-graph'
    ];

    const resizeVisiblePlots = function() {
        const pObj = (window.Plotly || (typeof Plotly !== 'undefined' ? Plotly : null));
        if (!pObj || !pObj.Plots || !pObj.Plots.resize) return;
        plotIds.forEach(function(id) {
            const container = document.getElementById(id);
            if (!container) return;
            const plot = container.querySelector('.js-plotly-plot') || container;
            if (!plot || !plot.data) return;
            const rect = plot.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return;
            pObj.Plots.resize(plot);
        });
    };

    window.f1AnalyzerSchedulePlotResize = function() {
        [0, 120, 360, 720, 1200].forEach(function(delay) {
            window.setTimeout(resizeVisiblePlots, delay);
        });
    };

    window.addEventListener('resize', window.f1AnalyzerSchedulePlotResize);
    window.addEventListener('load', window.f1AnalyzerSchedulePlotResize);
    window.setTimeout(window.f1AnalyzerSchedulePlotResize, 800);
    document.addEventListener('visibilitychange', function() {
        if (!document.hidden) window.f1AnalyzerSchedulePlotResize();
    });
    document.addEventListener('click', function(event) {
        if (event.target && event.target.closest && event.target.closest('#update-dashboard-btn')) {
            const root = document.getElementById('app-root');
            const isPhoneSize = window.matchMedia && window.matchMedia('(max-width: 768px)').matches;
            if (root && isPhoneSize) {
                root.classList.add('mobile-load-pending');
            }
        }
        if (event.target && event.target.closest && event.target.closest('.tab')) {
            window.f1AnalyzerSchedulePlotResize();
        }
    });
    if (window.MutationObserver) {
        const observer = new MutationObserver(function(mutations) {
            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (!node || node.nodeType !== 1) continue;
                    if (
                        (node.id && plotIds.includes(node.id)) ||
                        (node.classList && node.classList.contains('js-plotly-plot')) ||
                        (node.querySelector && node.querySelector('.js-plotly-plot'))
                    ) {
                        window.f1AnalyzerSchedulePlotResize();
                        return;
                    }
                }
            }
        });
        observer.observe(document.body, {childList: true, subtree: true});
    }
})();
