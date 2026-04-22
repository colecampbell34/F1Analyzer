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

        updateMiniMap: function(hoverData, miniStore, fig) {
            if (!hoverData || !miniStore || !fig) return window.dash_clientside.no_update;
            if (!hoverData.points || hoverData.points.length === 0) return window.dash_clientside.no_update;
            const hoverDist = hoverData.points[0].x;
            if (hoverDist === null || hoverDist === undefined) return window.dash_clientside.no_update;

            const dist = miniStore.dist || [];
            const x = miniStore.x || [];
            const y = miniStore.y || [];
            if (dist.length < 2 || x.length !== dist.length || y.length !== dist.length) return window.dash_clientside.no_update;

            const bestI = window.dash_clientside.clientside.nearestIndex(dist, hoverDist);

            const baseData = (fig.data || []).filter(tr => !(tr && tr.meta === 'hover'));
            baseData.push({
                type: 'scatter',
                mode: 'markers',
                x: [x[bestI]],
                y: [y[bestI]],
                marker: {color: '#ff0000', size: 12, symbol: 'circle', line: {color: 'white', width: 2}},
                hoverinfo: 'skip',
                showlegend: false,
                meta: 'hover'
            });

            return {...fig, data: baseData};
        },

        updateGGHover: function(hoverData, ggStore, fig) {
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

                // 2. Motion Trail
                const start = Math.max(0, idx - 15);
                baseData.push({
                    type: 'scatter',
                    mode: 'lines',
                    x: lat.slice(start, idx + 1),
                    y: lng.slice(start, idx + 1),
                    line: {color: color, width: 3, shape: 'spline'},
                    opacity: 0.4,
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
