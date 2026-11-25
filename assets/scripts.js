/*
 * Replay deliberately lives outside Dash's callback/render cycle.  Dash still
 * supplies the bounded telemetry payload and owns the controls, but animation
 * frames update the replay map on a canvas so marker motion is independent of
 * Plotly's asynchronous redraw and camera transition queues.
 */
(function() {
    const state = {
        running: false,
        frameId: null,
        miniStore: null,
        ggStore: null,
        t: 0,
        total: 0,
        clockOriginMs: null,
        clockOriginT: 0,
        lastAuxiliaryFrame: 0,
        lastLabelFrame: 0,
        lastCameraUpdate: 0,
        camera: null,
        trackBounds: null,
        mapCanvas: null,
        mapCanvasContext: null,
        mapCanvasParent: null,
        mapTrackSource: null,
        mapTrackPath: null,
        mapHiddenElements: [],
        mapParentPosition: null
    };

    const plotly = function() {
        return window.Plotly || (typeof Plotly !== 'undefined' ? Plotly : null);
    };
    const plot = function(id) {
        const container = document.getElementById(id);
        return container ? (container.querySelector('.js-plotly-plot') || container) : null;
    };
    const binarySearch = function(values, target) {
        let low = 0;
        let high = values.length - 1;
        while (low <= high) {
            const middle = (low + high) >>> 1;
            if (values[middle] < target) low = middle + 1;
            else if (values[middle] > target) high = middle - 1;
            else return middle;
        }
        return low;
    };
    const interpolate = function(series, time, metric) {
        const times = series.t || [];
        const values = series[metric] || [];
        if (!times.length || times.length !== values.length) return 0;
        if (time <= times[0]) return values[0];
        if (time >= times[times.length - 1]) return values[times.length - 1];
        const index = binarySearch(times, time);
        const start = times[index - 1];
        const end = times[index];
        const ratio = (time - start) / Math.max(1e-6, end - start);
        return values[index - 1] + ratio * (values[index] - values[index - 1]);
    };
    const positionAt = function(series, time) {
        return [interpolate(series, time, 'x'), interpolate(series, time, 'y')];
    };
    const advanceReplayClock = function(now) {
        if (state.clockOriginMs === null) {
            state.clockOriginMs = now;
            state.clockOriginT = state.t;
        }
        state.t = Math.min(
            state.total,
            state.clockOriginT + Math.max(0, now - state.clockOriginMs) / 1000
        );
        return state.t;
    };
    const updateText = function() {
        const timeLabel = document.getElementById('lap-playback-time-label');
        const pauseButton = document.getElementById('pause-resume-lap-btn');
        if (timeLabel) timeLabel.textContent = `Lap Time: ${state.t.toFixed(2)}s / ${state.total.toFixed(2)}s`;
        if (pauseButton) pauseButton.textContent = state.running ? 'Pause' : (state.t >= state.total ? 'Replay' : 'Resume');
    };
    const shouldFollowCars = function() {
        const toggle = document.querySelector('#mini-map-follow-toggle input[type="checkbox"]');
        return !toggle || Boolean(toggle.checked);
    };
    const activateReplayMap = function(mini) {
        if (!mini) return null;
        if (!state.mapCanvas || state.mapCanvasParent !== mini || !state.mapCanvas.isConnected) {
            const computedPosition = window.getComputedStyle(mini).position;
            if (computedPosition === 'static') {
                state.mapParentPosition = mini.style.position;
                mini.style.position = 'relative';
            }
            state.mapCanvas = document.createElement('canvas');
            state.mapCanvas.className = 'f1-replay-map-canvas';
            state.mapCanvas.setAttribute('aria-hidden', 'true');
            Object.assign(state.mapCanvas.style, {
                position: 'absolute', inset: '0', width: '100%', height: '100%',
                pointerEvents: 'none', zIndex: '3'
            });
            mini.appendChild(state.mapCanvas);
            state.mapCanvasContext = state.mapCanvas.getContext('2d');
            state.mapCanvasParent = mini;
            state.mapTrackSource = null;
            state.mapTrackPath = null;
        }
        const svg = mini.querySelector('.svg-container');
        if (svg && svg.style.visibility !== 'hidden') {
            state.mapHiddenElements.push({element: svg, visibility: svg.style.visibility});
            svg.style.visibility = 'hidden';
        }
        return state.mapCanvasContext;
    };
    const deactivateReplayMap = function() {
        state.mapHiddenElements.forEach(function(item) {
            if (item.element && item.element.isConnected) item.element.style.visibility = item.visibility;
        });
        state.mapHiddenElements = [];
        if (state.mapCanvas && state.mapCanvas.isConnected) state.mapCanvas.remove();
        if (state.mapCanvasParent && state.mapParentPosition !== null) {
            state.mapCanvasParent.style.position = state.mapParentPosition;
        }
        state.mapCanvas = null;
        state.mapCanvasContext = null;
        state.mapCanvasParent = null;
        state.mapTrackSource = null;
        state.mapTrackPath = null;
        state.mapParentPosition = null;
    };
    const buildMapTrackPath = function(track) {
        const path = new Path2D();
        let started = false;
        for (let i = 0; i < track.x.length; i++) {
            const x = Number(track.x[i]), y = Number(track.y[i]);
            if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
            if (!started) {
                path.moveTo(x, y);
                started = true;
            } else {
                path.lineTo(x, y);
            }
        }
        return path;
    };
    const drawReplayMap = function(mini, first, second) {
        const store = state.miniStore;
        const track = store && store.track;
        const ctx = activateReplayMap(mini);
        if (!ctx || !track || !track.x || !track.y || !track.x.length || !track.y.length) return;
        if (state.mapTrackSource !== track) {
            state.mapTrackPath = buildMapTrackPath(track);
            state.mapTrackSource = track;
        }

        const rect = mini.getBoundingClientRect();
        const width = rect.width, height = rect.height;
        if (!width || !height) return;
        const dpr = Math.max(1, window.devicePixelRatio || 1);
        const pixelWidth = Math.round(width * dpr), pixelHeight = Math.round(height * dpr);
        if (state.mapCanvas.width !== pixelWidth || state.mapCanvas.height !== pixelHeight) {
            state.mapCanvas.width = pixelWidth;
            state.mapCanvas.height = pixelHeight;
            state.mapCanvas.style.width = `${width}px`;
            state.mapCanvas.style.height = `${height}px`;
        }

        const camera = state.camera || state.trackBounds;
        if (!camera) return;
        const rangeX = Math.max(1e-6, camera.x1 - camera.x0);
        const rangeY = Math.max(1e-6, camera.y1 - camera.y0);
        const scale = Math.min(width / rangeX, height / rangeY);
        const offsetX = (width - rangeX * scale) / 2;
        const offsetY = (height - rangeY * scale) / 2;

        ctx.clearRect(0, 0, pixelWidth, pixelHeight);
        ctx.setTransform(
            dpr * scale, 0, 0, -dpr * scale,
            dpr * (offsetX - camera.x0 * scale),
            dpr * (offsetY + camera.y1 * scale)
        );
        ctx.strokeStyle = '#444';
        ctx.lineWidth = 2 / scale;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.stroke(state.mapTrackPath);

        const drawMarker = function(position, color) {
            const x = offsetX + (position[0] - camera.x0) * scale;
            const y = offsetY + (camera.y1 - position[1]) * scale;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.beginPath();
            ctx.arc(x, y, 5.5, 0, Math.PI * 2);
            ctx.fillStyle = color || '#f7f7f3';
            ctx.fill();
            ctx.lineWidth = 1.5;
            ctx.strokeStyle = '#fff';
            ctx.stroke();
            ctx.setTransform(
                dpr * scale, 0, 0, -dpr * scale,
                dpr * (offsetX - camera.x0 * scale),
                dpr * (offsetY + camera.y1 * scale)
            );
        };
        drawMarker(first, store.d1.color);
        drawMarker(second, store.d2.color);
        ctx.setTransform(1, 0, 0, 1, 0, 0);
    };
    const updateMapCamera = function(first, second, now) {
        const track = state.miniStore && state.miniStore.track;
        if (!track || !track.x || !track.y || !track.x.length || !track.y.length) return;
        if (!state.trackBounds) {
            const minX = Math.min.apply(null, track.x);
            const maxX = Math.max.apply(null, track.x);
            const minY = Math.min.apply(null, track.y);
            const maxY = Math.max.apply(null, track.y);
            const span = Math.max(maxX - minX, maxY - minY, 1);
            const margin = span * 0.05;
            state.trackBounds = {
                x0: minX - margin, x1: maxX + margin,
                y0: minY - margin, y1: maxY + margin,
                span: span + margin * 2
            };
        }
        const fullSpan = state.trackBounds.span;
        const full = state.trackBounds;
        const followEnabled = shouldFollowCars();
        let target = full;
        if (followEnabled) {
            const gap = Math.hypot(first[0] - second[0], first[1] - second[1]);
            // Zoom continuously with the cars' separation; avoid a threshold
            // that snaps between the local view and the whole circuit.
            const scale = Math.min(fullSpan * 1.2, Math.max(fullSpan * 0.2, gap * 3.4, 120));
            const centerX = (first[0] + second[0]) / 2;
            const centerY = (first[1] + second[1]) / 2;
            target = {
                x0: centerX - scale / 2,
                x1: centerX + scale / 2,
                y0: centerY - scale / 2,
                y1: centerY + scale / 2
            };
        }
        if (!state.camera) state.camera = {...full};
        else {
            // Use elapsed time rather than a fixed amount so the camera has
            // the same glide on fast and slower displays.
            const elapsed = Math.max(1, now - state.lastCameraUpdate);
            const ease = 1 - Math.exp(-elapsed / 500);
            ['x0', 'x1', 'y0', 'y1'].forEach(function(key) {
                state.camera[key] += (target[key] - state.camera[key]) * ease;
            });
        }
        state.lastCameraUpdate = now;
    };
    const updateMap = function(now) {
        const mini = plot('mini-track-map');
        if (!mini || !state.miniStore) return;
        const rawP1 = positionAt(state.miniStore.d1, state.t);
        const rawP2 = positionAt(state.miniStore.d2, state.t);
        updateMapCamera(rawP1, rawP2, now);
        drawReplayMap(mini, rawP1, rawP2);
    };
    const updateGG = function(pObj) {
        const diagram = plot('gg-diagram');
        if (!diagram || !diagram.data || !state.ggStore) return;
        const getDriverState = function(key) {
            const series = state.ggStore[key];
            if (!series || !series.t || series.t.length < 2) return null;
            const index = Math.min(series.t.length - 1, binarySearch(series.t, state.t));
            const start = Math.max(0, index - 16);
            const lat = interpolate(series, state.t, 'lat');
            const longitudinal = interpolate(series, state.t, 'long');
            return {
                lat: lat,
                longitudinal: longitudinal,
                trailLat: series.lat.slice(start, index + 1).concat([lat]),
                trailLong: series.long.slice(start, index + 1).concat([longitudinal]),
                name: series.driver || key
            };
        };
        const first = getDriverState('d1');
        const second = getDriverState('d2');
        const xs = [];
        const ys = [];
        const labels = [];
        [first, second].forEach(function(driver) {
            if (!driver) {
                xs.push([null], [null], [null]);
                ys.push([null], [null], [null]);
                labels.push(null, null, null);
                return;
            }
            xs.push([0, driver.lat], driver.trailLat, [driver.lat]);
            ys.push([0, driver.longitudinal], driver.trailLong, [driver.longitudinal]);
            labels.push(null, null, `<b>${driver.name}</b><br>Lat: ${driver.lat.toFixed(2)}G<br>Long: ${driver.longitudinal.toFixed(2)}G<extra></extra>`);
        });
        pObj.restyle(diagram, {x: xs, y: ys, hovertemplate: labels}, [7, 8, 9, 10, 11, 12]);
    };
    const updateSpeedCursor = function(pObj) {
        const graph = plot('speed-graph');
        if (!graph || !graph.layout || !state.miniStore) return;
        const delta = state.miniStore.delta || {};
        const reference = delta.reference === 'd1' ? state.miniStore.d1 : state.miniStore.d2;
        const distance = interpolate(reference, Math.min(state.t, reference.lap_s || state.t), 'dist') * (reference.dist_max || 1);
        const shapes = (graph.layout.shapes || []).map(function(shape) {
            return shape.name === 'playback-cursor' ? {...shape, x0: distance, x1: distance} : shape;
        });
        if (!shapes.some(function(shape) { return shape.name === 'playback-cursor'; })) {
            shapes.push({type: 'line', name: 'playback-cursor', xref: 'x', yref: 'paper', x0: distance, x1: distance, y0: 0, y1: 1, line: {color: '#bbbbbb', width: 1.5, dash: 'dot'}});
        }
        pObj.relayout(graph, {shapes: shapes});
    };
    const draw = function(now) {
        if (!state.running || !state.miniStore) return;
        advanceReplayClock(now);
        const pObj = plotly();
        if (pObj) {
            updateMap(now);
            // Secondary plots are still responsive, but do not need to compete
            // with position animation for every display frame.
            if (now - state.lastAuxiliaryFrame >= 66) {
                updateGG(pObj);
                updateSpeedCursor(pObj);
                const ref = (state.miniStore.delta || {}).reference === 'd1' ? state.miniStore.d1 : state.miniStore.d2;
                const progress = interpolate(ref, Math.min(state.t, ref.lap_s || state.t), 'dist');
                if (window.dash_clientside && window.dash_clientside.clientside) {
                    window.dash_clientside.clientside.updateLiveDashboard(state.t, state.miniStore, false, progress);
                }
                state.lastAuxiliaryFrame = now;
            }
        }
        if (now - state.lastLabelFrame >= 50 || state.t >= state.total) {
            updateText();
            state.lastLabelFrame = now;
        }
        if (state.t >= state.total) {
            state.running = false;
            state.frameId = null;
            state.clockOriginMs = null;
            updateText();
            return;
        }
        state.frameId = window.requestAnimationFrame(draw);
    };
    const play = function(miniStore, ggStore, restart) {
        if (!miniStore || !miniStore.d1 || !miniStore.d2) return false;
        state.miniStore = miniStore;
        state.ggStore = ggStore || {};
        state.total = Math.max(
            miniStore.d1.lap_s || (miniStore.d1.t || []).slice(-1)[0] || 0,
            miniStore.d2.lap_s || (miniStore.d2.t || []).slice(-1)[0] || 0
        );
        if (!state.total) return false;
        if (restart || state.t >= state.total) state.t = 0;
        state.running = true;
        state.clockOriginMs = performance.now();
        state.clockOriginT = state.t;
        state.lastAuxiliaryFrame = 0;
        state.lastLabelFrame = 0;
        state.lastCameraUpdate = 0;
        state.camera = null;
        state.trackBounds = null;
        state.mapTrackSource = null;
        state.mapTrackPath = null;
        if (state.frameId !== null) window.cancelAnimationFrame(state.frameId);
        updateText();
        state.frameId = window.requestAnimationFrame(draw);
        return true;
    };
    window.f1AnalyzerPlayback = {
        isRunning: function() { return state.running; },
        deactivateMapOverlay: deactivateReplayMap,
        start: function(miniStore, ggStore) { return play(miniStore, ggStore, true); },
        toggle: function(miniStore, ggStore) {
            if (state.running) {
                advanceReplayClock(performance.now());
                state.running = false;
                state.clockOriginMs = null;
                if (state.frameId !== null) window.cancelAnimationFrame(state.frameId);
                state.frameId = null;
                updateText();
                return true;
            }
            return play(miniStore || state.miniStore, ggStore || state.ggStore, false);
        },
        stop: function() {
            state.running = false;
            state.clockOriginMs = null;
            if (state.frameId !== null) window.cancelAnimationFrame(state.frameId);
            state.frameId = null;
            deactivateReplayMap();
            updateText();
        }
    };
    document.addEventListener('visibilitychange', function() {
        if (document.hidden && state.running) {
            advanceReplayClock(performance.now());
            state.clockOriginMs = null;
        }
    });
})();

(function() {
    let dragBound = false;
    const bindAIPanelDrag = function() {
        const panel = document.getElementById('ai-analysis-panel');
        const handle = document.getElementById('ai-panel-drag-handle');
        if (!panel || !handle || dragBound) return;
        dragBound = true;
        handle.addEventListener('pointerdown', function(event) {
            if (event.target.closest('button')) return;
            const rect = panel.getBoundingClientRect();
            const offsetX = event.clientX - rect.left;
            const offsetY = event.clientY - rect.top;
            panel.style.left = rect.left + 'px';
            panel.style.top = rect.top + 'px';
            panel.style.right = 'auto';
            panel.style.bottom = 'auto';
            handle.setPointerCapture(event.pointerId);
            const move = function(moveEvent) {
                const left = Math.max(0, Math.min(window.innerWidth - panel.offsetWidth, moveEvent.clientX - offsetX));
                const top = Math.max(0, Math.min(window.innerHeight - 60, moveEvent.clientY - offsetY));
                panel.style.left = left + 'px';
                panel.style.top = top + 'px';
            };
            const stop = function() {
                handle.removeEventListener('pointermove', move);
                handle.removeEventListener('pointerup', stop);
                handle.removeEventListener('pointercancel', stop);
            };
            handle.addEventListener('pointermove', move);
            handle.addEventListener('pointerup', stop);
            handle.addEventListener('pointercancel', stop);
        });
    };
    new MutationObserver(bindAIPanelDrag).observe(document.documentElement, {childList: true, subtree: true});
    document.addEventListener('DOMContentLoaded', bindAIPanelDrag);
    window.setTimeout(bindAIPanelDrag, 500);
})();

(function() {
    const state = {activeTab: null, visible: false};
    const labels = {
        'tab-telemetry': 'Preparing telemetry',
        'tab-trackmap': 'Preparing track map',
        'tab-strategy': 'Preparing strategy analysis',
        'tab-racepace': 'Preparing race and pace'
    };
    const activePlotForTab = function(tab) {
        return {
            'tab-telemetry': 'speed-graph',
            'tab-trackmap': '2d-dominance-graph',
            'tab-strategy': 'strategy-graph',
            'tab-racepace': 'race-gaps-graph'
        }[tab];
    };
    const overlay = function() { return document.getElementById('view-loading-overlay'); };
    const setCopy = function(tab, status) {
        const title = document.getElementById('view-loading-title');
        const detail = document.getElementById('view-loading-detail');
        if (title) title.textContent = labels[tab] || 'Preparing analysis';
        if (!detail) return;
        const profile = status && status.profile ? `${status.profile} data` : 'data';
        if (status && status.status === 'queued') detail.textContent = `Queued: loading ${profile} for this view…`;
        else if (status && status.status === 'loading') detail.textContent = `Loading ${profile}; the analysis will appear here automatically…`;
        else if (status && status.status === 'direct') detail.textContent = `Loading ${profile} for this view…`;
        else detail.textContent = 'Loading the data this view needs…';
    };
    const isViewReady = function(tab) {
        const graphId = activePlotForTab(tab);
        if (!graphId) return true;
        const container = document.getElementById(graphId);
        const graph = container && (container.querySelector('.js-plotly-plot') || container);
        if (!graph) return false;
        if (container && container.getAttribute('data-dash-is-loading') === 'true') return false;
        if (graph.data && graph.data.length) return true;
        // Error/not-applicable figures intentionally have no traces. They are
        // still a completed response, unlike the untouched "Choose a session"
        // placeholder.
        const annotations = (graph.layout && graph.layout.annotations) || [];
        return annotations.some(function(annotation) {
            return annotation.text && !String(annotation.text).includes('Choose a session');
        });
    };
    const show = function(tab, status) {
        state.activeTab = tab;
        state.visible = true;
        const node = overlay();
        if (node) node.classList.add('is-visible');
        const root = document.getElementById('app-root');
        if (root) root.classList.add('view-is-loading');
        setCopy(tab, status);
    };
    const hide = function() {
        state.visible = false;
        const node = overlay();
        if (node) node.classList.remove('is-visible');
        const root = document.getElementById('app-root');
        if (root) root.classList.remove('view-is-loading');
    };
    const check = function() {
        if (state.visible && isViewReady(state.activeTab)) hide();
    };
    window.f1AnalyzerViewLoading = {
        sync: function(tab, status) {
            const changedView = state.activeTab !== tab;
            const loading = status && ['queued', 'loading', 'direct'].includes(status.status);
            // Before a comparison is requested there is nothing to wait for.
            // Leaving the overlay up here obscures the helpful empty state and
            // makes the dashboard look as though it has stalled.
            if (!status || status.status === 'idle' || status.status === 'error') {
                state.activeTab = tab;
                hide();
                return;
            }
            if (changedView || loading) show(tab, status);
            else if (status && status.status === 'ready') {
                setCopy(tab, status);
                window.requestAnimationFrame(check);
            }
        },
        check: check,
        hide: hide
    };
    if (window.MutationObserver) {
        const observe = function() {
            if (!document.body) return;
            new MutationObserver(function() {
                window.requestAnimationFrame(check);
            }).observe(document.body, {childList: true, subtree: true});
        };
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', observe, {once: true});
        else observe();
    }
})();

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
            if (playbackDisabled === false || (window.f1AnalyzerPlayback && window.f1AnalyzerPlayback.isRunning())) {
                return window.dash_clientside.no_update;
            }
            if (window.f1AnalyzerPlayback && window.f1AnalyzerPlayback.deactivateMapOverlay) {
                window.f1AnalyzerPlayback.deactivateMapOverlay();
            }
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
            const hoverProgress = Math.max(0, Math.min(1, hoverDist / Math.max(1e-6, refSeries.dist_max || 1)));

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
            window.dash_clientside.clientside.updateLiveDashboard(tSec, miniStore, true, hoverProgress);

            const p1 = interpXY(d1, tSec);
            const p2 = interpXY(d2, tSec);
            if (!p1 || !p2) return window.dash_clientside.no_update;

            // Keep hover light as well: Plotly can move the two mounted marker
            // traces without Dash serialising a fresh mini-map figure.
            let mountedMiniMap = document.getElementById('mini-track-map');
            const hoverPlotly = (window.Plotly || (typeof Plotly !== 'undefined' ? Plotly : null));
            if (mountedMiniMap && hoverPlotly) {
                if (!mountedMiniMap.data) mountedMiniMap = mountedMiniMap.querySelector('.js-plotly-plot') || mountedMiniMap;
                if (mountedMiniMap && mountedMiniMap.data) {
                    hoverPlotly.restyle(mountedMiniMap, {
                        x: [[p1[0]], [p2[0]]], y: [[p1[1]], [p2[1]]],
                        hovertemplate: [
                            `<b>${d1.name || 'Driver 1'}</b><br>t=${tSec.toFixed(2)}s<extra></extra>`,
                            `<b>${d2.name || 'Driver 2'}</b><br>t=${tSec.toFixed(2)}s<extra></extra>`
                        ]
                    }, [1, 2]);
                    return window.dash_clientside.no_update;
                }
            }

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
            const playbackTrigger = window.dash_clientside.callback_context.triggered[0].prop_id;
            if (window.f1AnalyzerPlayback) {
                if (playbackTrigger.includes('lap-playback-interval')) return window.dash_clientside.no_update;
                if (playbackTrigger.includes('play-lap-btn')) window.f1AnalyzerPlayback.start(miniStore, ggStore);
                else if (playbackTrigger.includes('pause-resume-lap-btn')) window.f1AnalyzerPlayback.toggle(miniStore, ggStore);
                return [
                    window.dash_clientside.no_update, window.dash_clientside.no_update, window.dash_clientside.no_update,
                    true, 0, window.dash_clientside.no_update, window.dash_clientside.no_update,
                    window.dash_clientside.no_update
                ];
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
            } else if (trigger.includes('pause-resume-lap-btn')) {
                if (intervalDisabled) { lastUpdate = now; newIntervalDisabled = false; btnText = 'Pause'; }
                else { newIntervalDisabled = true; btnText = 'Resume'; }
            } else if (trigger.includes('lap-playback-interval')) {
                if (intervalDisabled) return window.dash_clientside.no_update;
                tSec += (now - lastUpdate) / 1000.0;
                lastUpdate = now;
            }

            if (tSec >= maxLap) { tSec = maxLap; newIntervalDisabled = true; btnText = 'Pause'; }

            // Update Live Dashboard on every replay frame.
            const deltaRef = (miniStore.delta && miniStore.delta.reference === 'd1') ? miniStore.d1 : miniStore.d2;
            const playbackProgress = tSec >= deltaRef.lap_s
                ? 1
                : interpMetric(deltaRef, Math.min(tSec, deltaRef.lap_s || tSec), 'dist');
            window.dash_clientside.clientside.updateLiveDashboard(tSec, miniStore, false, playbackProgress);

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
                    // Playback stores normalized progress; the chart uses the
                    // reference lap's derived-distance axis.
                    const cDistMeters = cDist * (ref.dist_max || 1);
                    const shapes = (speedDiv.layout.shapes || []).map(s => (s.name === 'playback-cursor' ? { ...s, x0: cDistMeters, x1: cDistMeters } : s));
                    if (!shapes.some(s => s.name === 'playback-cursor')) {
                        shapes.push({ type: 'line', name: 'playback-cursor', xref: 'x', yref: 'paper', x0: cDistMeters, x1: cDistMeters, y0: 0, y1: 1, line: { color: '#bbbbbb', width: 1.5, dash: 'dot' } });
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

        updateLiveDashboard: function(tSec, miniStore, hoverMode, deltaProgress) {
            const dash = document.getElementById('live-telemetry-dashboard');
            if (!dash) return;
            if (!miniStore || !miniStore.d1 || !miniStore.d2) {
                dash.style.display = 'none';
                return;
            }
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
                if (nameEl) { nameEl.innerText = data.name; nameEl.style.color = data.color; }
                if (speedEl) speedEl.innerText = Math.round(interpMetric(data, t, 'speed'));
                if (gearEl) gearEl.innerText = Math.round(interpMetric(data, t, 'gear'));
            };

            updateDriver('d1', miniStore.d1, tSec);
            updateDriver('d2', miniStore.d2, tSec);

            // Delta uses a 0..1 lap-progress scale so its lookup remains correct
            // regardless of which provider returned the normalized trace.
            // The lookup is cheap, so update it on every replay frame and hover.
            const getDeltaAtProgress = (targetProgress) => {
                    const delta = miniStore.delta || {};
                    const progress = delta.progress || [], values = delta.value || [];
                    if (progress.length < 2 || progress.length !== values.length) return null;
                    if (targetProgress <= progress[0]) return values[0];
                    if (targetProgress >= progress[progress.length - 1]) return values[values.length - 1];
                    let low = 0, high = progress.length - 1;
                    while (low <= high) {
                        const mid = (low + high) >>> 1;
                        if (progress[mid] < targetProgress) low = mid + 1;
                        else if (progress[mid] > targetProgress) high = mid - 1;
                        else return values[mid];
                    }
                    const ratio = (targetProgress - progress[low - 1]) / Math.max(1e-6, (progress[low] - progress[low - 1]));
                    return values[low - 1] + ratio * (values[low] - values[low - 1]);
            };

            const d1 = miniStore.d1, d2 = miniStore.d2;
            const primaryName = (miniStore.delta && miniStore.delta.primary) || d1.name;
            const secondaryName = (miniStore.delta && miniStore.delta.secondary) || d2.name;
            let targetProgress = deltaProgress;
            if (targetProgress === null || targetProgress === undefined) {
                const refSeries = (miniStore.delta && miniStore.delta.reference === 'd1') ? d1 : d2;
                targetProgress = interpMetric(
                    refSeries,
                    Math.min(tSec, refSeries.lap_s || tSec),
                    'dist'
                );
            }
            const delta = getDeltaAtProgress(Math.max(0, Math.min(1, targetProgress)));
            const deltaEl = document.getElementById('live-delta-value');
            const deltaLabelEl = document.querySelector('.delta-label');

            if (deltaEl && deltaLabelEl && delta !== null) {
                deltaLabelEl.innerText = `${primaryName || 'D1'} VS ${secondaryName || 'D2'}`;
                deltaEl.innerText = (delta >= 0 ? '+' : '-') + Math.abs(delta).toFixed(3) + 's';
                deltaEl.style.color = delta >= 0 ? '#00ff00' : '#ff4444';
            }
        },

        updateGGHover: function(hoverData, ggStore, fig, playbackDisabled) {
            if (playbackDisabled === false || (window.f1AnalyzerPlayback && window.f1AnalyzerPlayback.isRunning())) return window.dash_clientside.no_update;
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



        //         toggleFeedbackModal: function(open_clicks, mobile_open_clicks, cancel_clicks, refresh_data, is_open) {
        //             const trigger = window.dash_clientside.callback_context.triggered[0].prop_id;
        //             if (trigger === 'open-feedback-modal-btn.n_clicks' || trigger === 'mobile-open-feedback-modal-btn.n_clicks') return true;
        //             if (trigger.includes('cancel-feedback-btn') || trigger.includes('feedback-refresh-store')) return false;
        //             return is_open;
        //         },

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
        
        graphIdForTab: function(activeTab) {
            const ids = {
                'tab-telemetry': 'speed-graph',
                'tab-trackmap': '2d-dominance-graph',
                'tab-strategy': 'strategy-graph',
                'tab-racepace': 'race-gaps-graph'
            };
            return ids[activeTab] || null;
        },

        resizeVisiblePlots: function(activeTab, speedFigure, preloadStatus) {
            if (window.f1AnalyzerViewLoading) {
                window.f1AnalyzerViewLoading.sync(activeTab, preloadStatus);
            }
            if (activeTab !== 'tab-telemetry' && window.f1AnalyzerPlayback) {
                window.f1AnalyzerPlayback.stop();
            }
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
        const register = function() {
            navigator.serviceWorker.register('/service-worker.js').catch(function() {});
        };
        if ('requestIdleCallback' in window) {
            window.requestIdleCallback(register, {timeout: 2500});
        } else {
            window.setTimeout(register, 1200);
        }
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

    let resizeTimers = [];
    window.f1AnalyzerSchedulePlotResize = function() {
        resizeTimers.forEach(function(timer) {
            window.clearTimeout(timer);
        });
        resizeTimers = [80, 420].map(function(delay) {
            return window.setTimeout(resizeVisiblePlots, delay);
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
